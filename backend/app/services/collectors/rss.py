import calendar
import logging
from datetime import UTC, datetime

import feedparser
import httpx

from app.models.source import Source
from app.services.collectors.base import BaseCollector, RawArticle

logger = logging.getLogger(__name__)


class RSSCollector(BaseCollector):
    async def collect(self, source: Source) -> list[RawArticle]:
        url = source.url_or_identifier
        
        try:
            # RSS feeds often use 302 redirects (e.g. BBC News), so follow_redirects=True is explicitly allowed here
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()
                content = response.text
        except httpx.RequestError as exc:
            logger.warning(f"Network error fetching RSS feed {url}: {exc}")
            return []
        except httpx.HTTPStatusError as exc:
            logger.warning(f"HTTP error {exc.response.status_code} fetching RSS feed {url}")
            return []
        except Exception as exc:
            logger.warning(f"Unexpected error fetching RSS feed {url}: {exc}")
            return []

        parsed = feedparser.parse(content)
        
        if parsed.bozo and getattr(parsed.bozo_exception, 'getMessage', lambda: '')() != 'document declared as us-ascii, but parsed as utf-8':
            # Some minor bozo exceptions can be ignored, but generally log malformed feeds
            logger.warning(f"Malformed RSS feed {url}: {parsed.bozo_exception}")
            # we can still try to extract entries if they exist, but if it's completely broken, entries will be empty.

        articles = []
        for entry in parsed.entries:
            try:
                # Extract title
                title = entry.get("title", "").strip()
                if not title:
                    continue
                
                # Extract URL
                article_url = entry.get("link", "").strip()
                if not article_url:
                    continue
                
                # Extract content
                content_html = ""
                if "content" in entry and entry.content:
                    content_html = entry.content[0].value
                elif "summary" in entry:
                    content_html = entry.summary
                
                # Extract published_at
                # feedparser's *_parsed struct_times are UTC — use timegm,
                # not mktime, so hosts on non-UTC local time stay correct.
                published_at = None
                if "published_parsed" in entry and entry.published_parsed:
                    published_at = datetime.fromtimestamp(
                        calendar.timegm(entry.published_parsed), tz=UTC
                    )
                elif "updated_parsed" in entry and entry.updated_parsed:
                    published_at = datetime.fromtimestamp(
                        calendar.timegm(entry.updated_parsed), tz=UTC
                    )
                    
                # Extract author
                author = entry.get("author", None)
                
                # Extract raw metadata
                raw_metadata = dict(entry)
                
                articles.append(RawArticle(
                    title=title,
                    url=article_url,
                    content=content_html or None,
                    published_at=published_at,
                    author=author,
                    raw_metadata=raw_metadata
                ))
            except Exception as e:
                logger.warning(f"Error parsing RSS entry from {url}: {e}")
                continue

        return articles
