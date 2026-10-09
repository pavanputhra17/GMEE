"""Gold-standard claim-pair labeling API.

Design principle: ANNOTATOR BLINDING. `GET /eval/next` deliberately omits the
stored similarity score, bucket, engine verdicts and NLI stances — the
annotator judges only the two claim texts. Biased labeling is worse than no
labeling, and the blind is enforced by a test (tests/test_eval_api.py).
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()

VALID_LABELS = ("SAME_STORY", "EVOLVED", "DISTINCT")

_PAIR_SQL = """
SELECT p.id::text AS id, p.bucket AS bucket,
       ta.claim_text AS text_a, da.domain AS domain_a,
       tb.claim_text AS text_b, db.domain AS domain_b
FROM eval_pairs p
JOIN claims ta ON ta.id = p.claim_a_id
JOIN articles da ON da.id = ta.article_id
JOIN claims tb ON tb.id = p.claim_b_id
JOIN articles db ON db.id = tb.article_id
"""


def _blinded(row: Any) -> dict[str, Any]:
    """Strip every cue except the raw claim texts + outlet domains."""
    return {
        "pair_id": row.id,
        "a": {"text": row.text_a, "domain": row.domain_a},
        "b": {"text": row.text_b, "domain": row.domain_b},
    }


def _per_annotator(rows: Any) -> dict[str, Any]:
    """Aggregate (annotator, label, n) rows into per-annotator tallies.

    An annotator normally holds more than one label, so the labels must be
    nested — flattening to a single ``{label, count}`` silently discarded every
    vote but the last one returned by the GROUP BY.
    """
    out: dict[str, Any] = {}
    for annotator, label, n in rows:
        entry = out.setdefault(annotator, {"labels": {}, "total": 0})
        entry["labels"][label] = entry["labels"].get(label, 0) + n
        entry["total"] += n
    return out


@router.get("/next")
async def next_pair(annotator: str = "anon", limit_scan: int = 50) -> dict[str, Any]:
    """Next pair this annotator hasn't labeled yet — blinded."""
    from sqlalchemy import text

    from app.db.postgres import async_session_maker

    if not annotator or len(annotator) > 64:
        raise HTTPException(status_code=400, detail="annotator must be 1-64 chars")

    async with async_session_maker() as db:
        # lowest ids first for a stable, complete coverage order
        rows = (
            await db.execute(
                text(
                    _PAIR_SQL
                    + """
                    WHERE NOT EXISTS (
                        SELECT 1 FROM eval_pair_labels l
                        WHERE l.pair_id = p.id AND l.annotator = :ann
                    )
                    ORDER BY p.sampled_at ASC, p.id ASC
                    LIMIT :scan
                    """
                ),
                {"ann": annotator, "scan": max(1, min(limit_scan, 200))},
            )
        ).all()
        rows = list(rows)  # `.all()` returns a Sequence; sorting needs a list

        # prefer cross-outlet pairs first: they carry the most information
        rows.sort(key=lambda r: (r.domain_a == r.domain_b,))

    if not rows:
        return {"done": True, "pair": None}
    return {"done": False, "pair": _blinded(rows[0])}


class EvalLabelBody(BaseModel):
    pair_id: str = Field(min_length=32, max_length=36)
    annotator: str = Field(min_length=1, max_length=64)
    label: str = Field(pattern="^(SAME_STORY|EVOLVED|DISTINCT)$")


