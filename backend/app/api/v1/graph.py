"""Full-graph endpoint: every article node + every SIMILAR/DUPLICATE_OF edge.

The whole corpus graph in one payload (6.4k nodes, ~800 edges ≈ 1-2MB JSON).
"""

import html as htmllib
import logging
import re

from fastapi import APIRouter
from sqlalchemy import text

from app.db.neo4j_client import neo4j_client

logger = logging.getLogger(__name__)

router = APIRouter()

_TAG_RE = re.compile(r"<[^a-z/!]|</?[a-z][^>]*>", re.IGNORECASE)


def _clean_text(v, limit: int = 200) -> str | None:
    """Strip any markup/entities from stored text before it reaches the UI."""
    if not v:
        return None
    s = htmllib.unescape(_TAG_RE.sub(" ", str(v)))
    s = re.sub(r"\s+", " ", s).strip()
    return (s[:limit] or None)


@router.get("/full")
async def full_graph():
    driver = await neo4j_client.get_driver()

    async def _run(tx):
        # nodes: all articles with their outlet + degree
        nodes_res = await tx.run(
            """
            MATCH (a:Article)
            OPTIONAL MATCH (a)-[e:SIMILAR]-()
            RETURN a.id AS id,
                   a.title AS title,
                   a.domain AS domain,
                   a.url AS url,
                   a.publishedAt AS published_at,
                   count(e) AS deg
            """
        )
        nodes = await nodes_res.data()

        edges_res = await tx.run(
            """
            MATCH (a:Article)-[e:SIMILAR]-(b:Article)
            RETURN a.id AS src, b.id AS dst, e.score AS score
            """
        )
        raw = await edges_res.data()

        dupe_res = await tx.run(
            """
            MATCH (a:Article)-[:DUPLICATE_OF]-(b:Article)
            RETURN a.id AS src, b.id AS dst
            """
        )
        dupes = await dupe_res.data()
        return nodes, raw, dupes

    async with driver.session() as ses:
        nodes, raw, dupes = await ses.execute_read(_run)

    seen = set()
    edges = []
    for e in raw:
        key = tuple(sorted((e["src"], e["dst"])))
        if key in seen:
            continue
        seen.add(key)
        edges.append({"src": e["src"], "dst": e["dst"], "score": round(float(e["score"]), 3)})
    for e in dupes:
        key = tuple(sorted((e["src"], e["dst"])))
        if key in seen:
            continue
        seen.add(key)
        edges.append({"src": e["src"], "dst": e["dst"], "score": 1.0})

    return {
        "nodes": [
            {
                "id": n["id"],
                "title": _clean_text(n.get("title"), 160) or "",
                "domain": _clean_text(n.get("domain"), 80),
                "url": n.get("url"),
                "published_at": n.get("published_at"),
                "deg": n.get("deg", 0),
            }
            for n in nodes
        ],
        "edges": edges,
        "counts": {"nodes": len(nodes), "edges": len(edges)},
    }


@router.get("/claims")
async def claims_graph(limit: int = 1200):
    """Claims network from Postgres pgvector: near-duplicate claim pairs as edges."""
    from app.db.postgres import async_session_maker

    async with async_session_maker() as db:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT c.id::text AS id, c.claim_text AS title,
                           a.domain AS domain,
                           c.verdict AS verdict,
                           c.verdict_probability AS prob
                    FROM claims c JOIN articles a ON a.id = c.article_id
                    WHERE c.embedding IS NOT NULL AND c.verdict IS NOT NULL
                    ORDER BY c.confidence DESC NULLS LAST
                    LIMIT :lim
                    """
                ),
                {"lim": limit},
            )
        ).all()
        pair_rows = (
            await db.execute(
                text(
                    """
                    SELECT a.id::text AS src, b.id::text AS dst,
                           1 - (a.embedding <=> b.embedding) AS sim
                    FROM claims a, claims b
                    WHERE a.id < b.id
                      AND a.embedding IS NOT NULL AND b.embedding IS NOT NULL
                      AND 1 - (a.embedding <=> b.embedding) >= :thresh
                    LIMIT 4000
                    """
                ),
                {"thresh": 0.86},
            )
        ).all()

    nodes = [
        {
            "id": r[0], "title": _clean_text(r[1], 180) or "", "domain": _clean_text(r[2], 80),
            "verdict": r[3], "prob": float(r[4]) if r[4] is not None else None,
        }
        for r in rows
    ]
    idset = {n["id"] for n in nodes}
    edges = [
        {"src": r[0], "dst": r[1], "score": round(float(r[2]), 3)}
        for r in pair_rows
        if r[0] in idset and r[1] in idset
    ]
    return {
        "nodes": nodes,
        "edges": edges,
        "counts": {"nodes": len(nodes), "edges": len(edges)},
    }
