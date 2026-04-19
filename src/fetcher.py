"""NewsFetcher — Retrieves news articles from NewsAPI and RSS feeds."""

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests

from src.utils import ensure_dir, get_logger, load_sources, strip_html, today_str, truncate

logger = get_logger("fetcher")


class NewsFetcher:
    """Fetches articles from NewsAPI (primary) with RSS fallback."""

    def __init__(self, config: dict):
        self.config = config
        self.newsapi_key = config["newsapi"]["api_key"]
        self.newsapi_base = config["newsapi"]["base_url"]
        self.sources = load_sources()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def fetch(self, topic_key: str) -> list[dict]:
        """Fetch articles for a given topic key defined in config.yaml."""
        topic_cfg = self.config["topics"].get(topic_key)
        if not topic_cfg:
            raise ValueError(f"Unknown topic key: {topic_key}")

        queries: list[str] = topic_cfg.get("queries", [])
        language: str = topic_cfg.get("language", self.config["app"]["language"])
        region: str | None = topic_cfg.get("region")
        max_articles: int = topic_cfg.get("max_articles", 15)

        logger.info("Fetching articles for topic '%s' (queries=%s)", topic_key, queries)

        articles: list[dict] = []

        # Primary: NewsAPI
        if self.newsapi_key and not self.newsapi_key.startswith("${"):
            articles = self._fetch_newsapi(queries, language, region, max_articles)
            logger.info("NewsAPI returned %d article(s)", len(articles))
        else:
            logger.warning("NEWSAPI_KEY not set — skipping NewsAPI, using RSS fallback")

        # Fallback: RSS
        if not articles:
            logger.info("Falling back to RSS feeds for topic '%s'", topic_key)
            articles = self._fetch_rss(topic_key, max_articles)
            logger.info("RSS fallback returned %d article(s)", len(articles))

        articles = self._deduplicate(articles)
        articles = self._clean(articles)
        articles = articles[:max_articles]

        logger.info("Final article count for '%s': %d", topic_key, len(articles))

        self._save(articles, topic_key)
        return articles

    # ------------------------------------------------------------------
    # NewsAPI
    # ------------------------------------------------------------------

    def _fetch_newsapi(
        self, queries: list[str], language: str, region: str | None, max_articles: int
    ) -> list[dict]:
        since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
        articles: list[dict] = []
        seen_urls: set[str] = set()

        for query in queries:
            params: dict = {
                "q": query,
                "language": language,
                "from": since,
                "sortBy": "publishedAt",
                "pageSize": max_articles,
                "apiKey": self.newsapi_key,
            }
            if region:
                params["country"] = region

            endpoint = f"{self.newsapi_base}/everything" if not region else f"{self.newsapi_base}/top-headlines"

            try:
                resp = requests.get(endpoint, params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json()
                for item in data.get("articles", []):
                    url = item.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        articles.append(self._normalize_newsapi(item))
            except requests.RequestException as exc:
                logger.error("NewsAPI request failed for query '%s': %s", query, exc)

        return articles

    @staticmethod
    def _normalize_newsapi(item: dict) -> dict:
        return {
            "title": item.get("title") or "",
            "description": item.get("description") or item.get("content") or "",
            "url": item.get("url") or "",
            "published_at": item.get("publishedAt") or "",
            "source": (item.get("source") or {}).get("name") or "",
        }

    # ------------------------------------------------------------------
    # RSS Fallback
    # ------------------------------------------------------------------

    def _fetch_rss(self, topic_key: str, max_articles: int) -> list[dict]:
        rss_feeds = self.sources.get("rss_feeds", {})
        # Try exact topic key, then "all_topics" as a catch-all
        feed_urls: list[str] = rss_feeds.get(topic_key) or rss_feeds.get("all_topics") or []

        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        articles: list[dict] = []

        for url in feed_urls:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries:
                    published = self._parse_rss_date(entry)
                    if published and published < cutoff:
                        continue
                    articles.append(self._normalize_rss(entry, feed.feed.get("title", url)))
                    if len(articles) >= max_articles * 2:
                        break
            except (OSError, ValueError, KeyError) as exc:
                logger.error("RSS parse error for %s: %s", url, exc)

        return articles

    @staticmethod
    def _parse_rss_date(entry) -> datetime | None:
        """Parse publication date from a feedparser entry."""
        import email.utils

        for attr in ("published", "updated", "created"):
            raw = getattr(entry, attr, None)
            if not raw:
                continue
            try:
                t = email.utils.parsedate_to_datetime(raw)
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
                return t
            except (ValueError, TypeError, OverflowError):
                pass
        return None

    @staticmethod
    def _normalize_rss(entry, feed_title: str) -> dict:
        description = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
        return {
            "title": getattr(entry, "title", "") or "",
            "description": description,
            "url": getattr(entry, "link", "") or "",
            "published_at": getattr(entry, "published", "") or getattr(entry, "updated", "") or "",
            "source": feed_title,
        }

    # ------------------------------------------------------------------
    # Post-processing
    # ------------------------------------------------------------------

    @staticmethod
    def _deduplicate(articles: list[dict]) -> list[dict]:
        seen: set[str] = set()
        unique: list[dict] = []
        for art in articles:
            url = art.get("url", "")
            key = hashlib.md5(url.encode()).hexdigest() if url else None
            if key and key not in seen:
                seen.add(key)
                unique.append(art)
            elif not key:
                unique.append(art)
        return unique

    @staticmethod
    def _clean(articles: list[dict]) -> list[dict]:
        cleaned = []
        for art in articles:
            art["title"] = strip_html(art.get("title", ""))
            art["description"] = truncate(strip_html(art.get("description", "")), 500)
            cleaned.append(art)
        return cleaned

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save(self, articles: list[dict], topic_key: str) -> Path:
        date_str = today_str()
        out_dir = ensure_dir(Path("data") / "raw" / date_str)
        out_file = out_dir / f"{topic_key}_articles.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(articles, f, ensure_ascii=False, indent=2)
        logger.info("Articles saved to %s", out_file)
        return out_file
