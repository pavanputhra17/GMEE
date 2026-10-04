# mypy: disallow-untyped-defs=False, disallow-incomplete-defs=False, disallow-any-generics=False

"""Build the GMEE link graph from imported articles — no LLM needed.

Pipeline:
  1. Load processed articles from Postgres
  2. Embed titles+content locally (all-mpnet-base-v2, 768-dim, normalized)
  3. Blockwise cosine candidates -> bounded top-K neighbors -> SIMILAR edges
  4. Exact content_hash collisions -> DUPLICATE_OF edges
  5. Persist Article/Domain nodes + FROM_DOMAIN/SIMILAR/DUPLICATE_OF edges in Neo4j

Usage (backend/, project .env loaded):
  python scripts/build_link_graph.py --max-articles 10000 --block-size 256

The article cap also limits embedding/input memory. The newest capped subset
is processed, existing graph data is retained, and truncation is reported.
Blockwise scoring uses bounded memory but still performs quadratic arithmetic.
"""

import argparse
import asyncio
import os
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from neo4j import GraphDatabase
from sqlalchemy import text

from app.db.postgres import async_session_maker
from app.services.evolution.similarity import top_neighbors, unit_matrix

SIM_THRESHOLD = 0.82
TOP_K = 3
EMBED_BATCH = 64
DEFAULT_MAX_ARTICLES = 10000
DEFAULT_BLOCK_SIZE = 256


async def load_articles(max_articles: int = DEFAULT_MAX_ARTICLES) -> list[dict[str, Any]]:
    if max_articles < 1:
        raise ValueError("max_articles must be positive")
    async with async_session_maker() as db:
        res = await db.execute(
            text(
                """
                SELECT id::text AS id, LEFT(COALESCE(title, ''), 300) AS title, url, domain,
                       LEFT(COALESCE(cleaned_content, ''), 2000) AS body,
                       COALESCE(content_hash, '') AS chash,
                       EXTRACT(EPOCH FROM published_at)::bigint AS pub_ts,
                       COALESCE(word_count, 0) AS wc
                FROM articles
                WHERE processing_status = 'processed'
                ORDER BY published_at DESC NULLS LAST, id
                LIMIT :max_articles
                """
            ),
            {"max_articles": max_articles + 1},
        )
        rows = res.all()
    if len(rows) > max_articles:
        print(f"article cap reached: processing only the newest {max_articles} articles; existing graph data is retained")
    rows = rows[:max_articles]
    print(f"loaded {len(rows)} processed articles (cap={max_articles})")
    return [dict(r._mapping) for r in rows]


def embed_all(bodies: list[str]) -> np.ndarray:
    from sentence_transformers import SentenceTransformer

    print("loading all-mpnet-base-v2 ...")
    model = SentenceTransformer("all-mpnet-base-v2")
    vecs = model.encode(
        bodies,
        batch_size=EMBED_BATCH,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=True,
    ).astype(np.float32)
    print(f"embedded {len(vecs)} texts, dim={vecs.shape[1]}")
    return vecs


def find_edges(
    vecs: np.ndarray,
    hashes: list[str],
    *,
    top_k: int = TOP_K,
    threshold: float = SIM_THRESHOLD,
    block_size: int = DEFAULT_BLOCK_SIZE,
):
    if len(vecs) != len(hashes):
        raise ValueError("each embedding must have a corresponding content hash")
    if top_k < 1 or block_size < 1:
        raise ValueError("top_k and block_size must be positive")
    n = len(vecs)
    edges: dict[tuple[int, int], float] = {}
    if n > 1:
        unit = unit_matrix(vecs)
        for i in range(n):
            for j, score in top_neighbors(
                unit, i, limit=top_k, threshold=threshold, block_size=block_size,
            ):
                key = (min(i, j), max(i, j))
                edges[key] = max(edges.get(key, -1.0), round(score, 4))

    by_hash = defaultdict(list)
    for i, h in enumerate(hashes):
        if h:
            by_hash[h].append(i)
    dupe_pairs = {
        (idxs[0], other)
        for idxs in by_hash.values() for other in idxs[1:]
    }
    print(f"SIMILAR edges (>= {threshold}, top-{top_k}): {len(edges)}")
    print(f"exact duplicate groups: {sum(1 for v in by_hash.values() if len(v) > 1)}")
    print(f"DUPLICATE_OF edges: {len(dupe_pairs)}")
    return sorted(
        [(i, j, score) for (i, j), score in edges.items()],
        key=lambda edge: (-edge[2], edge[0], edge[1]),
    ), sorted(dupe_pairs)


