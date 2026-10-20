"""Shared collector types and persistence helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Document, Source
from ..utils.text import (
    content_hash,
    detect_language,
    hash_author,
    is_relevant,
    normalize_text,
)


@dataclass
class RawDocument:
    external_id: str | None
    url: str | None
    author: str | None
    published_at: datetime | None
    text: str
    meta: dict[str, Any] = field(default_factory=dict)
    language: str | None = None


def get_or_create_source(
    session: Session,
    name: str,
    kind: str,
    base_url: str | None = None,
) -> Source:
    source = session.scalar(select(Source).where(Source.name == name))
    if source is None:
        source = Source(name=name, kind=kind, base_url=base_url)
        session.add(source)
        session.flush()
    return source


def save_documents(
    session: Session,
    source: Source,
    docs: list[RawDocument],
) -> tuple[int, int]:
    """Insert new documents. Returns (inserted, skipped)."""
    inserted = 0
    skipped = 0
    seen_external: set[str] = set()
    seen_hashes: set[str] = set()

    for doc in docs:
        text = (doc.text or "").strip()
        if len(text) < 20:
            skipped += 1
            continue

        external_id = str(doc.external_id) if doc.external_id is not None else None
        digest = content_hash(text)

        if external_id and external_id in seen_external:
            skipped += 1
            continue
        if digest in seen_hashes:
            skipped += 1
            continue

        existing = None
        if external_id:
            existing = session.scalar(
                select(Document).where(
                    Document.source_id == source.id,
                    Document.external_id == external_id,
                )
            )
        if existing is None:
            existing = session.scalar(
                select(Document).where(
                    Document.source_id == source.id,
                    Document.content_hash == digest,
                )
            )
        if existing is not None:
            skipped += 1
            continue

        normalized = normalize_text(text)
        keyword_relevant = is_relevant(text)
        meta = dict(doc.meta or {})
        meta.setdefault("keyword_relevant", keyword_relevant)
        session.add(
            Document(
                source_id=source.id,
                external_id=external_id,
                url=doc.url,
                author_hash=hash_author(source.name, doc.author) if doc.author else None,
                published_at=doc.published_at,
                language=doc.language or detect_language(text),
                raw_text=text,
                normalized_text=normalized,
                meta=meta,
                content_hash=digest,
                is_relevant=keyword_relevant,
            )
        )
        if external_id:
            seen_external.add(external_id)
        seen_hashes.add(digest)
        inserted += 1

    session.flush()
    return inserted, skipped
