"""Print corpus statistics."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select

from src.db import get_session
from src.models import Document, Source
from src.utils.text import is_strictly_relevant


def main() -> None:
    with get_session() as session:
        total = session.scalar(select(func.count()).select_from(Document)) or 0
        relevant = (
            session.scalar(
                select(func.count()).select_from(Document).where(Document.is_relevant.is_(True))
            )
            or 0
        )
        print(f"Total documents: {total}")
        print(f"Relevant documents: {relevant}")
        print(f"Relevance rate: {relevant / total:.1%}" if total else "Relevance rate: n/a")
        texts = session.scalars(select(Document.raw_text)).all()
        strict = sum(1 for text in texts if is_strictly_relevant(text or ""))
        print(f"Strict SIP/MF candidates: {strict}")

        rows = session.execute(
            select(Source.name, func.count(Document.id))
            .join(Document, Document.source_id == Source.id)
            .group_by(Source.name)
            .order_by(func.count(Document.id).desc())
        ).all()
        print("\nBy source:")
        for name, count in rows:
            print(f"  {name:40s} {count:6d}")

        min_date, max_date = session.execute(
            select(func.min(Document.published_at), func.max(Document.published_at))
        ).one()
        print(f"\nDate range: {min_date} -> {max_date}")

        languages = session.execute(
            select(Document.language, func.count(Document.id))
            .group_by(Document.language)
            .order_by(func.count(Document.id).desc())
        ).all()
        print("\nBy language:")
        for language, count in languages:
            print(f"  {language or 'unknown':10s} {count:6d}")


if __name__ == "__main__":
    main()
