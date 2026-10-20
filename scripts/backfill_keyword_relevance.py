"""Backfill keyword relevance into document metadata.

The extraction pipeline overwrites `is_relevant` with the model's judgment.
This script preserves the original keyword relevance so later runs can still
select the right candidate pool.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from src.db import get_session
from src.models import Document
from src.utils.text import is_relevant


def main() -> None:
    updated = 0
    with get_session() as session:
        documents = session.scalars(select(Document)).all()
        for document in documents:
            meta = dict(document.meta or {})
            meta["keyword_relevant"] = is_relevant(document.raw_text or "")
            document.meta = meta
            updated += 1
        session.commit()
    print(f"Backfilled keyword_relevant for {updated} documents.")


if __name__ == "__main__":
    main()
