"""Inspect a run and the first documents it processed."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy import select

from src.db import get_session
from src.models import Document, Run


def main() -> None:
    run_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    with get_session() as session:
        run = session.get(Run, run_id)
        if run is None:
            print(f"Run {run_id} not found")
            return
        print(f"Run {run.id} | {run.status} | {run.prompt_version} | {run.model_id}")
        stats = dict(run.stats or {})
        errors = stats.pop("errors", [])
        print(json.dumps(stats, indent=2, default=str))
        print(f"\nErrors: {len(errors)}")
        for error in errors:
            print(json.dumps(error, indent=2, default=str)[:2500])

        print("\nFirst documents (by id):")
        documents = session.scalars(select(Document).order_by(Document.id).limit(8)).all()
        for document in documents:
            print("=" * 90)
            print(
                f"id={document.id} source={document.source.name} "
                f"relevant={document.is_relevant} meta={document.meta}"
            )
            print((document.raw_text or "")[:500])


if __name__ == "__main__":
    main()
