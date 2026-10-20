"""Google Play Store review collector."""

from __future__ import annotations

import time
from datetime import datetime

from google_play_scraper import Sort, reviews

from .base import RawDocument


class PlayStoreCollector:
    def __init__(
        self,
        country: str = "in",
        languages: tuple[str, ...] = ("en", "hi"),
        count: int = 600,
    ) -> None:
        self.country = country
        self.languages = languages
        self.count = count

    def _fetch(self, app_id: str, language: str) -> list[dict]:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                result, _ = reviews(
                    app_id,
                    lang=language,
                    country=self.country,
                    sort=Sort.NEWEST,
                    count=self.count,
                )
                return result or []
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                time.sleep(2 ** attempt)
        print(f"[play_store] failed {app_id}/{language}: {last_error}")
        return []

    def collect(self, app_id: str, app_name: str) -> list[RawDocument]:
        documents: list[RawDocument] = []
        for language in self.languages:
            for review in self._fetch(app_id, language):
                text = (review.get("content") or "").strip()
                if not text:
                    continue

                published = review.get("at")
                if isinstance(published, datetime):
                    published = published.replace(tzinfo=None)

                documents.append(
                    RawDocument(
                        external_id=review.get("reviewId"),
                        url=(
                            "https://play.google.com/store/apps/details"
                            f"?id={app_id}&reviewId={review.get('reviewId')}"
                        ),
                        author=review.get("userName"),
                        published_at=published,
                        text=text,
                        language=language,
                        meta={
                            "source": "play_store",
                            "app_id": app_id,
                            "app_name": app_name,
                            "score": review.get("score"),
                            "thumbs_up": review.get("thumbsUpCount"),
                            "app_version": review.get("appVersion"),
                            "review_created_version": review.get("reviewCreatedVersion"),
                            "reply_content": review.get("replyContent"),
                        },
                    )
                )
            time.sleep(1)
        return documents
