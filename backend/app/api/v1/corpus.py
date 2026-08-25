"""Read-only endpoints exposing the real corpus + story graph."""

import logging
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from app.db.neo4j_client import neo4j_client
from app.db.postgres import async_session_maker

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------- articles


@router.get("/articles")
async def list_articles(
    q: str = Query("", max_length=120),
    domain: str = Query("", max_length=80),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Paginated, searchable corpus listing."""
    like = f"%{q}%"
    where = ["processing_status = 'processed'"]
    params: dict[str, object] = {"limit": limit, "offset": offset}
    if q:
        where.append("(title ILIKE :like OR author ILIKE :like)")
        params["like"] = like
    if domain:
        where.append("domain = :domain")
        params["domain"] = domain
    where_sql = " AND ".join(where)

    count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}
    async with async_session_maker() as db:
        total = (
            await db.execute(
                text(f"SELECT COUNT(*) FROM articles WHERE {where_sql}"), count_params
            )
        ).scalar()
        rows = (
            await db.execute(
                text(
                    f"""
                    SELECT id::text, title, url, author, domain, language,
                           published_at, word_count, nlp_status,
                           LEFT(COALESCE(cleaned_content, content, ''), 240) AS excerpt
                    FROM articles
                    WHERE {where_sql}
                    ORDER BY published_at DESC NULLS LAST
                    LIMIT :limit OFFSET :offset
                    """
                ),
                params,
            )
        ).all()
        domains = (
            await db.execute(
                text(
                    "SELECT domain, COUNT(*) AS c FROM articles "
                    "WHERE processing_status='processed' GROUP BY domain ORDER BY c DESC"
                )
            )
        ).all()

    return {
        "total": total or 0,
        "limit": limit,
        "offset": offset,
        "items": [dict(r._mapping) for r in rows],
        "domains": [{"name": d[0], "count": d[1]} for d in domains],
    }


@router.get("/articles/recent")
async def recent_articles(limit: int = Query(12, ge=1, le=40)):
    """Most recently collected articles — the true ingest stream."""
    async with async_session_maker() as db:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT a.id::text AS id, a.title AS title, a.url AS url, a.domain AS domain,
                           s.name AS source_name,
                           a.collected_at, a.published_at, a.word_count
                    FROM articles a
                    LEFT JOIN sources s ON s.id = a.source_id
                    WHERE a.processing_status = 'processed'
                    ORDER BY COALESCE(a.collected_at, a.processed_at) DESC
                    LIMIT :limit
                    """
                ),
                {"limit": limit},
            )
        ).all()
    items = []
    for r in rows:
        m = dict(r._mapping)
        m["collected_at"] = m["collected_at"].isoformat() if m["collected_at"] else None
        m["published_at"] = m["published_at"].isoformat() if m["published_at"] else None
        items.append(m)
    return {"items": items}


@router.get("/stats")
async def corpus_stats():
    """Real corpus statistics for telemetry panels."""
    async with async_session_maker() as db:
        row = (
            await db.execute(
                text(
                    """
                    SELECT COUNT(*) AS total,
                           COUNT(embedding) AS embedded,
                           COUNT(DISTINCT domain) AS domains,
                           MIN(published_at)::date AS earliest,
                           MAX(published_at)::date AS latest
                    FROM articles WHERE processing_status='processed'
                    """
                )
            )
        ).first()
        nlp = (
            await db.execute(
                text(
                    "SELECT nlp_status, COUNT(*) FROM articles GROUP BY nlp_status"
                )
            )
        ).all()
    m = dict(row._mapping) if row else {}
    return {
        "total": int(m.get("total") or 0),
        "embedded": int(m.get("embedded") or 0),
        "domains": int(m.get("domains") or 0),
        "earliest": str(m.get("earliest")) if m.get("earliest") else None,
        "latest": str(m.get("latest")) if m.get("latest") else None,
        "nlp_counts": {k: int(v) for k, v in nlp},
    }


# ---------------------------------------------------------------- semantic search


