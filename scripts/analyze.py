"""Build theme, segment, and opportunity tables from grounded signals."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from src.analysis import (
    code_frequency,
    document_outcomes,
    export_analysis,
    save_theme_outputs,
    segment_summary,
    signals_frame,
    source_summary,
    stage_summary,
    theme_summary,
)
from src.db import get_session


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/exports")
    parser.add_argument("--no-db", action="store_true", help="Skip writing theme/opportunity rows.")
    args = parser.parse_args()

    with get_session() as session:
        signals, documents = signals_frame(session)
        if signals.empty:
            print("No current signals. Run extraction first.")
            return

        documents = document_outcomes(signals, documents)
        summary = theme_summary(signals, documents)
        codes = code_frequency(signals)
        segments = segment_summary(signals)
        sources = source_summary(signals)
        stages = stage_summary(signals)

        export_analysis(
            args.output,
            signals,
            documents,
            summary,
            codes,
            segments,
            sources,
            stages,
        )
        if not args.no_db:
            save_theme_outputs(signals, documents, summary, session)

    print(f"Signals: {len(signals)} across {signals['document_id'].nunique()} documents")
    print(f"Deep-coded documents: {int(documents['deep_coded'].sum())}")
    print(f"Relevant documents: {int(documents['model_relevant'].sum())}")
    print("\nTop themes by opportunity score:")
    columns = [
        "rank",
        "name",
        "signals",
        "documents",
        "share_signal_docs",
        "lapse_display",
        "lift_display",
        "opportunity_score",
    ]
    print(summary[columns].to_string(index=False, float_format=lambda value: f"{value:.2f}"))
    print("\nTop codes:")
    print(codes.head(25).to_string(index=False))
    print(f"\nExports written to {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
