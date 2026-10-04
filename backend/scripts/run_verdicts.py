"""Persist evidence-gated, uncalibrated verdict scores for corpus claims.

Usage: python scripts/run_verdicts.py [limit] [--rescore] [--outlet-priors FILE]

Only unscored records are updated by default, including at write time.
--rescore is an explicit opt-in to overwriting stored verdicts; nothing is
rescored automatically after an engine change. There is one scoring pass,
with neutral outlet priors unless separately supplied independent counts and
provenance are disclosed. The engine's own verdicts are never reliability data.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import async_session_maker
from app.services.verdict.engine import (
    METHOD_VERSION,
    SCORE_KIND,
    NLIUnavailableError,
    VerdictEngine,
    canonical_domain,
    near_window,
)
from app.services.verdict.evidence import (
    CORPUS_WARNING,
    MAX_CANDIDATES,
    ClaimCheckResult,
    EmbeddingUnavailableError,
    EvidenceCandidate,
    check_claim_with_embedding,
)

OutletPriors = dict[str, dict[str, Any]]
EVIDENCE_LIMIT = 6


async def load_claims(limit: int, rescore: bool = False) -> list[dict[str, Any]]:
    predicate = "TRUE" if rescore else "c.verdict IS NULL"
    async with async_session_maker() as db:
        rows = (
            (
                await db.execute(
                    text(f"""
            SELECT c.id::text AS id, c.article_id::text AS article_id,
                   c.claim_text, c.embedding, c.extracted_at,
                   a.domain AS outlet, a.published_at, a.collected_at,
                   a.canonical_article_id::text AS canonical_article_id,
                   a.content_hash,
                   COALESCE(
                       (SELECT json_agg(json_build_object('entity_type', ce.entity_type))
                        FROM claim_entities ce WHERE ce.claim_id = c.id),
                       '[]'::json) AS entities
            FROM claims c JOIN articles a ON a.id = c.article_id
            WHERE {predicate}
            ORDER BY c.confidence DESC NULLS LAST, c.id
            LIMIT :lim
        """),
                    {"lim": limit},
                )
            )
            .mappings()
            .all()
        )
    return [dict(row) for row in rows]


def load_outlet_priors(path: Path | None = None) -> OutletPriors:
    """Load caller-attested independent counts; no query of engine-labeled history.

    Format: {domain: {supported: int, disputed: int,
                      independently_validated: true, provenance: string}}.
    GMEE cannot audit the supplier's independence assertion.
    """
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError("Outlet priors must be a JSON object keyed by domain")
    priors: OutletPriors = {}
    for domain, stats in data.items():
        normalized = canonical_domain(domain) if isinstance(domain, str) else None
        if not normalized or normalized in priors or not isinstance(stats, dict):
            raise ValueError(
                "Outlet priors require distinct normalized domains and objects"
            )
        provenance = stats.get("provenance")
        if (
            stats.get("independently_validated") is not True
            or not isinstance(provenance, str)
            or not provenance.strip()
            or any(
                type(stats.get(k)) is not int or stats[k] < 0
                for k in ("supported", "disputed")
            )
        ):
            raise ValueError(
                "Each outlet prior needs nonnegative integer supported/disputed "
                "counts, independently_validated=true and nonempty provenance; "
                "engine verdict history is not acceptable independent data"
            )
        priors[normalized] = dict(stats)
    return priors


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Unsupported evidence value: {type(value).__name__}")


async def score_claim(
    db: AsyncSession,
    claim: Mapping[str, Any],
    track: Mapping[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    observed = datetime.now(UTC)
    own_domain = canonical_domain(claim.get("outlet"))
    origin = EvidenceCandidate(
        claim_id=str(claim["id"]),
        article_id=str(claim["article_id"]),
        text=str(claim["claim_text"]),
        url="",
        title="",
        domain=own_domain,
        published_at=None,
        similarity=1.0,
        canonical_article_id=claim.get("canonical_article_id"),
        content_hash=claim.get("content_hash"),
    )
    check: ClaimCheckResult
    if claim.get("embedding") is None:
        check = {
            "claim_text": origin.text,
            "assessment": "INSUFFICIENT_EVIDENCE",
            "evidence": [],
            "warnings": [
                CORPUS_WARNING,
                "No stored claim embedding; retrieval abstained.",
            ],
            "score_kind": SCORE_KIND,
            "observed_at": observed,
            "method_version": METHOD_VERSION,
        }
    else:
        check = await check_claim_with_embedding(
            db,
            origin.text,
            claim["embedding"],
            limit=EVIDENCE_LIMIT,
            observed_at=observed,
            exclude_claim_id=origin.claim_id,
            own_domain=own_domain,
            own_origin=origin,
        )
    pool = [dict(item) for item in check["evidence"]]
    corr_sig, contra_sig = VerdictEngine.corroboration_signal(pool, own_domain)
    lang_sig = VerdictEngine.linguistic_signal(origin.text)
    entities = claim.get("entities") or []
    if isinstance(entities, str):
        entities = json.loads(entities)
    ent_sig = VerdictEngine.entity_signal(entities)
    track_sig = VerdictEngine.track_record_signal((track or {}).get(own_domain or ""))
    result = VerdictEngine.combine([corr_sig, contra_sig, track_sig, ent_sig, lang_sig])
    result.evidence.update(
        {
            "checked_neighbors": check["evidence"],
            "corpus_assessment": check["assessment"],
            "observed_at": check["observed_at"],
            "coverage": CORPUS_WARNING,
            "source_prior_disclosure": track_sig.detail["disclosure"],
            "retrieval": {
                "max_candidates": MAX_CANDIDATES,
                "evidence_limit": EVIDENCE_LIMIT,
                "min_similarity": near_window()[0],
                "similarity_role": "retrieval_only",
            },
            "warnings": list(
                dict.fromkeys([*result.evidence["warnings"], *check["warnings"]])
            ),
        }
    )
    return {
        "probability": result.probability,
        "band": result.band,
        "rationale": result.rationale,
        "evidence": json.dumps(result.evidence, default=_json_default),
        "score_kind": SCORE_KIND,
        "method_version": METHOD_VERSION,
    }


async def persist(
    db: AsyncSession,
    claim_id: str,
    verdict: Mapping[str, Any],
    *,
    rescore: bool = False,
) -> bool:
    guard = "" if rescore else "AND verdict IS NULL"
    result = await db.execute(
        text(f"""
        UPDATE claims SET verdict = CAST(:band AS text),
                          verdict_probability = :score,
                          verdict_rationale = :rationale,
                          verdict_evidence = CAST(:evidence AS jsonb)
        WHERE id = CAST(:claim_id AS uuid) {guard}
        RETURNING id
    """),
        {
            "band": verdict["band"],
            "score": verdict["probability"],
            "rationale": verdict["rationale"],
            "evidence": verdict["evidence"],
            "claim_id": claim_id,
        },
    )
    return result.scalar_one_or_none() is not None


def _positive_limit(value: str) -> int:
    try:
        limit = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("limit must be a positive integer") from exc
    if limit < 1:
        raise argparse.ArgumentTypeError("limit must be a positive integer")
    return limit


def argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("limit", nargs="?", type=_positive_limit, default=100)
    parser.add_argument(
        "--rescore", action="store_true", help="Explicitly overwrite stored verdicts"
    )
    parser.add_argument(
        "--outlet-priors",
        type=Path,
        help="Independent counts/provenance JSON; default neutral",
    )
    return parser


async def main(argv: Sequence[str] | None = None) -> None:
    parser = argument_parser()
    args = parser.parse_args(argv)
    try:
        priors = load_outlet_priors(args.outlet_priors)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    claims = await load_claims(args.limit, rescore=args.rescore)
    mode = "explicit rescore mode" if args.rescore else "unscored claims only"
    print(f"Scoring {len(claims)} claims ({mode}); scores are uncalibrated heuristics.")
    print(
        "Source priors: "
        + (
            "caller-supplied independent counts; provenance is disclosed, not audited."
            if priors
            else "neutral; no independent outlet data supplied."
        )
    )
    done = 0
    async with async_session_maker() as db:
        try:
            for claim in claims:
                verdict = await score_claim(db, claim, priors)
                if await persist(db, str(claim["id"]), verdict, rescore=args.rescore):
                    done += 1
                if done and done % 10 == 0:
                    await db.commit()
                    print(f"  {done} scored", flush=True)
            await db.commit()
        except (EmbeddingUnavailableError, NLIUnavailableError) as exc:
            await db.rollback()
            print(
                f"Scoring stopped; pending writes rolled back. {exc}", file=sys.stderr
            )
            raise SystemExit(1) from exc
        except SQLAlchemyError as exc:
            await db.rollback()
            print(
                "Verdict storage failed; pending writes rolled back. Check PostgreSQL/pgvector.",
                file=sys.stderr,
            )
            raise SystemExit(1) from exc
    async with async_session_maker() as db:
        rows = (
            await db.execute(
                text(
                    "SELECT verdict, COUNT(*) FROM claims GROUP BY verdict ORDER BY 2 DESC"
                )
            )
        ).all()
    print("\n=== STORED VERDICT DISTRIBUTION (MAY INCLUDE LEGACY SCORES) ===")
    for row in rows:
        print(f"  {row[0]}: {row[1]}")
    print(f"\nTotal newly persisted this run: {done}")


if __name__ == "__main__":
    asyncio.run(main())
