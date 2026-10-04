import asyncio
import logging
from collections.abc import Sequence
from typing import Any, NamedTuple

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.claim import Claim
from app.models.evolution import ClaimClusterAssignment, ClaimClusterRun

logger = logging.getLogger(__name__)
CLUSTERING_ALGORITHM_VERSION = "gmee-bertopic-v2"


class _ClusterResult(NamedTuple):
    topics: list[int]
    labels: dict[int, str]
    keywords: dict[int, list[str]]


def _fit_topics(
    texts: list[str], embeddings: list[object], params: dict[str, Any]
) -> _ClusterResult:
    # UMAP cannot fit a tiny corpus; these are explicit noise assignments, not
    # guessed topics. Imports/model fitting also stay off the event loop.
    if len(texts) < max(3, params["min_topic_size"]):
        return _ClusterResult([-1] * len(texts), {}, {})
    try:
        from bertopic import BERTopic
        from umap import UMAP
    except ImportError:
        logger.error("BERTopic or UMAP not installed")
        raise
    umap_model = UMAP(
        n_neighbors=params["umap_n_neighbors"],
        n_components=params["umap_n_components"],
        min_dist=params["umap_min_dist"],
        metric=params["umap_metric"],
        random_state=params["random_state"],
    )
    topic_model = BERTopic(
        umap_model=umap_model,
        min_topic_size=params["min_topic_size"],
        calculate_probabilities=False,
    )
    topics, _ = topic_model.fit_transform(
        documents=texts,
        embeddings=np.asarray(embeddings, dtype=np.float32),
    )
    info = topic_model.get_topic_info()
    labels, keywords = {}, {}
    for _, row in info.iterrows():
        topic_id = int(row["Topic"])
        if topic_id != -1:
            labels[topic_id] = str(row["Name"])
            keywords[topic_id] = list(row["Representation"])
    return _ClusterResult([int(t) for t in topics], labels, keywords)


class ClusterService:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def run_clustering(
        self, db: AsyncSession, claims: Sequence[Claim]
    ) -> ClaimClusterRun:
        embedded = [c for c in claims if c.embedding is not None]
        params = {
            "algorithm_version": CLUSTERING_ALGORITHM_VERSION,
            "min_topic_size": self.settings.BERTOPIC_MIN_TOPIC_SIZE,
            "random_state": 42,
            "umap_n_neighbors": max(2, min(15, len(embedded) - 1)),
            "umap_n_components": max(1, min(5, len(embedded) - 2)),
            "umap_min_dist": 0.0,
            "umap_metric": "cosine",
            "calculate_probabilities": False,
            "embedding_source": "provided_claim_embeddings",
            "embedding_model": getattr(
                self.settings, "EMBEDDING_MODEL", "all-mpnet-base-v2"
            ),
            "input_claim_count": len(claims),
            "excluded_missing_embeddings": len(claims) - len(embedded),
            "corpus_count_basis": "embedded_claims",
        }
        result = await asyncio.to_thread(
            _fit_topics,
            [c.claim_text for c in embedded],
            [c.embedding for c in embedded],
            params,
        )
        run = ClaimClusterRun(claims_in_corpus=len(embedded), algorithm_params=params)
        db.add(run)
        await db.flush()
        assignments = [
            ClaimClusterAssignment(
                claim_id=claim.id,
                cluster_run_id=run.id,
                topic_id=topic_id,
                topic_label=result.labels.get(topic_id),
                topic_keywords={"keywords": result.keywords[topic_id]}
                if topic_id in result.keywords
                else None,
            )
            for claim, topic_id in zip(embedded, result.topics, strict=True)
        ]
        db.add_all(assignments)
        await db.flush()
        logger.info(
            "Clustering complete: %d embedded claims, %d topics",
            len(embedded),
            len(result.labels),
        )
        return run
