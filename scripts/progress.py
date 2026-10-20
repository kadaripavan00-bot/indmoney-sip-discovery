"""Print extraction progress by run."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from src.db import get_session
from src.models import Document, Signal


def main() -> None:
    with get_session() as session:
        documents = session.scalars(select(Document)).all()
        signals = session.scalars(select(Signal)).all()
        by_source = Counter()
        for document in documents:
            if (document.meta or {}).get("extract_run_id"):
                by_source[document.source.name] += 1
    runs = Counter((document.meta or {}).get("extract_run_id") for document in documents)
    runs.pop(None, None)
    print("Deep-coded:", sum(runs.values()))
    print("Signals:", len(signals))
    print("Runs:", dict(sorted(runs.items())))
    print("By source:", dict(by_source.most_common()))


if __name__ == "__main__":
    main()
