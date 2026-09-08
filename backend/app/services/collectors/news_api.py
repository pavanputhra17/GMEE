import logging
from datetime import datetime

import httpx

from app.core.config import get_settings
from app.models.source import Source
from app.services.collectors.base import (
    BaseCollector,
    MissingCredentialsError,
    RawArticle,
)

logger = logging.getLogger(__name__)


class NewsAPICollector(BaseCollector):
    def __init__(self) -> None:
        self.settings = get_settings()

    async def collect(self, source: Source) -> list[RawArticle]:
        api_key = self.settings.NEWSAPI_KEY
        if not api_key:
            raise MissingCredentialsError("NewsAPI key missing.")

        query = source.url_or_identifier
        url = "https://newsapi.org/v2/everything"
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    url,
                    params={
                        "q": query,
                        "pageSize": 100,  # Max allowed for developer accounts is 100 per page
                        "language": "en",
                        "sortBy": "publishedAt"
                    },
                    headers={"X-Api-Key": api_key}
                )
                response.raise_for_status()
                data = response.json()
        except httpx.RequestError as exc:
            logger.warning(f"Network error fetching NewsAPI for '{query}': {exc}")
            return []
        except httpx.HTTPStatusError as exc:
            logger.warning(f"HTTP error {exc.response.status_code} fetching NewsAPI for '{query}'")
            return []
        except Exception as exc:
            logger.warning(f"Unexpected error fetching NewsAPI for '{query}': {exc}")
            return []

        if data.get("status") != "ok":
            logger.warning(f"NewsAPI returned non-ok status for '{query}': {data.get('message')}")
            return []

        articles = []
        for item in data.get("articles", []):
            try:
                title = item.get("title")
                if not title or title == "[Removed]":
                    continue
                
                article_url = item.get("url")
                if not article_url:
                    continue
                
                content = item.get("content") or item.get("description")
                
                published_at_str = item.get("publishedAt")
                if published_at_str:
                    # Replace Z with +00:00 for fromisoformat compatibility in < 3.11, though 3.11 supports Z
                    published_at_str = published_at_str.replace("Z", "+00:00")
                    published_at = datetime.fromisoformat(published_at_str)
                else:
                    published_at = None
                
                author = item.get("author")
                
                articles.append(RawArticle(
                    title=title,
                    url=article_url,
                    content=content,
                    published_at=published_at,
                    author=author,
                    raw_metadata=item
                ))
            except Exception as e:
                logger.warning(f"Error parsing NewsAPI article for '{query}': {e}")
                continue

        return articles
