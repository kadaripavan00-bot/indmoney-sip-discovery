"""Count strict SIP/MF candidates by source."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy import select

from src.db import get_session
from src.models import Document
from src.utils.text import is_strictly_relevant


def main() -> None:
    with get_session() as session:
        documents = session.scalars(select(Document).order_by(Document.id)).all()
        counts = Counter()
        relevant = Counter()
        for document in documents:
            counts[document.source.name] += 1
            if is_strictly_relevant(document.raw_text or ""):
                relevant[document.source.name] += 1
        print("Total documents:", len(documents))
        print("Strict candidates:", sum(relevant.values()))
        print("\nStrict candidates by source:")
        for name, count in relevant.most_common():
            print(f"  {name:32s} {count:5d} / {counts[name]:5d}")


if __name__ == "__main__":
    main()
