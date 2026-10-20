"""Print a few random relevant documents for prompt calibration."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy import func, select

from src.db import get_session
from src.models import Document, Source


def main() -> None:
    with get_session() as session:
        rows = session.execute(
            select(Document, Source.name)
            .join(Source, Source.id == Document.source_id)
            .where(Document.is_relevant.is_(True))
            .order_by(func.random())
            .limit(8)
        ).all()

        for document, source_name in rows:
            print("=" * 100)
            print(f"{source_name} | {document.published_at} | {document.language}")
            print(f"URL: {document.url}")
            print("-" * 100)
            text = (document.raw_text or "").replace("\n", " ")
            print(text[:900])
            print()


if __name__ == "__main__":
    main()
