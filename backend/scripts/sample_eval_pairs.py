# mypy: disallow-untyped-defs=False, disallow-incomplete-defs=False, disallow-any-generics=False

"""Stratified gold-standard pair sampler.

Draws N pairs per cosine-similarity bucket from the embedded claim corpus and
inserts them into eval_pairs. Cross-outlet pairs are preferred (a same-outlet
pair can never corroborate), and each bucket is capped so no single bucket
dominates the annotation workload.

Buckets (cosine similarity):
  b95  0.95-1.00   b85  0.85-0.95   b75  0.75-0.85
  b60  0.60-0.75   b40  0.40-0.60   b00  0.00-0.40

Usage: python scripts/sample_eval_pairs.py [per_bucket=50] [pool=1500] [--seed 20260916]

The DB pool is seeded by a stable ID hash, not SQL random(). At most two
new+existing pairs per claim are allowed; pre-existing violations are retained.
"""

import argparse
import asyncio
import hashlib
import random
import sys
import uuid
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.postgres import async_session_maker
from app.models.eval import EvalPair
from app.services.eval.dataset import lock_pair_writes

BUCKETS = [
    ("b95", 0.95, 1.01),
    ("b85", 0.85, 0.95),
    ("b75", 0.75, 0.85),
    ("b60", 0.60, 0.75),
    ("b40", 0.40, 0.60),
    ("b00", -1.01, 0.40),
]


import ast


def parse_embedding(raw) -> "np.ndarray":
    """pgvector comes back as a string under asyncpg — parse robustly."""
    if raw is None:
        return np.zeros((768,), dtype=np.float32)
    if isinstance(raw, str):
        return np.asarray(ast.literal_eval(raw), dtype=np.float32)
    return np.asarray(raw, dtype=np.float32)