def write_neo4j(articles: list[dict], sim_edges, dupe_edges):
    uri = os.environ.get("NEO4J_URI", "bolt://127.0.0.1:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    pwd = os.environ.get("NEO4J_PASSWORD", "password")
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    driver.verify_connectivity()
    print(f"neo4j connected at {uri}")

    with driver.session() as ses:
        ses.run(
            "CREATE CONSTRAINT article_id IF NOT EXISTS FOR (a:Article) REQUIRE a.id IS UNIQUE"
        ).consume()
        ses.run(
            "CREATE CONSTRAINT domain_name IF NOT EXISTS FOR (d:Domain) REQUIRE d.name IS UNIQUE"
        ).consume()

        # domains
        domains = sorted({a["domain"] for a in articles if a["domain"]})
        ses.run(
            "UNWIND $names AS n MERGE (:Domain {name: n})",
            {"names": domains},
        ).consume()

        # articles
        t0 = datetime.now(UTC)
        B = 500
        for off in range(0, len(articles), B):
            chunk = [
                {
                    "id": a["id"],
                    "title": a["title"][:300],
                    "url": a["url"],
                    "domain": a["domain"],
                    "published_at": datetime.fromtimestamp(a["pub_ts"], tz=UTC).isoformat()
                    if a["pub_ts"]
                    else None,
                    "word_count": int(a["wc"]),
                    "hash": a["chash"],
                }
                for a in articles[off : off + B]
            ]
            ses.run(
                """
                UNWIND $rows AS r
                MERGE (ar:Article {id: r.id})
                  SET ar.title = r.title, ar.url = r.url, ar.domain = r.domain,
                      ar.wordCount = r.word_count,
                      ar.publishedAt = r.published_at, ar.contentHash = r.hash
                WITH ar, r
                MATCH (d:Domain {name: r.domain})
                MERGE (ar)-[:FROM_DOMAIN]->(d)
                """,
                {"rows": chunk},
            ).consume()
            print(f"  articles {min(off + B, len(articles))}/{len(articles)}")

        # SIMILAR edges
        for off in range(0, len(sim_edges), B):
            rows = [
                {"a": articles[i]["id"], "b": articles[j]["id"], "score": s}
                for i, j, s in sim_edges[off : off + B]
            ]
            ses.run(
                """
                UNWIND $rows AS r
                MATCH (a:Article {id: r.a}), (b:Article {id: r.b})
                MERGE (a)-[e:SIMILAR]->(b)
                  SET e.score = r.score
                """,
                {"rows": rows},
            ).consume()
            print(f"  similar {min(off + B, len(sim_edges))}/{len(sim_edges)}")

        # DUPLICATE_OF edges use the same bounded write payload as similarities.
        for off in range(0, len(dupe_edges), B):
            rows = [
                {"a": articles[i]["id"], "b": articles[j]["id"]}
                for i, j in dupe_edges[off:off + B]
            ]
            ses.run(
                """
                UNWIND $rows AS r
                MATCH (a:Article {id: r.a}), (b:Article {id: r.b})
                MERGE (a)-[:DUPLICATE_OF]->(b)
                """,
                {"rows": rows},
            ).consume()

        # stats
        stats = {}
        for label, q in [
            ("articles", "MATCH (a:Article) RETURN count(a)"),
            ("domains", "MATCH (d:Domain) RETURN count(d)"),
            ("similar", "MATCH ()-[e:SIMILAR]->() RETURN count(e)"),
            ("dupes", "MATCH ()-[e:DUPLICATE_OF]->() RETURN count(e)"),
        ]:
            rec = ses.run(q).single()
            if rec is None:
                continue
            stats[label] = rec[0]
        print("\n=== NEO4J GRAPH ===")
        for k, v in stats.items():
            print(f"{k}: {v}")

        # most-connected articles
        print("\n=== TOP HUB STORIES ===")
        hub = ses.run(
            """
            MATCH (a:Article)-[e:SIMILAR]-()
            RETURN a.title AS t, a.domain AS d, count(e) AS deg
            ORDER BY deg DESC LIMIT 8
            """
        )
        for rec in hub:
            print(f"  [{rec['deg']:3d} links] ({rec['d']}) {rec['t'][:80]}")

        # sample chain
        print("\n=== SAMPLE STORY CLUSTER ===")
        cluster = ses.run(
            """
            MATCH (a:Article)-[e1:SIMILAR]-(b:Article)-[e2:SIMILAR]-(c:Article)
            WHERE id(a) < id(c)
            WITH a, b, c LIMIT 1
            MATCH (x)-[s:SIMILAR]-(y)
            WHERE x IN [a,b,c] AND y IN [a,b,c]
            RETURN x.title AS x, y.title AS y, s.score AS score
            """
        )
        for rec in cluster:
            print(f"  ({rec['score']}) {rec['x'][:60]}  <->  {rec['y'][:60]}")

    driver.close()
    print(f"\ngraph build finished in {(datetime.now(UTC) - t0).total_seconds():.1f}s")


async def main(
    *,
    max_articles: int = DEFAULT_MAX_ARTICLES,
    block_size: int = DEFAULT_BLOCK_SIZE,
) -> None:
    articles = await load_articles(max_articles=max_articles)
    if not articles:
        print("No processed articles; nothing to embed or project.")
        return
    bodies = [f"{a['title']}. {a['body']}"[:2000] for a in articles]
    hashes = [a["chash"] for a in articles]
    vecs = embed_all(bodies)
    sim_edges, dupe_edges = find_edges(vecs, hashes, block_size=block_size)
    write_neo4j(articles, sim_edges, dupe_edges)


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-articles", type=_positive_int,
        default=os.environ.get("LINK_GRAPH_MAX_ARTICLES", str(DEFAULT_MAX_ARTICLES)),
        help="maximum newest articles loaded/embedded (default: 10000, or LINK_GRAPH_MAX_ARTICLES)",
    )
    parser.add_argument(
        "--block-size", type=_positive_int,
        default=os.environ.get("LINK_GRAPH_BLOCK_SIZE", str(DEFAULT_BLOCK_SIZE)),
        help="maximum cosine scores materialized per query block (default: 256)",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(max_articles=args.max_articles, block_size=args.block_size))