@router.post("/label", status_code=201)
async def label_pair(body: EvalLabelBody) -> dict[str, Any]:
    """Record (or update) this annotator's label for a pair."""
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.db.postgres import async_session_maker
    from app.models.eval import EvalPairLabel

    try:
        pid = uuid.UUID(body.pair_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="pair_id must be a UUID") from exc

    async with async_session_maker() as db:
        exists = (
            await db.execute(
                text("SELECT 1 FROM eval_pairs WHERE id = CAST(:pid AS uuid)"),
                {"pid": body.pair_id},
            )
        ).first()
        if exists is None:
            raise HTTPException(status_code=404, detail="pair not found")

        stmt = pg_insert(EvalPairLabel).values(
            pair_id=pid,
            annotator=body.annotator,
            label=body.label,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_eval_label_pair_annotator",
            set_={"label": stmt.excluded.label, "created_at": datetime.now(UTC)},
        )
        await db.execute(stmt)
        await db.commit()

    return {"status": "recorded", "pair_id": body.pair_id, "label": body.label}


@router.get("/report")
async def eval_report() -> dict[str, Any]:
    """Publication metrics over consensus labels.

    AUROC with bootstrap CI, best-F1, F1 at the engine operating point, Brier
    score, expected calibration error, reliability bins, a threshold sweep and
    pairwise McNemar significance — plus an explicit warning while the sample is
    too small to conclude anything. Pure metrics live in
    `services/eval/metrics.py`; assembly in `services/eval/report.py`.
    """
    from app.db.postgres import async_session_maker
    from app.services.eval.report import build_report, collect_labeled_pairs

    async with async_session_maker() as db:
        rows = await collect_labeled_pairs(db)
    return build_report(rows)


@router.get("/progress")
async def progress() -> dict[str, Any]:
    """Labeling coverage + inter-annotator agreement (Cohen's kappa)."""
    from collections import defaultdict

    from sqlalchemy import text

    from app.db.postgres import async_session_maker
    from app.services.eval.metrics import cohen_kappa

    async with async_session_maker() as db:
        by_bucket = (
            await db.execute(
                text(
                    """
                    SELECT p.bucket,
                           count(DISTINCT p.id) AS pairs,
                           count(DISTINCT l.pair_id) AS labeled
                    FROM eval_pairs p
                    LEFT JOIN eval_pair_labels l ON l.pair_id = p.id
                    GROUP BY p.bucket ORDER BY p.bucket
                    """
                )
            )
        ).all()
        per_annotator = (
            await db.execute(
                text(
                    """
                    SELECT annotator, label, count(*) AS n
                    FROM eval_pair_labels GROUP BY 1, 2 ORDER BY 1, 2
                    """
                )
            )
        ).all()
        label_matrix = (
            await db.execute(
                text(
                    """
                    SELECT pair_id::text AS pid, annotator, label
                    FROM eval_pair_labels ORDER BY pair_id, annotator
                    """
                )
            )
        ).all()

    # kappa between every annotator pair over their shared pairs
    by_pair: dict[str, dict[str, str]] = defaultdict(dict)
    for r in label_matrix:
        by_pair[r[0]][r[1]] = r[2]
    annotators = sorted({r[1] for r in label_matrix})
    kappas = []
    for i, a1 in enumerate(annotators):
        for a2 in annotators[i + 1:]:
            shared = [
                (m[a1], m[a2])
                for m in by_pair.values()
                if a1 in m and a2 in m
            ]
            if len(shared) >= 5:  # below this kappa is meaningless
                kappas.append({
                    "annotators": [a1, a2],
                    "pairs": len(shared),
                    "kappa": round(
                        cohen_kappa([s[0] for s in shared], [s[1] for s in shared]) or 0.0, 4
                    ),
                })

    total_pairs = sum(r[1] for r in by_bucket)
    labeled_pairs = sum(r[2] for r in by_bucket)
    return {
        "total_pairs": total_pairs,
        "labeled_votes": sum(r[2] for r in per_annotator),
        "labeled_pairs_distinct": len({r[0] for r in label_matrix}),
        "by_bucket": [
            {"bucket": r[0], "pairs": r[1], "labeled": r[2]} for r in by_bucket
        ],
        "per_annotator": _per_annotator(per_annotator),
        "inter_annotator": kappas,
        "complete": total_pairs > 0 and labeled_pairs >= total_pairs,
    }