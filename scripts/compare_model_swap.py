"""Compare the primary extraction with a second-model gold-set run."""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

from src.analysis import (
    CONTINUE_OUTCOMES,
    LAPSE_OUTCOMES,
    _match_themes,
    _primary_outcome,
    _primary_theme,
)


def cohen_kappa(left: list[str], right: list[str]) -> float:
    if not left or len(left) != len(right):
        return float("nan")
    labels = sorted(set(left) | set(right))
    n = len(left)
    observed = sum(1 for a, b in zip(left, right) if a == b) / n
    expected = sum((left.count(label) / n) * (right.count(label) / n) for label in labels)
    if expected >= 1.0:
        return 1.0
    return (observed - expected) / (1.0 - expected)


def bootstrap_ci(
    left: list[str], right: list[str], iterations: int = 2000, seed: int = 42
) -> list[float | None]:
    """Percentile bootstrap confidence interval for Cohen's kappa."""
    if not left or len(left) != len(right):
        return [None, None]
    rng = random.Random(seed)
    values: list[float] = []
    for _ in range(iterations):
        indices = [rng.randrange(len(left)) for _ in range(len(left))]
        value = cohen_kappa(
            [left[index] for index in indices],
            [right[index] for index in indices],
        )
        if value == value:  # skip NaN
            values.append(value)
    if not values:
        return [None, None]
    values.sort()
    low = values[max(0, int(0.025 * len(values)) - 1)]
    high = values[min(len(values) - 1, int(0.975 * len(values)))]
    return [low, high]


def jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def load_second_model(path: Path) -> dict[int, dict]:
    records: dict[int, dict] = {}
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "document_id" in record:
                records[int(record["document_id"])] = record
    return records


def primary_outcome(record: dict) -> str:
    outcomes = [signal.get("outcome") for signal in record.get("signals", [])]
    return _primary_outcome(outcomes)


