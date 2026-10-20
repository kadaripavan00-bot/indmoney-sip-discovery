"""Build a stratified 200-item gold set for validation and adjudication."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

from src.analysis import document_outcomes, signals_frame
from src.db import get_session

OUTCOME_GROUPS = {
    "lapse": {"stopped", "paused", "reduced", "withdrew"},
    "continue": {"continues", "increased", "returned"},
    "unknown": {"unknown"},
}


def _outcome_group(outcome: str | None) -> str:
    for group, values in OUTCOME_GROUPS.items():
        if outcome in values:
            return group
    return "unknown"


def _sample_stratum(frame: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    if len(frame) <= n:
        return frame
    return frame.sample(n=n, random_state=seed)


def build_gold_set(signals: pd.DataFrame, documents: pd.DataFrame, size: int = 200) -> pd.DataFrame:
    docs = document_outcomes(signals, documents)
    docs["outcome_group"] = docs["document_outcome"].map(_outcome_group)

    # Prefer documents that have a signal, then fill with model-relevant and
    # keyword-relevant documents so the gold set tests both relevance and coding.
    signal_docs = set(signals["document_id"].tolist()) if not signals.empty else set()
    docs["has_signal"] = docs["document_id"].isin(signal_docs)

    # Every resolved outcome in the corpus is included first. There are only
    # ~80, and outcome kappa is the noisiest part of validation, so dropping
    # any of them to satisfy a per-source quota would be wasteful.
    selected: list[pd.DataFrame] = []
    resolved = docs[docs["outcome_group"].isin(["lapse", "continue"])].copy()
    if len(resolved) > size:
        resolved = _sample_stratum(resolved, size, seed=1000)
    if not resolved.empty:
        selected.append(resolved)
    selected_ids = set(resolved["document_id"].tolist())

    remaining_slots = max(0, size - len(resolved))
    source_kinds = sorted(docs["source_kind"].dropna().unique())
    per_source = remaining_slots // max(1, len(source_kinds))

    # The remaining slots test relevance and theme coding: half signal-bearing
    # unresolved documents, half no-signal documents, balanced by source.
    for source_index, source_kind in enumerate(source_kinds):
        group = docs[
            (docs["source_kind"] == source_kind)
            & (~docs["document_id"].isin(selected_ids))
        ]
        with_signal = group[group["has_signal"]]
        without_signal = group[~group["has_signal"]]
        take_with = min(len(with_signal), per_source // 2)
        take_without = min(len(without_signal), per_source - take_with)
        if take_with + take_without < per_source:
            take_with = min(len(with_signal), per_source - take_without)

        chosen_parts: list[pd.DataFrame] = []
        if take_with:
            part = _sample_stratum(
                with_signal, take_with, seed=2000 + source_index * 10
            )
            chosen_parts.append(part)
            selected_ids.update(part["document_id"].tolist())
        if take_without:
            part = _sample_stratum(
                without_signal, take_without, seed=3000 + source_index * 10
            )
            chosen_parts.append(part)
            selected_ids.update(part["document_id"].tolist())
        if chosen_parts:
            selected.append(pd.concat(chosen_parts, ignore_index=True))

    result = pd.concat(selected, ignore_index=True) if selected else docs.head(0)
    if len(result) < size:
        remaining = docs[~docs["document_id"].isin(result["document_id"])]
        if not remaining.empty:
            result = pd.concat(
                [result, _sample_stratum(remaining, size - len(result), seed=4000)],
                ignore_index=True,
            )
    result = result.drop_duplicates("document_id").head(size).copy()

    # Attach the Gemini signal(s) for each document.
    rows = []
    for _, doc in result.iterrows():
        doc_signals = signals[signals["document_id"] == doc["document_id"]] if not signals.empty else signals
        primary_theme = "other_unclassified"
        if not doc_signals.empty:
            first = doc_signals.iloc[0]
            quote = first["quote"]
            gemini_outcome = first["outcome"]
            gemini_themes = first["themes"]
            primary_theme = first["primary_theme"]
            gemini_codes = {
                "triggers": first["triggers"],
                "behaviors": first["behaviors"],
                "emotions": first["emotions"],
                "expectations": first["expectations"],
                "help_seeking": first["help_seeking"],
            }
            gemini_all_codes = {
                field: sorted(
                    {
                        code
                        for values in doc_signals[field]
                        for code in (values if isinstance(values, list) else [])
                    }
                )
                for field in (
                    "triggers",
                    "behaviors",
                    "emotions",
                    "expectations",
                    "help_seeking",
                )
            }
            all_quotes = doc_signals["quote"].tolist()
        else:
            quote = ""
            gemini_outcome = doc["document_outcome"]
            gemini_themes = []
            gemini_codes = {}
            gemini_all_codes = {}
            all_quotes = []
        rows.append(
            {
                "gold_id": f"G{len(rows) + 1:03d}",
                "document_id": int(doc["document_id"]),
                "source": doc["source"],
                "source_kind": doc["source_kind"],
                "url": doc["url"],
                "published_at": doc["published_at"],
                "document_text": (doc.get("document_text") or "")[:1800],
                "gemini_relevant": bool(doc["model_relevant"]),
                "gemini_outcome": gemini_outcome,
                "gemini_primary_theme": primary_theme,
                "gemini_themes": gemini_themes,
                "gemini_quote": quote,
                "gemini_all_quotes": all_quotes,
                "gemini_codes": json.dumps(gemini_codes, ensure_ascii=False),
                "gemini_all_codes": json.dumps(gemini_all_codes, ensure_ascii=False),
                "human_relevant": "",
                "human_outcome": "",
                "human_primary_theme": "",
                "human_notes": "",
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, default=200)
    parser.add_argument("--output", default="data/exports")
    args = parser.parse_args()

    with get_session() as session:
        signals, documents = signals_frame(session)
        if signals.empty:
            print("No current signals. Run extraction first.")
            return
        gold = build_gold_set(signals, documents, size=args.size)

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    gold.to_csv(output / "gold_set_200.csv", index=False, encoding="utf-8-sig")
    with (output / "gold_set_200.jsonl").open("w", encoding="utf-8") as handle:
        for record in gold.to_dict(orient="records"):
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    review = gold.sample(n=min(30, len(gold)), random_state=7).copy()
    review.to_csv(output / "gold_set_review_30.csv", index=False, encoding="utf-8-sig")
    print(f"Wrote {len(gold)} gold rows to {output / 'gold_set_200.csv'}")
    print(f"Wrote {len(review)} review rows to {output / 'gold_set_review_30.csv'}")
    print(gold.groupby(["source_kind", "gemini_outcome"]).size().to_string())


if __name__ == "__main__":
    main()
