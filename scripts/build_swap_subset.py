"""Build a quota-sized second-model subset from the 200-item gold set.

The free-tier Groq limit is low. This subset keeps every resolved-outcome
document (the outcome kappa is the noisiest dimension) and adds signal-bearing
unknown and no-signal controls so relevance is not evaluated on an all-relevant
sample.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

RESOLVED = {
    "stopped",
    "paused",
    "reduced",
    "withdrew",
    "continues",
    "returned",
    "increased",
}


def take_per_source(frame: pd.DataFrame, per_source: int) -> pd.DataFrame:
    parts = []
    for source_kind in sorted(frame["source_kind"].dropna().unique()):
        pool = frame[frame["source_kind"] == source_kind].sort_values("document_id")
        parts.append(pool.head(per_source))
    return pd.concat(parts, ignore_index=True) if parts else frame.head(0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", default="data/exports/gold_set_200.csv")
    parser.add_argument("--output", default="data/exports/gold_set_swap_100.csv")
    args = parser.parse_args()

    gold = pd.read_csv(args.gold)
    gold["_has_quote"] = gold["gemini_quote"].fillna("").astype(str).str.strip().ne("")

    resolved = gold[gold["gemini_outcome"].isin(RESOLVED)].copy()
    resolved["swap_stratum"] = "resolved"

    unresolved = gold[
        (~gold["document_id"].isin(resolved["document_id"]))
        & gold["_has_quote"]
    ].copy()
    unresolved = unresolved.sort_values("document_id")
    unresolved = take_per_source(unresolved, 2).head(10)
    unresolved["swap_stratum"] = "unknown_signal"

    no_signal = gold[
        (~gold["document_id"].isin(resolved["document_id"]))
        & (~gold["document_id"].isin(unresolved["document_id"]))
        & (~gold["_has_quote"])
    ].copy()
    no_signal = no_signal.sort_values("document_id")
    no_signal = take_per_source(no_signal, 2).head(10)
    no_signal["swap_stratum"] = "no_signal"

    subset = pd.concat([resolved, unresolved, no_signal], ignore_index=True)
    subset = subset.drop(columns=["_has_quote"])
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    subset.to_csv(output, index=False, encoding="utf-8-sig")

    print(f"Wrote {len(subset)} rows to {output}")
    print(
        subset.groupby(["swap_stratum", "source_kind"])
        .size()
        .unstack(fill_value=0)
        .to_string()
    )


if __name__ == "__main__":
    main()
