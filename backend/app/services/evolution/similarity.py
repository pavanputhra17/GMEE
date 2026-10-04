"""Bounded-memory cosine candidate search over supplied embeddings.

Exact scores are scanned in blocks, retaining at most K neighbors per query.
This avoids an N x N Gram matrix; arithmetic can still be quadratic in N.
Ties favor the lower input index, so callers should supply a stable ordering.
"""

import heapq
from collections.abc import Sequence

import numpy as np

SIMILARITY_BLOCK_SIZE = 256


def unit_matrix(embeddings: Sequence[object] | np.ndarray) -> np.ndarray:
    matrix = np.asarray(embeddings, dtype=np.float32)
    if matrix.ndim != 2:
        raise ValueError("embeddings must be a two-dimensional matrix")
    if not np.isfinite(matrix).all():
        raise ValueError("embeddings must contain finite values")
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    normalized: np.ndarray = matrix / np.maximum(norms, 1e-9)
    return normalized


def top_neighbors(
    unit: np.ndarray,
    query_index: int,
    *,
    limit: int,
    threshold: float,
    start: int = 0,
    stop: int | None = None,
    block_size: int = SIMILARITY_BLOCK_SIZE,
) -> list[tuple[int, float]]:
    """Return strongest qualifying neighbors without allocating a square matrix."""
    if limit < 1 or block_size < 1:
        raise ValueError("candidate limit and block size must be positive")
    stop = len(unit) if stop is None else min(stop, len(unit))
    heap: list[tuple[float, int]] = []
    for offset in range(start, stop, block_size):
        scores = np.matmul(
            unit[offset : min(offset + block_size, stop)], unit[query_index]
        )
        for relative in np.flatnonzero(scores >= threshold):
            index = offset + int(relative)
            if index == query_index:
                continue
            score = float(np.clip(scores[relative], -1.0, 1.0))
            candidate = (score, -index)
            if len(heap) < limit:
                heapq.heappush(heap, candidate)
            elif candidate > heap[0]:
                heapq.heapreplace(heap, candidate)
    return [(-index, score) for score, index in sorted(heap, reverse=True)]