async def fetch_pool(pool_size: int, seed: int = 20260916):
    """Deterministic seeded pool for a fixed corpus snapshot (including ID ties)."""
    async with async_session_maker() as db:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT c.id::text AS id, c.embedding, a.domain AS domain
                    FROM claims c JOIN articles a ON a.id = c.article_id
                    WHERE c.embedding IS NOT NULL
                    ORDER BY md5(c.id::text || ':' || :seed), c.id
                    LIMIT :n
                    """
                ),
                {"n": pool_size, "seed": str(seed)},
            )
        ).all()
    return [(r[0], parse_embedding(r[1]), r[2] or "unknown") for r in rows]


def pick_pairs(pool, per_bucket: int, rng: random.Random) -> list[tuple[str, str, float]]:
    if per_bucket < 1:
        raise ValueError("per_bucket must be positive")
    if len(pool) < 2:
        return []
    pool = sorted(pool, key=lambda p: p[0])
    if len({p[0] for p in pool}) != len(pool):
        raise ValueError("pool contains duplicate claim IDs")
    vectors = np.stack([p[1] for p in pool])
    if vectors.ndim != 2 or not np.isfinite(vectors).all():
        raise ValueError("pool embeddings must be finite vectors of equal dimension")
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    unit = vectors / np.maximum(norms, 1e-9)
    sims = unit @ unit.T
    by_bucket: dict[str, list[tuple[int, int, float]]] = defaultdict(list)
    for i, j in combinations(range(len(pool)), 2):
        if norms[i, 0] == 0 or norms[j, 0] == 0:
            continue
        score = float(np.clip(sims[i, j], -1.0, 1.0))
        for name, lo, hi in BUCKETS:
            if lo <= score < hi:
                by_bucket[name].append((i, j, score))
                break

    chosen: list[tuple[str, str, float]] = []
    usage: Counter[str] = Counter()
    for name, _, _ in BUCKETS:
        candidates = by_bucket.get(name, [])
        rng.shuffle(candidates)  # Shuffle the real list, not a discarded slice.
        candidates.sort(key=lambda ij: pool[ij[0]][2] == pool[ij[1]][2])
        taken = 0
        for i, j, score in candidates:
            if taken >= per_bucket:
                break
            a, b = sorted((pool[i][0], pool[j][0]))
            if usage[a] >= 2 or usage[b] >= 2:
                continue
            usage.update((a, b))
            chosen.append((a, b, score))
            taken += 1
    return chosen


def pool_fingerprint(pool) -> str:
    digest = hashlib.sha256()
    for claim_id, embedding, domain in sorted(pool, key=lambda p: p[0]):
        digest.update(f"{claim_id}:{domain}:".encode())
        digest.update(np.asarray(embedding, dtype="<f4").tobytes())
    return digest.hexdigest()


async def main() -> None:
    parser = argparse.ArgumentParser(description="Deterministically sample blinded evaluation pairs without deleting history")
    parser.add_argument("per_bucket", nargs="?", type=int, default=50)
    parser.add_argument("pool", nargs="?", type=int, default=1500)
    parser.add_argument("--seed", type=int, default=20260916)
    args = parser.parse_args()
    if args.per_bucket < 1 or args.pool < 2:
        parser.error("per_bucket must be positive and pool must be at least 2")
    pool = await fetch_pool(args.pool, args.seed)
    print(f"pool: {len(pool)} embedded claims; seed={args.seed}")
    if len(pool) < 2:
        parser.error("not enough embedded claims; run NLP before sampling")
    pairs = pick_pairs(pool, args.per_bucket, random.Random(args.seed))
    provenance = {
        "method": "seeded-id-hash-pool+stratified-cosine-v2", "seed": args.seed,
        "pool_size_requested": args.pool, "pool_size_actual": len(pool),
        "pool_sha256": pool_fingerprint(pool), "per_bucket": args.per_bucket,
        "max_pairs_per_claim": 2, "embedding_source": "stored claims.embedding; historical model version unknown",
    }
    inserted = duplicates = capped = frozen = 0
    async with async_session_maker() as db:
        await lock_pair_writes(db)
        existing = (await db.execute(text("SELECT claim_a_id::text, claim_b_id::text, split FROM eval_pairs"))).all()
        existing_set = {tuple(sorted((a, b))) for a, b, _ in existing}
        usage = Counter(claim for a, b, _ in existing for claim in (a, b))
        # Do not add a new pair sharing a frozen article/claim component. Split
        # assignment must remain a complete freeze, not be weakened by sampling.
        protected_articles = {str(r[0]) for r in (await db.execute(text("""
            SELECT DISTINCT c.article_id FROM claims c JOIN eval_pairs p
            ON c.id IN (p.claim_a_id, p.claim_b_id) WHERE p.split <> 'unassigned'
        """))).all()}
        protected_claims = {str(r[0]) for r in (await db.execute(text("""
            SELECT c.id FROM claims c WHERE c.article_id IN (
                SELECT c2.article_id FROM claims c2 JOIN eval_pairs p
                ON c2.id IN (p.claim_a_id, p.claim_b_id) WHERE p.split <> 'unassigned'
            )
        """))).all()} if protected_articles else set()
        for a, b, score in pairs:
            key = (a, b)
            if key in existing_set:
                duplicates += 1
                continue
            if a in protected_claims or b in protected_claims:
                frozen += 1
                continue
            if usage[a] >= 2 or usage[b] >= 2:
                capped += 1
                continue
            bucket = next(name for name, lo, hi in BUCKETS if lo <= score < hi)
            canonical_key = f"{a}:{b}"
            statement = pg_insert(EvalPair).values(
                id=uuid.uuid5(uuid.NAMESPACE_URL, f"gmee-eval:{canonical_key}"),
                claim_a_id=uuid.UUID(a), claim_b_id=uuid.UUID(b), canonical_key=canonical_key,
                bucket=bucket, sim_score=round(score, 6), split="unassigned", event_group="unassigned",
                sampling_provenance=provenance,
            ).on_conflict_do_nothing().returning(EvalPair.id)
            if (await db.execute(statement)).scalar_one_or_none() is None:
                duplicates += 1
                continue
            existing_set.add(key)
            usage.update((a, b))
            inserted += 1
        await db.commit()
    print(f"selected={len(pairs)} inserted={inserted} duplicate/conflict={duplicates} claim-cap={capped} frozen-component={frozen}")
    print("Historical pairs/votes were retained; bucket shortfalls are not silently filled with a different sample.")


if __name__ == "__main__":
    asyncio.run(main())