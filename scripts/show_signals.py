"""Display extracted signals with their source context."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy import func, select

from src.db import get_session
from src.models import Document, Signal, Source


def main() -> None:
    run_filter = int(sys.argv[1]) if len(sys.argv) > 1 else None
    with get_session() as session:
        total = session.scalar(select(func.count()).select_from(Signal)) or 0
        print(f"Total signals: {total}\n")
        query = (
            select(Signal, Document, Source.name)
            .join(Document, Document.id == Signal.document_id)
            .join(Source, Source.id == Document.source_id)
            .order_by(Signal.id.desc())
        )
        if run_filter is not None:
            query = query.where(Signal.run_id == run_filter)
        rows = session.execute(query.limit(30)).all()

        for signal, document, source_name in rows:
            print("=" * 100)
            print(
                f"signal={signal.id} run={signal.run_id} doc={document.id} "
                f"source={source_name} stage={signal.journey_stage} "
                f"outcome={signal.outcome} confidence={signal.confidence}"
            )
            print(
                f"triggers={signal.triggers} behaviors={signal.behaviors} "
                f"emotions={signal.emotions}"
            )
            print(
                f"expectations={signal.expectations} help={signal.help_seeking} "
                f"segment={signal.segment}"
            )
            print(f"QUOTE: {signal.quote}")
            warnings = (signal.raw or {}).get("validation_warnings")
            if warnings:
                print(f"normalization warnings: {warnings}")
            grounding_warnings = (signal.raw or {}).get("grounding_warnings")
            if grounding_warnings:
                print(f"grounding warnings: {grounding_warnings}")
            print(f"DOC: {(document.raw_text or '')[:700]}")


if __name__ == "__main__":
    main()
