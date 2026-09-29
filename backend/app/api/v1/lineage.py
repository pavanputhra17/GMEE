"""Claim lineage inspector: the EVOLVED_FROM component around one claim,
rendered as a time-ordered version chain with typed word-level diffs.

Deliberately a separate router from graph.py: it uses Postgres (claim
relationships) while graph.py is Neo4j-centred, and it needs its own
parameter-binding style (explicit per-id binds — asyncpg array binding of
uuid columns silently under-matched in testing).
"""

import html as htmllib
import re
import uuid as uuidlib
from itertools import pairwise
from typing import Any

__all__ = ["pairwise", "router"]

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from app.db.postgres import async_session_maker
from app.services.verdict.mutation_diff import diff_versions

router = APIRouter()

MAX_HOPS = 3
MAX_VERSIONS = 12
MAX_COMPONENT = 400


def _clean(v: Any, limit: int) -> str | None:
    if not v:
        return None
    s = htmllib.unescape(re.sub(r"<[^>]*>", " ", str(v)))
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit] or None


@router.get("/lineage/{claim_id}")
async def claim_lineage(claim_id: str) -> dict[str, Any]:
    try:
        root = uuidlib.UUID(claim_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="claim_id must be a UUID") from exc

    root_s = str(root)
    seen: set[str] = {root_s}
    frontier = [root_s]
    edges: list[dict[str, Any]] = []
    edge_keys: set[tuple[str, str]] = set()

    async with async_session_maker() as db:
        for _ in range(MAX_HOPS):
            if not frontier:
                break
            binds = {f"i{n}": x for n, x in enumerate(frontier)}
            names = ",".join(f":i{n}" for n in range(len(frontier)))
            rows = (
                await db.execute(
                    text(
                        f"""
                        SELECT r.from_claim_id::text AS src,
                               r.to_claim_id::text AS dst,
                               r.score AS score
                        FROM claim_relationships r
                        WHERE r.relationship_type = 'EVOLVED_FROM'
                          AND (r.from_claim_id::text IN ({names})
                               OR r.to_claim_id::text IN ({names}))
                        """
                    ),
                    binds,
                )
            ).all()
            frontier = []
            for r in rows:
                key = (r[0], r[1])
                if key not in edge_keys:
                    edge_keys.add(key)
                    edges.append({"from": r[0], "to": r[1], "score": float(r[2])})
                for sid in (r[0], r[1]):
                    if sid not in seen:
                        seen.add(sid)
                        frontier.append(sid)
            if len(seen) >= MAX_COMPONENT:
                break

        if len(seen) == 1:
            raise HTTPException(status_code=404, detail="claim has no evolution lineage")

        # Cap the rendered chain: root + strongest-linked claims, then sorted
        # by publish time. Raw component BFS would return a 700-claim hairball.
        link_score: dict[str, float] = {}
        for e in edges:
            for sid in (e["from"], e["to"]):
                if sid != root_s:
                    link_score[sid] = max(link_score.get(sid, 0.0), e["score"])
        ranked = sorted(link_score, key=lambda s: -link_score[s])[: MAX_VERSIONS - 1]
        chosen = [root_s] + [s for s in ranked if s != root_s]

        binds = {f"i{n}": x for n, x in enumerate(chosen)}
        names = ",".join(f":i{n}" for n in range(len(chosen)))
        vrows = (
            await db.execute(
                text(
                    f"""
                    SELECT c.id::text, c.claim_text, a.domain, a.published_at, a.title
                    FROM claims c JOIN articles a ON a.id = c.article_id
                    WHERE c.id::text IN ({names})
                    ORDER BY a.published_at ASC NULLS LAST
                    """
                ),
                binds,
            )
        ).all()

    versions = [
        {
            "id": r[0],
            "text": _clean(r[1], 600) or "",
            "domain": _clean(r[2], 80),
            "published_at": r[3].isoformat() if r[3] else None,
            "article_title": _clean(r[4], 140),
        }
        for r in vrows
    ]

    diffs = [
        {
            "from_index": i,
            "to_index": i + 1,
            "from_id": a["id"],
            "to_id": b["id"],
            **diff_versions(a["text"], b["text"]),
        }
        for i, (a, b) in enumerate(pairwise(versions))
    ]

    return {
        "root": root_s,
        "versions": versions,
        "edges": edges,
        "diffs": diffs,
        "counts": {
            "versions": len(versions),
            "edges": len(edges),
            "component_claims": len(seen),
        },
    }
