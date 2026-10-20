"""Run the LLM signal extractor.

Examples:
    python scripts/extract_signals.py --limit 12 --batch-size 3
    python scripts/extract_signals.py --source play_store --limit 60
    python scripts/extract_signals.py --limit 200 --resume
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline.extract import run_extraction


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--source", default=None, help="Filter sources by substring, e.g. play_store")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--all-docs",
        action="store_true",
        help="Process keyword-irrelevant documents too. Default is relevant-only.",
    )
    args = parser.parse_args()

    stats = run_extraction(
        limit=args.limit,
        batch_size=args.batch_size,
        source_contains=args.source,
        resume=args.resume,
        relevant_only=not args.all_docs,
    )
    printable = {key: value for key, value in stats.items() if key != "errors"}
    print(json.dumps(printable, indent=2, default=str))
    if stats.get("errors"):
        print(f"\n{len(stats['errors'])} errors recorded in the run stats.")


if __name__ == "__main__":
    main()