@router.get("/search")
async def semantic_search(
    q: str = Query(..., min_length=2, max_length=300),
    limit: int = Query(10, ge=1, le=30),
):
    """Nearest-neighbor article search via pgvector cosine distance."""
    from sqlalchemy import text as sql_text

    from app.services.nlp.embedding_service import EmbeddingService

    try:
        EmbeddingService.load_model()
        qvec = EmbeddingService.generate_embedding(q)
    except Exception as exc:  # model load failure etc.
        logger.exception("embedding failure")
        raise HTTPException(status_code=503, detail=f"embedding service unavailable: {exc}")

    lit = "[" + ",".join(f"{x:.6f}" for x in qvec) + "]"

    async with async_session_maker() as db:
        rows = (
            await db.execute(
                sql_text(
                    """
                    SELECT id::text, title, url, author, domain,
                           published_at, word_count,
                           1 - (embedding <=> CAST(:qv AS vector)) AS score
                    FROM articles
                    WHERE embedding IS NOT NULL
                    ORDER BY embedding <=> CAST(:qv AS vector)
                    LIMIT :lim
                    """
                ),
                {"qv": lit, "lim": limit},
            )
        ).all()

    items = []
    for r in rows:
        m = dict(r._mapping)
        m["score"] = round(float(m["score"]), 4)
        m["published_at"] = m["published_at"].isoformat() if m["published_at"] else None
        items.append(m)

    return {"query": q, "count": len(items), "items": items}


@router.get("/articles/{article_id}")
async def article_detail(article_id: str):
    async with async_session_maker() as db:
        row = (
            await db.execute(
                text(
                    """
                    SELECT id::text, title, url, author, domain, language,
                           published_at, collected_at, word_count, nlp_status,
                           COALESCE(cleaned_content, content, '') AS body
                    FROM articles WHERE id = CAST(:aid AS uuid)
                    """
                ),
                {"aid": article_id},
            )
        ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="article not found")
    return dict(row._mapping)


# ---------------------------------------------------------------- graph


@router.get("/graph/story-clusters")
async def story_clusters(min_links: int = Query(3, ge=1), limit: int = Query(6, ge=1, le=20)):
    """Hub stories (most SIMILAR links) with their cross-outlet neighbors."""
    driver = await neo4j_client.get_driver()

    async def _run(tx):
        hubs_res = await tx.run(
            """
            MATCH (a:Article)-[e:SIMILAR]-(b:Article)
            WITH a, count(e) AS deg, sum(e.score) AS mass
            WHERE deg >= $min_links
            RETURN a.id AS id, a.title AS title, a.domain AS domain,
                   a.url AS url, deg, mass
            ORDER BY deg DESC LIMIT $limit
            """,
            min_links=min_links,
            limit=limit,
        )
        hubs = await hubs_res.data()
        out = []
        for h in hubs:
            nbrs = await tx.run(
                """
                MATCH (a:Article {id: $id})-[e:SIMILAR]-(b:Article)
                RETURN b.id AS id, b.title AS title, b.domain AS domain,
                       b.url AS url, e.score AS score
                ORDER BY e.score DESC
                """,
                id=h["id"],
            )
            nbrs_data = await nbrs.data()
            out.append({**h, "neighbors": nbrs_data})
        return out

    async with driver.session() as ses:
        clusters = await ses.execute_read(_run)
    return {"clusters": clusters}


@router.get("/graph/stats")
async def graph_stats():
    driver = await neo4j_client.get_driver()

    async def _run(tx):
        stats = {}
        for label, q in [
            ("articles", "MATCH (a:Article) RETURN count(a)"),
            ("domains", "MATCH (d:Domain) RETURN count(d)"),
            ("similar", "MATCH ()-[e:SIMILAR]->() RETURN count(e)"),
            ("dupes", "MATCH ()-[e:DUPLICATE_OF]->() RETURN count(e)"),
        ]:
            res = await tx.run(q)
            stats[label] = (await res.single())[0]

        outlets_res = await tx.run(
            """
            MATCH (a:Article)-[:FROM_DOMAIN]->(d:Domain)
            OPTIONAL MATCH (a)-[e:SIMILAR]-(b:Article)
            WHERE b.domain IS NOT NULL AND b.domain <> d.name
            RETURN d.name AS name, count(DISTINCT a) AS stories,
                   count(DISTINCT CASE WHEN b IS NOT NULL THEN b END) AS cross
            ORDER BY stories DESC
            """)
        stats["outlets"] = await outlets_res.data()
        return stats

    async with driver.session() as ses:
        return await ses.execute_read(_run)
