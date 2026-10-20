"""Discourse forum collector for ValuePickr and TradingQ&A."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import requests
from bs4 import BeautifulSoup

from .base import RawDocument

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
}


class DiscourseCollector:
    def __init__(self, base_url: str, name: str, max_topics: int = 15) -> None:
        self.base_url = base_url.rstrip("/")
        self.name = name
        self.max_topics = max_topics
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _search(self, query: str) -> list[dict[str, Any]]:
        try:
            response = self.session.get(
                f"{self.base_url}/search.json",
                params={"q": query},
                timeout=30,
            )
            response.raise_for_status()
            return response.json().get("posts", [])
        except Exception as exc:  # noqa: BLE001
            print(f"[forum:{self.name}] search failed q={query}: {exc}")
            return []

    def _topic(self, topic_id: int) -> dict[str, Any]:
        try:
            response = self.session.get(
                f"{self.base_url}/t/{topic_id}.json",
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # noqa: BLE001
            print(f"[forum:{self.name}] topic {topic_id} failed: {exc}")
            return {}

    def collect(self, query: str) -> list[RawDocument]:
        posts = self._search(query)
        topic_ids: list[int] = []
        for post in posts:
            topic_id = post.get("topic_id")
            if topic_id and topic_id not in topic_ids:
                topic_ids.append(topic_id)

        documents: list[RawDocument] = []
        for topic_id in topic_ids[: self.max_topics]:
            topic = self._topic(topic_id)
            title = topic.get("title", "")
            stream = topic.get("post_stream", {}).get("posts", [])
            for post in stream:
                cooked = post.get("cooked") or ""
                text = BeautifulSoup(cooked, "lxml").get_text(" ", strip=True)
                if not text:
                    continue

                created = post.get("created_at")
                published = None
                if created:
                    try:
                        published = datetime.fromisoformat(created.replace("Z", "+00:00")).replace(tzinfo=None)
                    except ValueError:
                        published = None

                documents.append(
                    RawDocument(
                        external_id=f"{topic_id}:{post.get('post_number')}",
                        url=f"{self.base_url}/t/{topic_id}/{post.get('post_number')}",
                        author=post.get("username"),
                        published_at=published,
                        text=f"{title}\n{text}".strip(),
                        language="en",
                        meta={
                            "source": f"forum:{self.name}",
                            "forum": self.name,
                            "topic_id": topic_id,
                            "topic_title": title,
                            "query": query,
                        },
                    )
                )
            time.sleep(1)
        return documents
