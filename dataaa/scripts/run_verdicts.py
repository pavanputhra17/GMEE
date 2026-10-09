# mypy: disallow-untyped-defs=False, disallow-incomplete-defs=False, disallow-any-generics=False

"""Batch verdict runner — scores every claim in the corpus.

For each claim:
  1. pull its embedding + entities + source outlet
  2. find near-neighbor claims via pgvector (cross-outlet)
  3. NLI-check the closest few for entailment/contradiction stance
  4. combine five signals -> P(supported), band, rationale, evidence
  5. persist to claims.verdict_*

Usage: python scripts/run_verdicts.py [limit]
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import bindparam, text

from app.db.postgres import async_session_maker
from app.services.verdict.engine import (
    DISPUTED_BANDS,
    SUPPORTED_BANDS,
    VerdictEngine,
    near_window,
    nli_stance,
)


async def load_claims(limit: int):
    async with async_session_maker() as db:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT c.id::text AS id, c.claim_text, c.embedding,
                           a.domain AS outlet,
                           COALESCE(
                               (SELECT json_agg(json_build_object(
                                   'entity_type', ce.entity_type))
                                FROM claim_entities ce WHERE ce.claim_id = c.id),
                               '[]'::json) AS entities
                    FROM claims c
                    JOIN articles a ON a.id = c.article_id
                    WHERE c.verdict IS NULL
                    ORDER BY c.confidence DESC NULLS LAST
                    LIMIT :lim
                    """
                ),
                {"lim": limit},
            )
        ).all()
        return [dict(r._mapping) for r in rows]


async def neighbors_for(db, claim_id: str, emb) -> list[dict]:
    if emb is None:
        return []
    res = await db.execute(
        text(
            """
            SELECT c.id::text AS id, c.claim_text, a.domain AS domain,
                   c.embedding <=> :emb AS dist
            FROM claims c JOIN articles a ON a.id = c.article_id
            WHERE c.id <> CAST(:cid AS uuid) AND c.embedding IS NOT NULL
            ORDER BY c.embedding <=> :emb
            LIMIT 12
            """
        ),
        {"emb": emb, "cid": claim_id},
    )
    return [dict(r._mapping) for r in res.all()]


async def outlet_track_records() -> dict[str, dict]:
    """Historical support/dispute counts per outlet from already-verdicted claims.

    The band vocabulary comes from the engine itself (SUPPORTED_BANDS /
    DISPUTED_BANDS) — the previous hard-coded names ('LEAN_SUPPORTED',
    'LEAN_DISPUTED') no longer existed, so every outlet silently scored 0/0
    and the track-record signal never left its Laplace prior.
    """
    stmt = (
        text(
            """
            SELECT a.domain AS outlet,
                   COUNT(*) FILTER (WHERE c.verdict IN :supported) AS supported,
                   COUNT(*) FILTER (WHERE c.verdict IN :disputed) AS disputed
            FROM claims c JOIN articles a ON a.id = c.article_id
            WHERE c.verdict IS NOT NULL
            GROUP BY a.domain
            """
        )
        .bindparams(
            bindparam("supported", expanding=True),
            bindparam("disputed", expanding=True),
        )
    )
    async with async_session_maker() as db:
        rows = (
            await db.execute(
                stmt,
                {
                    "supported": list(SUPPORTED_BANDS),
                    "disputed": list(DISPUTED_BANDS),
                },
            )
        ).all()
    return {r[0]: {"supported": r[1], "disputed": r[2]} for r in rows}


async def score_claim(db, claim: dict, track: dict) -> dict | None:
    emb = claim["embedding"]
    nbrs = await neighbors_for(db, claim["id"], emb)

    lo, hi = near_window()
    near = [n for n in nbrs if lo <= (1 - float(n["dist"])) <= hi]

    # NLI stance on up to 3 nearest cross-outlet neighbors
    checked = []
    own_domain = claim["outlet"]
    for nb in near[:3]:
        if nb["domain"] == own_domain:
            continue
        stance = await nli_stance(claim["claim_text"], nb["claim_text"])
        checked.append({**nb, "sim": round(1 - float(nb["dist"]), 3), "nli": stance})

    # neighbors without explicit NLI stance count as neutral proximity;
    # NLI-checked ones carry their stance
    pool = [
        {**n, "nli": next((c["nli"] for c in checked if c["id"] == n["id"]), None)}
        for n in near
    ] or checked
    corr_sig, contra_sig = VerdictEngine.corroboration_signal(pool, own_domain)
    lang_sig = VerdictEngine.linguistic_signal(claim["claim_text"])
    ent_sig = VerdictEngine.entity_signal(claim["entities"] or [])
    track_sig = VerdictEngine.track_record_signal(track.get(own_domain))

    result = VerdictEngine.combine([corr_sig, contra_sig, track_sig, ent_sig, lang_sig])

    # enrich evidence with the NLI-checked neighbor list
    result.evidence["checked_neighbors"] = [
        {
            "domain": n["domain"],
            "similarity": n["sim"],
            "stance": n["nli"],
            "claim": n["claim_text"][:200],
        }
        for n in checked
    ]
    return {
        "probability": result.probability,
        "band": result.band,
        "rationale": result.rationale,
        "evidence": json.dumps(result.evidence),
    }


async def persist(db, claim_id: str, v: dict) -> None:
    await db.execute(
        text(
            """
            UPDATE claims SET verdict = CAST(:band AS text),
                              verdict_probability = :p,
                              verdict_rationale = :r,
                              verdict_evidence = CAST(:e AS jsonb)
            WHERE id = CAST(:cid AS uuid)
            """
        ),
        {"band": v["band"], "p": v["probability"], "r": v["rationale"], "e": v["evidence"], "cid": claim_id},
    )


async def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 100

    claims = await load_claims(limit)
    print(f"scoring {len(claims)} unscored claims …")

    done = 0
    # two passes: first pass seeds track records with initial scoring,
    # second pass refines using those priors.
    for pass_no in (1, 2):
        track = await outlet_track_records()
        async with async_session_maker() as db:
            for i, claim in enumerate(claims):
                v = await score_claim(db, claim, track)
                if v is None:
                    continue
                await persist(db, claim["id"], v)
                done += 1
                if done % 10 == 0:
                    await db.commit()
                    print(f"  pass {pass_no}: {done} scored", flush=True)
            await db.commit()

    # final distribution
    async with async_session_maker() as db:
        rows = (
            await db.execute(
                text("SELECT verdict, COUNT(*) FROM claims GROUP BY verdict ORDER BY 2 DESC")
            )
        ).all()
    print("\n=== VERDICT DISTRIBUTION ===")
    for r in rows:
        print(f"  {r[0]}: {r[1]}")
    print(f"\ntotal scored this run: {done}")


if __name__ == "__main__":
    asyncio.run(main())
