"""Generate charts for the deck, case write-up, and PRD."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.reporting import build_all_charts


def main() -> None:
    charts = build_all_charts(Path("deliverables/charts"))
    for name, path in charts.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
