"""Claim propagation sandbox (first-order branching approximation).

Given the article SIMILAR graph and a hub article, estimate how far a story
would spread if each cross-outlet link independently transmits with
probability p. This is intentionally a simple, transparent model — it exists
so journalists can reason about "what if this mutates and spreads?" without
pretending to be an epidemic simulator.

Pure functions only; the endpoint in api/v1/graph.py wires real Neo4j edges.
"""


from typing import TypedDict


class CascadeLevel(TypedDict):
    level: int
    reached: int
    expected: float


class SimulateCascadeResult(TypedDict):
    root: str
    p: float
    max_depth: int
    levels: list[CascadeLevel]
    deterministic_reach: int
    total_expected_reach: float
    mean_fanout: float
    r_effective: float
    model: str


def _clamp(p: float) -> float:
    return max(0.05, min(0.95, p))


def simulate_cascade(
    adjacency: dict[str, list[str]],
    root: str,
    p: float,
    max_depth: int = 3,
) -> SimulateCascadeResult:
    """Expected-reach cascade from `root`.

    - `reached` per level: nodes deterministically reachable within depth
      (graph structure, independent of p).
    - `expected`: reached * p**level — each hop independently transmits with
      probability p, so a node at depth L is infected with probability p**L.
    - `r_effective`: p * mean out-degree — >1 means the story tends to escape
      the initial cluster.
    """
    p = _clamp(p)
    max_depth = max(1, min(max_depth, 6))

    visited = {root}
    frontier = [root] if root in adjacency else []
    levels: list[CascadeLevel] = []
    total = 1.0  # the root itself

    for level in range(1, max_depth + 1):
        if not frontier:
            break
        neighbours = [
            n for f in frontier for n in adjacency.get(f, []) if n not in visited
        ]
        new = list(dict.fromkeys(neighbours))
        expected = len(new) * (p ** level)
        levels.append({"level": level, "reached": len(new), "expected": round(expected, 2)})
        visited.update(new)
        frontier = new
        total += expected

    fanouts = [len(v) for v in adjacency.values()]
    mean_fanout = (sum(fanouts) / len(fanouts)) if fanouts else 0.0

    return {
        "root": root,
        "p": p,
        "max_depth": max_depth,
        "levels": levels,
        "deterministic_reach": len(visited),
        "total_expected_reach": round(total, 2),
        "mean_fanout": round(mean_fanout, 3),
        "r_effective": round(p * mean_fanout, 3),
        "model": "first-order branching: P(node at depth L infected) = p^L",
    }