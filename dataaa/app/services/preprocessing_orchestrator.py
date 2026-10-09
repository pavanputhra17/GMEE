import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.article import Article, ProcessingStatusEnum
from app.services.nlp_orchestrator import NLPOrchestrator
from app.services.preprocessing.cleaner import clean_text
from app.services.preprocessing.language_detector import detect_language
from app.services.preprocessing.metadata_extractor import (
    compute_word_count,
    extract_domain,
    extract_or_repair_published_at,
)
from app.services.preprocessing.near_duplicate_detector import NearDuplicateDetector

logger = logging.getLogger(__name__)


@dataclass
class PreprocessingSummary:
    total_processed: int = 0
    status_counts: dict[str, int] = field(default_factory=lambda: {
        ProcessingStatusEnum.processed.value: 0,
        ProcessingStatusEnum.skipped_non_english.value: 0,
        ProcessingStatusEnum.failed.value: 0,
    })
    errors: list[str] = field(default_factory=list)


class PreprocessingOrchestrator:
    BATCH_SIZE = 100

    async def run_preprocessing_cycle(self, db: AsyncSession) -> PreprocessingSummary:
        logger.info("Starting preprocessing cycle")
        summary = PreprocessingSummary()

        dup_detector = NearDuplicateDetector(db)
        await dup_detector.initialize()
        
        while True:
            # 1. Select a batch of raw articles
            # We select them one batch at a time to avoid loading a huge backlog into memory
            stmt = select(Article).where(
                Article.processing_status == ProcessingStatusEnum.raw
            ).limit(self.BATCH_SIZE)
            
            result = await db.execute(stmt)
            articles: Sequence[Article] = result.scalars().all()
            
            if not articles:
                break
                
            for article in articles:
                try:
                    # 2. Claim it atomically in our transaction context
                    article.processing_status = ProcessingStatusEnum.processing
                    await db.commit()
                    await db.refresh(article)
                except Exception as e:
                    logger.warning(f"Could not claim article {article.id} for processing: {e}")
                    await db.rollback()
                    continue
                
                try:
                    # 3. Clean text
                    article.cleaned_content = clean_text(article.content)
                    
                    # 4. Language detection
                    lang = detect_language(article.cleaned_content)
                    article.language = lang
                    
                    if lang and lang != 'en':
                        article.processing_status = ProcessingStatusEnum.skipped_non_english
                        article.processed_at = datetime.now(UTC)
                        await db.commit()
                        summary.status_counts[ProcessingStatusEnum.skipped_non_english.value] += 1
                        summary.total_processed += 1
                        continue
                        
                    # 5. Near-duplicate detection (only if English or undetermined, but we skip if not english above)
                    if article.cleaned_content:
                        canonical_id = dup_detector.find_and_insert(article)
                        if canonical_id:
                            article.canonical_article_id = canonical_id
                            
                    # 6. Metadata extraction
                    article.domain = extract_domain(article.url)
                    article.word_count = compute_word_count(article.cleaned_content)
                    article.published_at = extract_or_repair_published_at(article.published_at, article.raw_metadata)
                    
                    # Mark processed
                    article.processing_status = ProcessingStatusEnum.processed
                    article.processed_at = datetime.now(UTC)
                    await db.commit()
                    
                    summary.status_counts[ProcessingStatusEnum.processed.value] += 1
                    summary.total_processed += 1
                    
                except Exception as e:
                    article_id = article.id
                    logger.exception(f"Error preprocessing article {article_id}")
                    # Re-fetch article from db to discard uncommitted changes before marking failed
                    await db.rollback()
                    
                    # Now set it to failed
                    try:
                        # Fetch it again to cleanly update status
                        failed_stmt = select(Article).where(Article.id == article_id)
                        failed_res = await db.execute(failed_stmt)
                        failed_article = failed_res.scalar_one_or_none()
                        if failed_article:
                            failed_article.processing_status = ProcessingStatusEnum.failed
                            failed_article.processed_at = datetime.now(UTC)
                            await db.commit()
                    except Exception as fallback_e:
                        logger.error(f"Failed to mark article {article_id} as failed: {fallback_e}")
                        await db.rollback()
                        
                    summary.status_counts[ProcessingStatusEnum.failed.value] += 1
                    summary.errors.append(f"Article {article_id}: {e}")
                    summary.total_processed += 1

        logger.info(f"Preprocessing cycle completed. Processed: {summary.total_processed}")
        
        # Trigger NLP pipeline
        try:
            logger.info("Triggering NLP cycle.")
            nlp_orchestrator = NLPOrchestrator()
            nlp_summary = await nlp_orchestrator.run_nlp_cycle(db)
            logger.info(f"Triggered NLP cycle. Total Processed: {nlp_summary.total_processed}")
        except Exception as e:
            logger.error(f"Error triggering NLP cycle: {e}")
            
        return summary
