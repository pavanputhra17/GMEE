import logging
from collections.abc import Sequence
from datetime import UTC, datetime

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.article import Article, NLPStatusEnum, ProcessingStatusEnum
from app.models.claim import Claim, ClaimEntity
from app.services.nlp.embedding_service import EmbeddingService
from app.services.nlp.entity_extractor import EntityExtractor
from app.services.nlp.llm_client import AnthropicLLMClient, LLMClient

logger = logging.getLogger(__name__)


class NLPSummary(BaseModel):
    total_processed: int = 0
    status_counts: dict[str, int] = {
        NLPStatusEnum.completed.value: 0,
        NLPStatusEnum.skipped.value: 0,
        NLPStatusEnum.failed.value: 0,
    }
    claims_extracted: int = 0
    llm_calls_made: int = 0
    errors: list[str] = []


class NLPOrchestrator:
    def __init__(self, llm_client: LLMClient | None = None):
        self.settings = get_settings()
        self.max_articles = getattr(self.settings, 'NLP_MAX_ARTICLES_PER_CYCLE', 10)
        self.llm_client = llm_client or AnthropicLLMClient()

    async def run_nlp_cycle(self, db: AsyncSession) -> NLPSummary:
        summary = NLPSummary()
        
        # Select pending articles
        stmt = select(Article).where(
            Article.processing_status == ProcessingStatusEnum.processed,
            Article.nlp_status == NLPStatusEnum.pending
        ).limit(self.max_articles)
        
        result = await db.execute(stmt)
        articles: Sequence[Article] = result.scalars().all()
        
        if not articles:
            logger.info("No articles pending NLP processing.")
            return summary
            
        logger.info(f"Starting NLP cycle. Found {len(articles)} pending articles (cap: {self.max_articles}).")
        
        # Check if we should skip due to missing API key
        # AnthropicLLMClient sets self.client to None if key is missing
        if getattr(self.llm_client, 'client', True) is None:
            logger.warning("No LLM API key configured. Skipping NLP extraction for these articles.")
            for article in articles:
                article.nlp_status = NLPStatusEnum.skipped
                await db.commit()
                summary.status_counts[NLPStatusEnum.skipped.value] += 1
                summary.total_processed += 1
            return summary

        logger.info(f"Will make up to {len(articles)} LLM API calls this cycle.")
        
        for article in articles:
            try:
                # 1. Claim article for processing
                article.nlp_status = NLPStatusEnum.processing
                await db.commit()
                await db.refresh(article)
                
                # We need cleaned_content to extract claims
                text_to_process = article.cleaned_content or article.content
                if not text_to_process:
                    # Nothing to process
                    article.nlp_status = NLPStatusEnum.completed
                    await db.commit()
                    summary.status_counts[NLPStatusEnum.completed.value] += 1
                    summary.total_processed += 1
                    continue
                
                # 2. Call LLM to extract claims
                extracted_claims_data = await self.llm_client.extract_claims(text_to_process)
                summary.llm_calls_made += 1
                
                # 3. Process each claim
                new_claims = []
                for claim_data in extracted_claims_data:
                    # NER
                    entities = EntityExtractor.extract_entities(claim_data.claim_text)
                    # Embeddings
                    embedding = EmbeddingService.generate_embedding(claim_data.claim_text)
                    
                    claim_model = Claim(
                        article_id=article.id,
                        claim_text=claim_data.claim_text,
                        confidence=claim_data.confidence,
                        embedding=embedding,
                        extracted_at=datetime.now(UTC)
                    )
                    
                    # Add entities to claim
                    for ent in entities:
                        claim_model.entities.append(ClaimEntity(
                            entity_text=ent.entity_text,
                            entity_type=ent.entity_type,
                            start_char=ent.start_char,
                            end_char=ent.end_char
                        ))
                    
                    new_claims.append(claim_model)
                
                if new_claims:
                    db.add_all(new_claims)
                    summary.claims_extracted += len(new_claims)
                    
                # Mark as completed
                article.nlp_status = NLPStatusEnum.completed
                await db.commit()
                
                summary.status_counts[NLPStatusEnum.completed.value] += 1
                summary.total_processed += 1
                
            except Exception as e:
                article_id = article.id
                logger.exception(f"Error during NLP processing for article {article_id}: {e}")
                
                # Re-fetch and mark as failed
                await db.rollback()
                try:
                    failed_stmt = select(Article).where(Article.id == article_id)
                    failed_res = await db.execute(failed_stmt)
                    failed_article = failed_res.scalar_one_or_none()
                    if failed_article:
                        failed_article.nlp_status = NLPStatusEnum.failed
                        await db.commit()
                except Exception as fallback_e:
                    logger.error(f"Failed to mark article {article_id} as failed: {fallback_e}")
                    await db.rollback()
                    
                summary.status_counts[NLPStatusEnum.failed.value] += 1
                summary.errors.append(f"Article {article_id}: {e}")
                summary.total_processed += 1
                
        logger.info(f"NLP cycle completed. Processed {summary.total_processed} articles. Extracted {summary.claims_extracted} claims.")
        
        # Trigger evolution cycle (it has its own guards)
        try:
            from app.services.evolution.orchestrator import EvolutionOrchestrator
            evo_orch = EvolutionOrchestrator()
            evo_summary = await evo_orch.run_evolution_cycle(db)
            logger.info(f"Auto-triggered evolution cycle result: {evo_summary}")
        except Exception as e:
            logger.exception(f"Error during auto-triggered evolution cycle: {e}")

        return summary
