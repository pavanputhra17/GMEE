"""Collector failure-mode branches (must return [], never raise)."""
import uuid

import httpx
import pytest

from app.models.source import Source, SourceTypeEnum
from app.services.collectors.base import MissingCredentialsError
from app.services.collectors.news_api import NewsAPICollector
from app.services.collectors.reddit import RedditCollector
from app.services.collectors.rss import RSSCollector


def _source(t: SourceTypeEnum, ident: str = "feed") -> Source:
    return Source(id=uuid.uuid4(), name="T", type=t, url_or_identifier=ident, is_active=True)


def _patch_get(monkeypatch: pytest.MonkeyPatch, fn) -> None:
    monkeypatch.setattr(httpx.AsyncClient, "get", fn)


async def test_rss_network_error_returns_empty(monkeypatch):
    async def boom(self, *a, **k):
        raise httpx.RequestError("connection reset")

    _patch_get(monkeypatch, boom)
    assert await RSSCollector().collect(_source(SourceTypeEnum.rss)) == []


async def test_rss_http_status_error_returns_empty(monkeypatch):
    req = httpx.Request("GET", "http://feed")
    resp = httpx.Response(503, request=req)

    class Resp:
        def raise_for_status(self):
            raise httpx.HTTPStatusError("503", request=req, response=resp)

        text = ""

    async def ok(self, *a, **k):
        return Resp()

    _patch_get(monkeypatch, ok)
    assert await RSSCollector().collect(_source(SourceTypeEnum.rss)) == []


async def test_rss_unexpected_error_returns_empty(monkeypatch):
    async def boom(self, *a, **k):
        raise ValueError("unexpected")

    _patch_get(monkeypatch, boom)
    assert await RSSCollector().collect(_source(SourceTypeEnum.rss)) == []


async def test_reddit_missing_credentials_raises(monkeypatch):
    c = RedditCollector()
    monkeypatch.setattr(c.settings, "REDDIT_CLIENT_ID", "")
    monkeypatch.setattr(c.settings, "REDDIT_CLIENT_SECRET", "")
    with pytest.raises(MissingCredentialsError):
        await c.collect(_source(SourceTypeEnum.reddit, "science"))


async def test_reddit_no_token_returns_empty(monkeypatch):
    c = RedditCollector()
    monkeypatch.setattr(c.settings, "REDDIT_CLIENT_ID", "id")
    monkeypatch.setattr(c.settings, "REDDIT_CLIENT_SECRET", "sec")

    async def no_token(client):
        return None

    monkeypatch.setattr(c, "_get_access_token", no_token)
    assert await c.collect(_source(SourceTypeEnum.reddit, "science")) == []


async def test_reddit_network_error_returns_empty(monkeypatch):
    c = RedditCollector()
    monkeypatch.setattr(c.settings, "REDDIT_CLIENT_ID", "id")
    monkeypatch.setattr(c.settings, "REDDIT_CLIENT_SECRET", "sec")

    async def boom(self, *a, **k):
        raise httpx.RequestError("timeout")

    _patch_get(monkeypatch, boom)
    assert await c.collect(_source(SourceTypeEnum.reddit, "science")) == []


async def test_reddit_http_error_returns_empty(monkeypatch):
    c = RedditCollector()
    monkeypatch.setattr(c.settings, "REDDIT_CLIENT_ID", "id")
    monkeypatch.setattr(c.settings, "REDDIT_CLIENT_SECRET", "sec")

    req = httpx.Request("GET", "https://oauth.reddit.com/r/science/new")
    resp = httpx.Response(503, request=req)

    class Resp:
        status_code = 503

        def raise_for_status(self):
            raise httpx.HTTPStatusError("503", request=req, response=resp)

        def json(self):
            return {}

    async def ok(self, *a, **k):
        return Resp()

    _patch_get(monkeypatch, ok)
    assert await c.collect(_source(SourceTypeEnum.reddit, "science")) == []


async def test_reddit_success_skips_malformed_posts(monkeypatch):
    c = RedditCollector()
    monkeypatch.setattr(c.settings, "REDDIT_CLIENT_ID", "id")
    monkeypatch.setattr(c.settings, "REDDIT_CLIENT_SECRET", "sec")

    async def fake_token(client):
        return "tok"

    monkeypatch.setattr(c, "_get_access_token", fake_token)

    class Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": {
                    "children": [
                        {
                            "data": {
                                "title": "New study on coral",
                                "permalink": "/r/science/comments/abc/new_study/",
                                "selftext": "Full text here",
                                "created_utc": 1700000000,
                                "author": "sciencebot",
                            }
                        },
                        {"data": {"permalink": "/r/science/comments/def/"}},
                        {"data": {"title": "No link here", "permalink": "", "url": ""}},
                    ]
                }
            }

    async def ok(self, *a, **k):
        return Resp()

    _patch_get(monkeypatch, ok)
    articles = await c.collect(_source(SourceTypeEnum.reddit, "science"))
    assert len(articles) == 1
    a = articles[0]
    assert a.title == "New study on coral"
    assert a.url == "https://www.reddit.com/r/science/comments/abc/new_study/"
    assert a.published_at is not None and a.published_at.tzinfo is not None
    assert a.author == "sciencebot"


async def test_newsapi_removed_articles_are_skipped(monkeypatch):
    c = NewsAPICollector()
    monkeypatch.setattr(c.settings, "NEWSAPI_KEY", "k")

    class Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "status": "ok",
                "articles": [
                    {"title": "[Removed]", "url": "http://news.com/removed"},
                    {"title": "Real story", "url": "http://news.com/1", "content": "body",
                     "publishedAt": "2026-01-01T00:00:00Z", "author": None},
                ],
            }

    async def ok(self, *a, **k):
        return Resp()

    monkeypatch.setattr(httpx.AsyncClient, "get", ok)
    articles = await c.collect(_source(SourceTypeEnum.news_api, "misinformation"))
    assert len(articles) == 1
    assert articles[0].title == "Real story"


async def test_newsapi_malformed_payload_returns_empty(monkeypatch):
    c = NewsAPICollector()
    monkeypatch.setattr(c.settings, "NEWSAPI_KEY", "k")

    class Resp:
        def raise_for_status(self):
            return None

        def json(self):
            raise ValueError("invalid json")

    async def ok(self, *a, **k):
        return Resp()

    monkeypatch.setattr(httpx.AsyncClient, "get", ok)
    assert await c.collect(_source(SourceTypeEnum.news_api, "misinformation")) == []
