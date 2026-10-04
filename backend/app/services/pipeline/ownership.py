"""Atomic, expiring article ownership for the preprocessing and NLP stages.

Previously workers did read-then-write ("SELECT pending; then set
processing"), so two workers could both read the same row and both process
it, and a crash left rows stranded in ``processing`` forever.

Now:
  * ``claim_articles`` moves rows to ``processing`` with a single conditional
    UPDATE that re-checks the ready state, stamping a unique owner token and a
    lease expiry. ``FOR UPDATE SKIP LOCKED`` (PostgreSQL) lets concurrent
    workers pick disjoint batches; the conditional WHERE guarantees a row is
    won by at most one worker even without it.
  * ``finish_article`` writes results only ``WHERE claimed_by = owner`` (a
    fencing check). A worker whose lease expired and was recovered cannot
    overwrite the newer owner's results.
  * ``recover_expired`` returns expired claims to the queue (bounded batch),
    or marks them ``failed`` once ``PIPELINE_MAX_ATTEMPTS`` is reached.
"""

import enum
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.article import Article, NLPStatusEnum, ProcessingStatusEnum

logger = logging.getLogger(__name__)


class Stage(str, enum.Enum):
    preprocessing = "preprocessing"
    nlp = "nlp"


@dataclass(frozen=True)
class _StageSpec:
    column: Any
    ready: Any
    processing: Any
    failed: Any
    extra_ready_filter: tuple[Any, ...]


def _spec(stage: Stage) -> _StageSpec:
    if stage is Stage.preprocessing:
        return _StageSpec(
            column=Article.processing_status,
            ready=ProcessingStatusEnum.raw,
            processing=ProcessingStatusEnum.processing,
            failed=ProcessingStatusEnum.failed,
            extra_ready_filter=(),
        )
    return _StageSpec(
        column=Article.nlp_status,
        ready=NLPStatusEnum.pending,
        processing=NLPStatusEnum.processing,
        failed=NLPStatusEnum.failed,
        extra_ready_filter=(Article.processing_status == ProcessingStatusEnum.processed,),
    )


def new_owner_token(prefix: str) -> str:
    """Unique per worker run — never reused, so stale owners cannot match."""
    return f"{prefix}:{uuid.uuid4().hex[:20]}"[:64]


def sanitize_error(exc: BaseException, limit: int = 300) -> str:
    """Class name plus bounded single-line message; no tracebacks."""
    message = " ".join(str(exc).split())
    text = f"{type(exc).__name__}: {message}" if message else type(exc).__name__
    return text[:limit]


def _now() -> datetime:
    return datetime.now(UTC)


