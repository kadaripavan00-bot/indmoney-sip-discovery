"""Reddit collector using old.reddit.com's public JSON endpoint."""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from datetime import datetime

import requests

from .base import RawDocument

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
}


class RedditCollector:
    def __init__(self, delay_seconds: float = 1.5) -> None:
        self.delay_seconds = delay_seconds
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _search_json(self, subreddit: str, query: str, limit: int) -> list[dict]:
        url = f"https://old.reddit.com/r/{subreddit}/search.json"
        params = {
            "q": query,
            "restrict_sr": 1,
            "sort": "new",
            "limit": min(limit, 100),
            "t": "all",
        }
        for attempt in range(3):
            try:
                response = self.session.get(url, params=params, timeout=30)
                if response.status_code == 429:
                    time.sleep(5 * (attempt + 1))
                    continue
                response.raise_for_status()
                return response.json().get("data", {}).get("children", [])
            except Exception as exc:  # noqa: BLE001
                if attempt == 2:
                    print(f"[reddit] JSON failed r/{subreddit} q={query}: {exc}")
                time.sleep(2 ** attempt)
        return []

    def _search_rss(self, subreddit: str, query: str, limit: int) -> list[RawDocument]:
        url = f"https://www.reddit.com/r/{subreddit}/search.rss"
        params = {
            "q": query,
            "restrict_sr": 1,
            "sort": "new",
            "limit": min(limit, 100),
            "t": "all",
        }
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            root = ET.fromstring(response.text)
        except Exception as exc:  # noqa: BLE001
            print(f"[reddit] RSS failed r/{subreddit} q={query}: {exc}")
            return []

        namespace = {"atom": "http://www.w3.org/2005/Atom"}
        documents: list[RawDocument] = []
        for entry in root.findall("atom:entry", namespace):
            title = entry.findtext("atom:title", default="", namespaces=namespace)
            content = entry.findtext("atom:content", default="", namespaces=namespace)
            text = f"{title}\n{content}".strip()
            if not text:
                continue
            link = entry.find("atom:link", namespace)
            author = entry.findtext("atom:author/atom:name", default="", namespaces=namespace)
            updated = entry.findtext("atom:updated", default="", namespaces=namespace)
            published = None
            if updated:
                try:
                    published = datetime.fromisoformat(updated.replace("Z", "+00:00")).replace(tzinfo=None)
                except ValueError:
                    published = None
            documents.append(
                RawDocument(
                    external_id=entry.findtext("atom:id", default=None, namespaces=namespace),
                    url=link.get("href") if link is not None else None,
                    author=author,
                    published_at=published,
                    text=text,
                    language="en",
                    meta={"source": "reddit", "subreddit": subreddit, "query": query},
                )
            )
        return documents

    def search(self, subreddit: str, query: str, limit: int = 50) -> list[RawDocument]:
        children = self._search_json(subreddit, query, limit)
        documents: list[RawDocument] = []

        for child in children:
            data = child.get("data", {})
            title = data.get("title") or ""
            selftext = data.get("selftext") or ""
            text = f"{title}\n{selftext}".strip()
            if not text:
                continue

            created = data.get("created_utc")
            published = datetime.utcfromtimestamp(created) if created else None
            documents.append(
                RawDocument(
                    external_id=data.get("id"),
                    url=f"https://www.reddit.com{data.get('permalink', '')}",
                    author=data.get("author"),
                    published_at=published,
                    text=text,
                    language="en",
                    meta={
                        "source": "reddit",
                        "subreddit": data.get("subreddit") or subreddit,
                        "score": data.get("score"),
                        "num_comments": data.get("num_comments"),
                        "query": query,
                    },
                )
            )

        time.sleep(self.delay_seconds)
        if not documents:
            documents = self._search_rss(subreddit, query, limit)
        return documents
