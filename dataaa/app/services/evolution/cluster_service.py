import logging
from collections.abc import Sequence

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.claim import Claim
from app.models.evolution import ClaimClusterAssignment, ClaimClusterRun

logger = logging.getLogger(__name__)


class ClusterService:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def run_clustering(self, db: AsyncSession, claims: Sequence[Claim]) -> ClaimClusterRun:
        # Import bertopic locally so we don't blow up if it's missing at app startup
        try:
            from bertopic import BERTopic
            from umap import UMAP
        except ImportError:
            logger.error("BERTopic or UMAP not installed")
            raise

        logger.info(f"Starting clustering on {len(claims)} claims.")

        texts = [c.claim_text for c in claims]
        embeddings = np.array([c.embedding for c in claims])

        # BERTopic parameters
        min_topic_size = self.settings.BERTOPIC_MIN_TOPIC_SIZE
        random_state = 42

        # Configure UMAP for reproducibility
        umap_model = UMAP(
            n_neighbors=15, 
            n_components=5, 
            min_dist=0.0, 
            metric='cosine', 
            random_state=random_state
        )

        topic_model = BERTopic(
            umap_model=umap_model, 
            min_topic_size=min_topic_size,
            calculate_probabilities=False
        )
        
        topics, _ = topic_model.fit_transform(documents=texts, embeddings=embeddings)
        topic_info = topic_model.get_topic_info()

        # Create Cluster Run
        run = ClaimClusterRun(
            claims_in_corpus=len(claims),
            algorithm_params={
                "min_topic_size": min_topic_size,
                "random_state": random_state,
                "umap_n_neighbors": 15,
                "umap_n_components": 5
            }
        )
        db.add(run)
        
        # Flush to get run.id
        await db.flush()

        # Create assignments
        assignments = []
        for i, claim in enumerate(claims):
            topic_id = topics[i]
            
            label = None
            keywords = None
            if topic_id != -1:
                # -1 is noise
                # topic_info has columns Topic, Count, Name, Representation, Representative_Docs
                row = topic_info[topic_info['Topic'] == topic_id]
                if not row.empty:
                    label = row.iloc[0]['Name']
                    keywords_list = row.iloc[0]['Representation']
                    keywords = {"keywords": keywords_list}

            assignments.append(ClaimClusterAssignment(
                claim_id=claim.id,
                cluster_run_id=run.id,
                topic_id=int(topic_id),
                topic_label=label,
                topic_keywords=keywords
            ))

        db.add_all(assignments)
        await db.flush()
        
        logger.info(f"Clustering complete. Created {len(topic_info) - (1 if -1 in topic_info['Topic'].values else 0)} clusters.")
        return run