async def claim_articles(
    db: AsyncSession,
    stage: Stage,
    owner: str,
    limit: int,
    *,
    lease_seconds: int | None = None,
) -> list[uuid.UUID]:
    """Atomically claim up to ``limit`` ready articles. Returns claimed IDs."""
    if limit <= 0:
        return []
    spec = _spec(stage)
    lease = lease_seconds or get_settings().PIPELINE_LEASE_SECONDS
    now = _now()
    candidates = (
        select(Article.id)
        .where(spec.column == spec.ready, *spec.extra_ready_filter)
        .order_by(Article.collected_at, Article.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    stmt = (
        update(Article)
        .where(
            Article.id.in_(candidates.scalar_subquery()),
            spec.column == spec.ready,  # compare-and-set: still ready
        )
        .values(
            {
                spec.column: spec.processing,
                Article.claimed_by: owner,
                Article.claim_expires_at: now + timedelta(seconds=lease),
                Article.attempt_count: Article.attempt_count + 1,
            }
        )
        .returning(Article.id)
        .execution_options(synchronize_session="fetch")
    )
    result = await db.execute(stmt)
    ids = [row[0] for row in result.all()]
    await db.commit()
    return ids


async def finish_article(
    db: AsyncSession,
    stage: Stage,
    article_id: uuid.UUID,
    owner: str,
    *,
    status: Any,
    values: dict[str, Any] | None = None,
    error: str | None = None,
    commit: bool = True,
) -> bool:
    """Fenced terminal write. Returns False if ownership was lost."""
    spec = _spec(stage)
    payload: dict[Any, Any] = {
        spec.column: status,
        Article.claimed_by: None,
        Article.claim_expires_at: None,
        Article.last_error: error,
    }
    for key, value in (values or {}).items():
        payload[getattr(Article, key)] = value
    result = await db.execute(
        update(Article)
        .where(
            Article.id == article_id,
            Article.claimed_by == owner,
            spec.column == spec.processing,
        )
        .values(payload)
        .execution_options(synchronize_session="fetch")
    )
    won = (result.rowcount or 0) == 1  # type: ignore[attr-defined]
    if not won:
        logger.warning(
            "lost ownership of article %s for %s (lease expired/recovered); result discarded",
            article_id,
            stage.value,
        )
        await db.rollback()
        return False
    if commit:
        await db.commit()
    return True


async def extend_claims(
    db: AsyncSession, stage: Stage, owner: str, *, lease_seconds: int | None = None
) -> int:
    """Heartbeat: push the lease forward for rows this owner still holds."""
    spec = _spec(stage)
    lease = lease_seconds or get_settings().PIPELINE_LEASE_SECONDS
    result = await db.execute(
        update(Article)
        .where(Article.claimed_by == owner, spec.column == spec.processing)
        .values(claim_expires_at=_now() + timedelta(seconds=lease))
        .execution_options(synchronize_session="fetch")
    )
    await db.commit()
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


async def release_unfinished(db: AsyncSession, stage: Stage, owner: str) -> int:
    """Return rows this owner claimed but did not finish (e.g. lease lost mid-batch)."""
    spec = _spec(stage)
    result = await db.execute(
        update(Article)
        .where(Article.claimed_by == owner, spec.column == spec.processing)
        .values({spec.column: spec.ready, Article.claimed_by: None, Article.claim_expires_at: None})
        .execution_options(synchronize_session="fetch")
    )
    await db.commit()
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


@dataclass
class RecoveryResult:
    stage: str
    requeued: int
    failed: int
    dry_run: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "requeued": self.requeued,
            "failed": self.failed,
            "dry_run": self.dry_run,
        }


async def recover_expired(
    db: AsyncSession,
    stage: Stage,
    *,
    include_unleased: bool = False,
    dry_run: bool = False,
    batch: int | None = None,
    now: datetime | None = None,
) -> RecoveryResult:
    """Requeue (or fail, after max attempts) claims whose lease has expired.

    ``include_unleased`` additionally targets legacy rows stuck in
    ``processing`` with no lease (pre-gmee03 crashes). Only enable it when no
    worker is running, because such rows have no owner to fence against.
    """
    settings = get_settings()
    spec = _spec(stage)
    now = now or _now()
    limit = batch or settings.PIPELINE_RECOVERY_BATCH
    expired = Article.claim_expires_at < now
    if include_unleased:
        expired = or_(expired, Article.claim_expires_at.is_(None))
    stuck = and_(spec.column == spec.processing, expired)

    rows = (
        await db.execute(
            select(Article.id, Article.attempt_count).where(stuck).order_by(Article.id).limit(limit)
        )
    ).all()
    exhausted = [r[0] for r in rows if (r[1] or 0) >= settings.PIPELINE_MAX_ATTEMPTS]
    retry = [r[0] for r in rows if (r[1] or 0) < settings.PIPELINE_MAX_ATTEMPTS]
    if dry_run or not rows:
        return RecoveryResult(stage.value, len(retry), len(exhausted), dry_run)

    requeued = failed = 0
    if retry:
        res = await db.execute(
            update(Article)
            .where(Article.id.in_(retry), stuck)
            .values({spec.column: spec.ready, Article.claimed_by: None, Article.claim_expires_at: None})
            .execution_options(synchronize_session="fetch")
        )
        requeued = int(res.rowcount or 0)  # type: ignore[attr-defined]
    if exhausted:
        res = await db.execute(
            update(Article)
            .where(Article.id.in_(exhausted), stuck)
            .values(
                {
                    spec.column: spec.failed,
                    Article.claimed_by: None,
                    Article.claim_expires_at: None,
                    Article.last_error: "LeaseExpired: max attempts reached",
                }
            )
            .execution_options(synchronize_session="fetch")
        )
        failed = int(res.rowcount or 0)  # type: ignore[attr-defined]
    await db.commit()
    if requeued or failed:
        logger.warning(
            "recovered expired %s claims: requeued=%d failed=%d", stage.value, requeued, failed
        )
    return RecoveryResult(stage.value, requeued, failed, False)
