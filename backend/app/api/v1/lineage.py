"""Bounded inspection of ACTUAL persisted EVOLVED_FROM edges.

Versions may be time-sorted for presentation, but siblings are never paired as
invented transmissions. Each diff follows a stored parent -> child edge; the
stored relationship itself points child -> parent. Legacy edges without typed
evidence are explicitly labeled as re-analyzed, not historical observations.
"""

import html as htmllib
import json
import re
import uuid as uuidlib
from collections import defaultdict, deque
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from app.db.postgres import async_session_maker
from app.services.verdict.mutation_diff import diff_versions

router = APIRouter()
MAX_HOPS = 3
MAX_VERSIONS = 12
MAX_COMPONENT = 400
MAX_EDGE_ROWS = MAX_COMPONENT * 4


def _clean(v: Any, limit: int) -> str | None:
    if not v:
        return None
    s = htmllib.unescape(re.sub(r"<[^>]*>", " ", str(v)))
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit] or None


def _connected_versions(root: str, edges: list[dict[str, Any]]) -> list[str]:
    """Keep a connected, bounded slice instead of disconnected high-score nodes."""
    neighbors: dict[str, list[tuple[float, str]]] = defaultdict(list)
    for edge in edges:
        neighbors[edge["from"]].append((edge["score"], edge["to"]))
        neighbors[edge["to"]].append((edge["score"], edge["from"]))
    chosen, visited, frontier = [root], {root}, deque([root])
    while frontier and len(chosen) < MAX_VERSIONS:
        cid = frontier.popleft()
        for _, other in sorted(neighbors[cid], key=lambda item: (-item[0], item[1])):
            if other in visited:
                continue
            visited.add(other)
            chosen.append(other)
            frontier.append(other)
            if len(chosen) == MAX_VERSIONS:
                break
    return chosen


def _stored_analysis(value: Any) -> dict[str, Any] | None:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return None
    return (
        value
        if isinstance(value, dict) and isinstance(value.get("mutation_types"), list)
        else None
    )


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
    truncated = False
    async with async_session_maker() as db:
        for _ in range(MAX_HOPS):
            if not frontier:
                break
            binds: dict[str, Any] = {f"i{n}": x for n, x in enumerate(frontier)}
            binds["edge_lim"] = MAX_EDGE_ROWS + 1
            names = ",".join(f":i{n}" for n in range(len(frontier)))
            rows = (
                await db.execute(
                    text(f"""
                        SELECT r.from_claim_id::text AS src,
                               r.to_claim_id::text AS dst,
                               r.score, r.mutation_evidence,
                               r.id::text, r.created_at
                        FROM claim_relationships r
                        WHERE r.relationship_type = 'EVOLVED_FROM'
                          AND (r.from_claim_id::text IN ({names})
                               OR r.to_claim_id::text IN ({names}))
                        ORDER BY r.score DESC, r.from_claim_id, r.to_claim_id
                        LIMIT :edge_lim
                    """),
                    binds,
                )
            ).all()
            if len(rows) > MAX_EDGE_ROWS:
                truncated = True
            frontier = []
            for r in rows[:MAX_EDGE_ROWS]:
                src, dst = str(r[0]), str(r[1])
                new_ids = {src, dst} - seen
                if len(seen) + len(new_ids) > MAX_COMPONENT:
                    truncated = True
                    continue
                for sid in sorted(new_ids):
                    seen.add(sid)
                    frontier.append(sid)
                key = (src, dst)
                if key not in edge_keys:
                    edge_keys.add(key)
                    edges.append(
                        {
                            "from": src,
                            "to": dst,
                            "score": float(r[2]),
                            "mutation_evidence": r[3],
                            "id": str(r[4]),
                            "created_at": r[5].isoformat() if r[5] else None,
                        }
                    )
            if len(seen) == MAX_COMPONENT:
                truncated = True
                break
        if frontier:
            truncated = True
        if len(seen) == 1:
            raise HTTPException(
                status_code=404, detail="claim has no evolution lineage"
            )

        chosen = _connected_versions(root_s, edges)
        truncated = truncated or len(chosen) < len(seen)
        binds = {f"i{n}": x for n, x in enumerate(chosen)}
        names = ",".join(f":i{n}" for n in range(len(chosen)))
        vrows = (
            await db.execute(
                text(f"""
                    SELECT c.id::text, c.claim_text, a.domain, a.published_at,
                           a.title, c.article_id::text
                    FROM claims c JOIN articles a ON a.id = c.article_id
                    WHERE c.id::text IN ({names})
                    ORDER BY a.published_at ASC NULLS LAST, c.id
                """),
                binds,
            )
        ).all()

    versions = [
        {
            "id": str(r[0]),
            "text": _clean(r[1], 600) or "",
            "domain": _clean(r[2], 80),
            "published_at": r[3].isoformat() if r[3] else None,
            "article_title": _clean(r[4], 140),
            "article_id": str(r[5]),
        }
        for r in vrows
    ]
    raw = {str(r[0]): r for r in vrows}
    indexes = {version["id"]: i for i, version in enumerate(versions)}
    rendered_edges, diffs = [], []
    for edge in sorted(
        edges, key=lambda e: (indexes.get(e["from"], MAX_VERSIONS), e["to"], e["from"])
    ):
        child_id, parent_id = edge["from"], edge["to"]
        if child_id not in indexes or parent_id not in indexes:
            continue
        parent, child = raw[parent_id], raw[child_id]
        diff = diff_versions(
            parent[1] or "",
            child[1] or "",
            older_timestamp=parent[3],
            newer_timestamp=child[3],
        )
        stored = _stored_analysis(edge["mutation_evidence"])
        analysis = {
            **(stored if stored is not None else diff["analysis"]),
            "observed_propagation": False,
            "inference": "inferred_candidate_lineage",
        }
        source = "persisted" if stored is not None else "legacy_edge_reanalysis"
        rendered_edges.append(
            {
                "id": edge["id"],
                "from": child_id,
                "to": parent_id,
                "score": edge["score"],
                "created_at": edge["created_at"],
                "relationship_type": "EVOLVED_FROM",
                "parent_claim_id": parent_id,
                "child_claim_id": child_id,
                "analysis": analysis,
                "mutation_types": analysis["mutation_types"],
                "evidence_source": source,
                "observed_propagation": False,
            }
        )
        diffs.append(
            {
                **diff,
                "from_index": indexes[parent_id],
                "to_index": indexes[child_id],
                "from_id": parent_id,
                "to_id": child_id,
                "analysis": analysis,
                "evidence_source": source,
            }
        )
    return {
        "root": root_s,
        "versions": versions,
        "edges": rendered_edges,
        "diffs": diffs,
        "counts": {
            "versions": len(versions),
            "edges": len(rendered_edges),
            "component_claims": len(seen),
            "component_edges": len(edges),
        },
        "truncated": truncated,
        "observed_propagation": False,
    }
