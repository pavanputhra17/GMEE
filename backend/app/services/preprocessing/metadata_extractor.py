import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from dateutil.parser import parse as dateutil_parse

logger = logging.getLogger(__name__)


def extract_domain(url: str | None) -> str | None:
    if not url:
        return None
    try:
        parsed = urlparse(url)
        return parsed.netloc if parsed.netloc else None
    except Exception:
        return None


def compute_word_count(text: str | None) -> int | None:
    if not text:
        return None
    return len(text.split())


def extract_or_repair_published_at(
    published_at: datetime | None,
    raw_metadata: dict[str, Any]
) -> datetime | None:
    """
    If published_at is already set, return it.
    Otherwise, look into raw_metadata for common date fields and try to parse them.
    Returns None if no parseable date is found.
    """
    if published_at:
        return published_at

    candidate_fields = ['publishedAt', 'created_utc', 'pubDate', 'published', 'date']
    
    for field in candidate_fields:
        if raw_metadata.get(field):
            val = raw_metadata[field]
            try:
                # If it's a unix timestamp (e.g. reddit created_utc)
                if isinstance(val, (int, float)):
                    return datetime.fromtimestamp(val, tz=UTC)
                # If it's a string, attempt to parse
                if isinstance(val, str):
                    parsed_date = dateutil_parse(val)
                    if parsed_date is not None and isinstance(parsed_date, datetime):
                        return parsed_date
            except Exception as exc:
                logger.debug("date parse fallback failed (%r): %s", val, exc)
                continue
                
    return None
