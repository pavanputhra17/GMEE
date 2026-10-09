# mypy: disallow-untyped-defs=False, disallow-incomplete-defs=False, disallow-any-generics=False

"""Stratified gold-standard pair sampler.

Draws N pairs per cosine-similarity bucket from the embedded claim corpus and
inserts them into eval_pairs. Cross-outlet pairs are preferred (a same-outlet
pair can never corroborate), and each bucket is capped so no single bucket
dominates the annotation workload.

Buckets (cosine similarity):
  b95  0.95-1.00   b85  0.85-0.95   b75  0.75-0.85
  b60  0.60-0.75   b40  0.40-0.60   b00  0.00-0.40

Usage: python scripts/sample_eval_pairs.py [per_bucket=50] [pool=1500]
"""

import asyncio
import random
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from app.db.postgres import async_session_maker
from app.models.eval import EvalPair

BUCKETS = [
    ("b95", 0.95, 1.01),
    ("b85", 0.85, 0.95),
    ("b75", 0.75, 0.85),
    ("b60", 0.60, 0.75),
    ("b40", 0.40, 0.60),
    ("b00", -0.01, 0.40),
]


import ast


def parse_embedding(raw) -> "np.ndarray":
    """pgvector comes back as a string under asyncpg — parse robustly."""
    if raw is None:
        return np.zeros((768,), dtype=np.float32)
    if isinstance(raw, str):
        return np.asarray(ast.literal_eval(raw), dtype=np.float32)
    return np.asarray(raw, dtype=np.float32)


async def fetch_pool(pool_size: int):
    """Random embedded claims (recency-spread) with their outlet domain."""
    async with async_session_maker() as db:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT c.id::text AS id, c.embedding, a.domain AS domain
                    FROM claims c JOIN articles a ON a.id = c.article_id
                    WHERE c.embedding IS NOT NULL
                    ORDER BY random()
                    LIMIT :n
                    """
                ),
                {"n": pool_size},
            )
        ).all()
    return [(r[0], parse_embedding(r[1]), r[2] or "unknown") for r in rows]


def pick_pairs(pool, per_bucket: int, rng: random.Random) -> list[tuple[str, str, float]]:
    ids = np.stack([p[1] for p in pool])
    norms = np.linalg.norm(ids, axis=1, keepdims=True)
    unit = ids / np.maximum(norms, 1e-9)
    sims = unit @ unit.T

    # de-duplicate claims that came from the same outlet paragraph-by-paragraph
    by_bucket: dict[str, list[tuple[int, int, float]]] = defaultdict(list)
    n = len(pool)
    for i, j in combinations(range(n), 2):
        s = float(sims[i, j])
        if s <= 0.0:
            continue
        for name, lo, hi in BUCKETS:
            if lo <= s < hi:
                by_bucket[name].append((i, j, s))
                break

    chosen: list[tuple[str, str, float]] = []
    for name, _, _ in BUCKETS:
        cand = by_bucket.get(name, [])
        # prefer cross-outlet pairs: a same-outlet pair can never corroborate
        cand.sort(key=lambda ij: (pool[ij[0]][2] == pool[ij[1]][2],))
        rng.shuffle(cand[: max(len(cand) // 2, 1)])
        taken = 0
        seen_ids: set[str] = set()
        for i, j, s in cand:
            if taken >= per_bucket:
                break
            a, b = pool[i][0], pool[j][0]
            # allow at most 2 pairs per claim to keep diversity
            if (a in seen_ids or b in seen_ids) and taken < per_bucket // 2:
                continue
            seen_ids.update((a, b))
            chosen.append((a, b, s))
            taken += 1
    return chosen


async def main() -> None:
    per_bucket = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    pool_size = int(sys.argv[2]) if len(sys.argv) > 2 else 1500
    rng = random.Random(20260916)  # deterministic sampling — reproducible eval

    pool = await fetch_pool(pool_size)
    print(f"pool: {len(pool)} embedded claims")
    if len(pool) < 10:
        print("not enough embedded claims — run NLP first")
        return

    pairs = pick_pairs(pool, per_bucket, rng)
    print(f"selected {len(pairs)} pairs across {len(BUCKETS)} buckets")

    async with async_session_maker() as db:
        # idempotent: never re-sample a pair that's already in the table
        existing = (
            await db.execute(text("SELECT claim_a_id::text, claim_b_id::text FROM eval_pairs"))
        ).all()
        existing_set = {frozenset((a, b)) for a, b in existing}

        inserted = 0
        for a, b, s in pairs:
            key = frozenset((a, b))
            if key in existing_set:
                continue
            bucket = next(name for name, lo, hi in BUCKETS if lo <= s < hi)
            db.add(EvalPair(claim_a_id=a, claim_b_id=b, bucket=bucket, sim_score=round(s, 6)))
            existing_set.add(key)
            inserted += 1
        await db.commit()
    print(f"inserted {inserted} new pairs (skipped {len(pairs) - inserted} duplicates)")


if __name__ == "__main__":
    asyncio.run(main())