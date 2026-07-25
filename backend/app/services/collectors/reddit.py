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


class RedditCollector(BaseCollector):
    def __init__(self):
        self.settings = get_settings()
        self._access_token: str | None = None
        self._token_expires_at: float = 0

    async def _get_access_token(self, client: httpx.AsyncClient) -> str | None:
        client_id = self.settings.REDDIT_CLIENT_ID
        client_secret = self.settings.REDDIT_CLIENT_SECRET
        
        if not client_id or not client_secret:
            return None
            
        now = datetime.now().timestamp()
        if self._access_token and now < self._token_expires_at:
            return self._access_token

        try:
            auth = httpx.BasicAuth(client_id, client_secret)
            data = {"grant_type": "client_credentials"}
            headers = {"User-Agent": self.settings.REDDIT_USER_AGENT}
            
            response = await client.post(
                "https://www.reddit.com/api/v1/access_token",
                auth=auth,
                data=data,
                headers=headers
            )
            response.raise_for_status()
            token_data = response.json()
            
            self._access_token = token_data.get("access_token")
            # Usually expires in 86400 seconds (1 day) or 3600 seconds, we pad it by 60s
            expires_in = token_data.get("expires_in", 3600)
            self._token_expires_at = now + expires_in - 60
            
            return self._access_token
        except Exception as exc:
            logger.warning(f"Failed to get Reddit access token: {exc}")
            return None

    async def collect(self, source: Source) -> list[RawArticle]:
        client_id = self.settings.REDDIT_CLIENT_ID
        client_secret = self.settings.REDDIT_CLIENT_SECRET
        
        if not client_id or not client_secret:
            raise MissingCredentialsError("Reddit credentials missing.")

        subreddit = source.url_or_identifier
        # Remove /r/ prefix if user accidentally added it
        if subreddit.startswith("/r/"):
            subreddit = subreddit[3:]
        elif subreddit.startswith("r/"):
            subreddit = subreddit[2:]
            
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                token = await self._get_access_token(client)
                if not token:
                    return []
                    
                url = f"https://oauth.reddit.com/r/{subreddit}/new"
                headers = {
                    "Authorization": f"Bearer {token}",
                    "User-Agent": self.settings.REDDIT_USER_AGENT
                }
                
                response = await client.get(url, headers=headers, params={"limit": 100})
                response.raise_for_status()
                data = response.json()
        except httpx.RequestError as exc:
            logger.warning(f"Network error fetching Reddit /r/{subreddit}: {exc}")
            return []
        except httpx.HTTPStatusError as exc:
            logger.warning(f"HTTP error {exc.response.status_code} fetching Reddit /r/{subreddit}")
            return []
        except Exception as exc:
            logger.warning(f"Unexpected error fetching Reddit /r/{subreddit}: {exc}")
            return []

        articles = []
        children = data.get("data", {}).get("children", [])
        for child in children:
            post = child.get("data", {})
            try:
                title = post.get("title")
                if not title:
                    continue
                    
                permalink = post.get("permalink", "")
                article_url = f"https://www.reddit.com{permalink}" if permalink else post.get("url")
                if not article_url:
                    continue
                
                content = post.get("selftext") or None
                
                created_utc = post.get("created_utc")
                published_at = datetime.fromtimestamp(created_utc) if created_utc else None
                
                author = post.get("author")
                
                articles.append(RawArticle(
                    title=title,
                    url=article_url,
                    content=content,
                    published_at=published_at,
                    author=author,
                    raw_metadata=post
                ))
            except Exception as e:
                logger.warning(f"Error parsing Reddit post from /r/{subreddit}: {e}")
                continue

        return articles