def primary_theme(record: dict) -> str:
    themes: list[str] = []
    for signal in record.get("signals", []):
        row = {
            "triggers": signal.get("triggers") or [],
            "behaviors": signal.get("behaviors") or [],
            "emotions": signal.get("emotions") or [],
            "expectations": signal.get("expectations") or [],
            "outcome": signal.get("outcome") or "unknown",
            "quote": signal.get("quote") or "",
        }
        themes.extend(_match_themes(row))
    return _primary_theme(themes)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", default="data/exports/gold_set_200.csv")
    parser.add_argument("--second", default="data/exports/model_swap_gemini_flash.jsonl")
    parser.add_argument("--output", default="data/exports")
    args = parser.parse_args()

    gold = pd.read_csv(args.gold)
    second = load_second_model(Path(args.second))
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    rows = []
    for _, row in gold.iterrows():
        doc_id = int(row["document_id"])
        record = second.get(doc_id)
        if record is None:
            continue
        second_outcome = primary_outcome(record)
        second_theme = primary_theme(record)
        second_behaviors = sorted(
            {behavior for signal in record.get("signals", []) for behavior in signal.get("behaviors", [])}
        )
        gemini_behaviors = []
        try:
            codes = json.loads(row.get("gemini_all_codes") or "{}")
            if not codes:
                codes = json.loads(row.get("gemini_codes") or "{}")
            gemini_behaviors = sorted(codes.get("behaviors", []))
        except (json.JSONDecodeError, TypeError):
            pass
        rows.append(
            {
                "document_id": doc_id,
                "source": row["source"],
                "gemini_relevant": bool(row["gemini_relevant"]),
                "second_relevant": bool(record.get("relevant")),
                "gemini_outcome": row["gemini_outcome"],
                "second_outcome": second_outcome,
                "gemini_theme": row["gemini_primary_theme"],
                "second_theme": second_theme,
                "gemini_behaviors": gemini_behaviors,
                "second_behaviors": second_behaviors,
                "behavior_jaccard": jaccard(set(gemini_behaviors), set(second_behaviors)),
                "gemini_quote": row["gemini_quote"],
                "second_quotes": [signal.get("quote") for signal in record.get("signals", [])],
                "document_text": row["document_text"],
                "url": row["url"],
            }
        )

    frame = pd.DataFrame(rows)
    if frame.empty:
        print("No overlapping gold-set documents found.")
        return

    relevant_pairs = list(zip(frame["gemini_relevant"].astype(str), frame["second_relevant"].astype(str)))
    relevance_kappa = cohen_kappa([a for a, _ in relevant_pairs], [b for _, b in relevant_pairs])

    known = frame[
        frame["gemini_outcome"].isin(LAPSE_OUTCOMES | CONTINUE_OUTCOMES)
        & frame["second_outcome"].isin(LAPSE_OUTCOMES | CONTINUE_OUTCOMES)
    ]
    outcome_kappa = cohen_kappa(
        known["gemini_outcome"].astype(str).tolist(),
        known["second_outcome"].astype(str).tolist(),
    )

    theme_frame = frame[
        (frame["gemini_theme"] != "other_unclassified")
        | (frame["second_theme"] != "other_unclassified")
    ]
    theme_kappa = cohen_kappa(
        theme_frame["gemini_theme"].astype(str).tolist(),
        theme_frame["second_theme"].astype(str).tolist(),
    )

    behavior_codes = sorted(
        {code for values in frame["gemini_behaviors"] for code in values}
        | {code for values in frame["second_behaviors"] for code in values}
    )
    behavior_agreement = {}
    for code in behavior_codes:
        left = frame["gemini_behaviors"].apply(lambda values: str(code in values)).tolist()
        right = frame["second_behaviors"].apply(lambda values: str(code in values)).tolist()
        behavior_agreement[code] = {
            "kappa": cohen_kappa(left, right),
            "gemini_count": int(sum(value == "True" for value in left)),
            "second_count": int(sum(value == "True" for value in right)),
        }

    first_record = next(iter(second.values()), {})
    agreement = {
        "gold_items": int(len(gold)),
        "compared_items": int(len(frame)),
        "second_provider": first_record.get("provider"),
        "second_model": first_record.get("model"),
        "relevance": {
            "kappa": relevance_kappa,
            "ci95": bootstrap_ci(
                [a for a, _ in relevant_pairs], [b for _, b in relevant_pairs]
            ),
            "gemini_relevant": int(frame["gemini_relevant"].sum()),
            "second_relevant": int(frame["second_relevant"].sum()),
            "both_relevant": int((frame["gemini_relevant"] & frame["second_relevant"]).sum()),
        },
        "outcome": {
            "kappa": outcome_kappa,
            "ci95": bootstrap_ci(
                known["gemini_outcome"].astype(str).tolist(),
                known["second_outcome"].astype(str).tolist(),
            ),
            "compared": int(len(known)),
            "gemini_distribution": dict(Counter(known["gemini_outcome"])),
            "second_distribution": dict(Counter(known["second_outcome"])),
        },
        "primary_theme": {
            "kappa": theme_kappa,
            "ci95": bootstrap_ci(
                theme_frame["gemini_theme"].astype(str).tolist(),
                theme_frame["second_theme"].astype(str).tolist(),
            ),
            "compared": int(len(theme_frame)),
            "gemini_distribution": dict(Counter(theme_frame["gemini_theme"])),
            "second_distribution": dict(Counter(theme_frame["second_theme"])),
        },
        "behaviors": behavior_agreement,
        "mean_behavior_jaccard": float(frame["behavior_jaccard"].mean()),
    }

    (output / "model_swap_agreement.json").write_text(
        json.dumps(agreement, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    disagreements = frame[
        (frame["gemini_relevant"] != frame["second_relevant"])
        | (frame["gemini_outcome"] != frame["second_outcome"])
        | (frame["gemini_theme"] != frame["second_theme"])
    ].copy()
    disagreements.to_csv(
        output / "model_swap_disagreements.csv", index=False, encoding="utf-8-sig"
    )

    print(json.dumps(agreement, indent=2, ensure_ascii=False, default=str))
    print(f"\nDisagreements: {len(disagreements)} -> {output / 'model_swap_disagreements.csv'}")


if __name__ == "__main__":
    main()
