# mypy: disallow-untyped-defs=False, disallow-incomplete-defs=False, disallow-any-generics=False

"""Build the GMEE link graph from imported articles — no LLM needed.

Pipeline:
  1. Load processed articles from Postgres
  2. Embed titles+content locally (all-mpnet-base-v2, 768-dim, normalized)
  3. Cosine-similarity matrix -> top-K neighbors above threshold -> SIMILAR edges
  4. Exact content_hash collisions -> DUPLICATE_OF edges
  5. Persist Article/Domain nodes + FROM_DOMAIN/SIMILAR/DUPLICATE_OF edges in Neo4j

Usage (backend/, project .env loaded):
  NEO4J_URI=bolt://127.0.0.1:7687 python scripts/build_link_graph.py
"""

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

SIM_THRESHOLD = 0.82
TOP_K = 3
EMBED_BATCH = 64


async def load_articles() -> list[dict[str, Any]]:
    async with async_session_maker() as db:
        res = await db.execute(
            text(
                """
                SELECT id::text, title, url, domain,
                       COALESCE(cleaned_content, '') AS body,
                       COALESCE(content_hash, '') AS chash,
                       EXTRACT(EPOCH FROM published_at)::bigint AS pub_ts,
                       COALESCE(word_count, 0) AS wc
                FROM articles
                WHERE processing_status = 'processed'
                ORDER BY published_at ASC
                """
            )
        )
        rows = res.all()
    print(f"loaded {len(rows)} processed articles")
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


def find_edges(vecs: np.ndarray, hashes: list[str]):
    n = len(vecs)
    sims = vecs @ vecs.T
    np.fill_diagonal(sims, -1.0)

    edges = set()
    # top-K above threshold per row
    topk_idx = np.argpartition(-sims, range(min(TOP_K, n - 1)), axis=1)[:, :TOP_K]
    for i in range(n):
        for j in topk_idx[i]:
            s = float(sims[i, j])
            if s >= SIM_THRESHOLD:
                key = (min(i, j), max(i, j))
                if key not in edges:
                    edges.add((key[0], key[1], round(s, 4)))

    # hash duplicates
    by_hash = defaultdict(list)
    for i, h in enumerate(hashes):
        if h:
            by_hash[h].append(i)
    dupe_pairs = set()
    for h, idxs in by_hash.items():
        if len(idxs) > 1:
            base = idxs[0]
            for other in idxs[1:]:
                dupe_pairs.add((base, other))

    print(f"SIMILAR edges (>= {SIM_THRESHOLD}, top-{TOP_K}): {len(edges)}")
    print(f"exact duplicate groups: {sum(1 for v in by_hash.values() if len(v) > 1)}")
    print(f"DUPLICATE_OF edges: {len(dupe_pairs)}")
    return sorted(edges, key=lambda e: -e[2]), sorted(dupe_pairs)


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
                  SET ar.title = r.title, ar.url = r.url, ar.wordCount = r.word_count,
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

        # DUPLICATE_OF edges
        rows = [
            {"a": articles[i]["id"], "b": articles[j]["id"]}
            for i, j in dupe_edges
        ]
        if rows:
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


async def main() -> None:
    articles = await load_articles()
    bodies = [
        f"{a['title']}. {a['body']}"[:2000] for a in articles
    ]
    hashes = [a["chash"] for a in articles]
    vecs = embed_all(bodies)
    sim_edges, dupe_edges = find_edges(vecs, hashes)
    write_neo4j(articles, sim_edges, dupe_edges)


if __name__ == "__main__":
    asyncio.run(main())
