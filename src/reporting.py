"""Shared reporting helpers: data loading, charts, and presentation constants."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from sqlalchemy import select

from .analysis import (
    LAPSE_OUTCOMES,
    code_frequency,
    document_outcomes,
    segment_summary,
    signals_frame,
    source_summary,
    stage_summary,
    theme_summary,
)
from .db import get_session
from .models import Run

PALETTE = {
    "navy": "#17324D",
    "teal": "#1F6F5C",
    "teal_light": "#DCEBE5",
    "sand": "#E8DCC8",
    "coral": "#C96A4B",
    "grey": "#5B6770",
    "light_grey": "#F4F6F5",
    "white": "#FFFFFF",
    "grid": "#D9E2DE",
}

OUTCOME_LABELS = {
    "stopped": "Stopped",
    "paused": "Paused",
    "reduced": "Reduced",
    "withdrew": "Withdrew",
    "returned": "Returned",
    "increased": "Increased",
    "continues": "Continues",
    "unknown": "Unknown",
}

SHORT_NAMES = {
    "positive_continuation": "What keeps SIPs alive",
    "cashflow_shock": "Cash-flow shocks",
    "market_panic": "Market noise",
    "cancellation_friction": "Can't stop or fix it",
    "mandate_friction": "Mandate failures",
    "goal_competition": "Fund/goal confusion",
    "expectation_gap": "Return disappointment",
    "forced_pause": "System-forced pauses",
    "product_confusion": "Product confusion",
    "habit_decay": "Out of sight",
    "other_unclassified": "Other",
}

STAGE_LABELS = {
    "pre_start": "Pre-start",
    "m0_setup": "0–30 days",
    "m3_early": "Month 3",
    "m6_mid": "Month 6",
    "m9_late": "Month 9",
    "post_lapse": "Post-lapse",
    "unknown": "Unknown",
}

SOURCE_KIND_LABELS = {
    "play_store": "Play Store",
    "app_store": "App Store",
    "reddit": "Reddit",
    "forum": "Forums",
    "youtube": "YouTube",
}

STAGE_ORDER = {
    "pre_start": 0,
    "m0_setup": 1,
    "m3_early": 2,
    "m6_mid": 3,
    "m9_late": 4,
    "post_lapse": 5,
    "unknown": 99,
}


def setup_matplotlib() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.titlesize": 15,
            "axes.titleweight": "bold",
            "axes.labelsize": 10,
            "axes.edgecolor": PALETTE["grid"],
            "axes.linewidth": 0.8,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "xtick.color": PALETTE["grey"],
            "ytick.color": PALETTE["grey"],
            "text.color": PALETTE["navy"],
            "figure.facecolor": PALETTE["white"],
            "axes.facecolor": PALETTE["white"],
            "savefig.facecolor": PALETTE["white"],
            "savefig.dpi": 220,
        }
    )


EXPORTS = Path(__file__).resolve().parents[1] / "data" / "exports"


def load_validation() -> dict[str, Any]:
    """Load validation artefacts when they exist, without failing a build."""
    result: dict[str, Any] = {"model_swap": None, "red_team": None}
    for key, name in (
        ("model_swap", "model_swap_agreement.json"),
        ("red_team", "red_team_report.json"),
    ):
        path = EXPORTS / name
        if not path.exists():
            continue
        try:
            result[key] = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
    return result


def load_report_data() -> dict[str, Any]:
    with get_session() as session:
        signals, documents = signals_frame(session)
        documents = document_outcomes(signals, documents)
        summary = theme_summary(signals, documents)
        sources = source_summary(signals)
        stages = stage_summary(signals)
        segments = segment_summary(signals)
        codes = code_frequency(signals)
        run = session.scalars(select(Run).order_by(Run.id.desc())).first()
        run_stats = {
            "id": run.id if run else None,
            "status": run.status if run else None,
            "prompt_version": run.prompt_version if run else None,
            "stats": (run.stats or {}) if run else {},
            "started_at": run.started_at if run else None,
            "finished_at": run.finished_at if run else None,
        }

    facts = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "documents": int(len(documents)),
        "keyword_relevant": int(documents["keyword_relevant"].sum()) if not documents.empty else 0,
        "strict_relevant": int(documents["strict_relevant"].sum()) if not documents.empty else 0,
        "deep_coded": int(documents["deep_coded"].sum()) if not documents.empty else 0,
        "model_relevant": int(documents["model_relevant"].sum()) if not documents.empty else 0,
        "signals": int(len(signals)),
        "signal_documents": int(signals["document_id"].nunique()) if not signals.empty else 0,
        "lapse_signals": int(signals["outcome"].isin(LAPSE_OUTCOMES).sum()) if not signals.empty else 0,
        "continue_signals": int(
            signals["outcome"].isin({"continues", "increased", "returned"}).sum()
        )
        if not signals.empty
        else 0,
        "date_min": str(documents["published_at"].dropna().min()) if not documents.empty else "—",
        "date_max": str(documents["published_at"].dropna().max()) if not documents.empty else "—",
        "sources": int(documents["source"].nunique()) if not documents.empty else 0,
        "run": run_stats,
    }
    return {
        "signals": signals,
        "documents": documents,
        "summary": summary,
        "sources": sources,
        "stages": stages,
        "segments": segments,
        "codes": codes,
        "facts": facts,
        "validation": load_validation(),
    }


def _save(fig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)


def save_theme_scores(summary: pd.DataFrame, path: Path) -> None:
    if summary.empty:
        return
    chart = summary[summary["slug"] != "other_unclassified"].head(10).sort_values(
        "opportunity_score", ascending=True
    )
    fig, ax = plt.subplots(figsize=(8.6, 4.8))
    colors = []
    for _, row in chart.iterrows():
        if row.get("kind") == "protective":
            colors.append(PALETTE["sand"])
        elif row["opportunity_score"] >= chart["opportunity_score"].max() * 0.8:
            colors.append(PALETTE["coral"])
        else:
            colors.append(PALETTE["teal"])
    labels = [SHORT_NAMES.get(slug, name) for slug, name in zip(chart["slug"], chart["name"])]
    bars = ax.barh(labels, chart["opportunity_score"], color=colors, height=0.62)
    for bar, value in zip(bars, chart["opportunity_score"]):
        ax.text(
            value + 1.2,
            bar.get_y() + bar.get_height() / 2,
            f"{value:.0f}",
            va="center",
            fontsize=9,
            color=PALETTE["navy"],
            fontweight="bold",
        )
    ax.set_xlim(0, max(chart["opportunity_score"].max() * 1.18, 10))
    ax.set_xlabel("Opportunity score (0–100)")
    ax.set_title("Where the retention opportunity is", loc="left")
    ax.grid(axis="x", color=PALETTE["grid"], linewidth=0.7, alpha=0.8)
    ax.set_axisbelow(True)
    _save(fig, path)


def save_funnel(facts: dict[str, Any], path: Path) -> None:
    stages = [
        ("Collected", facts["documents"]),
        ("Keyword-relevant", facts["keyword_relevant"]),
        ("Strict SIP/MF", facts["strict_relevant"]),
        ("Deep-coded", facts["deep_coded"]),
        ("Model-relevant", facts["model_relevant"]),
        ("With a signal", facts["signal_documents"]),
    ]
    labels = [label for label, _ in stages]
    values = [value for _, value in stages]
    fig, ax = plt.subplots(figsize=(8.6, 3.6))
    bars = ax.barh(labels[::-1], values[::-1], color=PALETTE["teal"], height=0.58)
    for bar, value in zip(bars, values[::-1]):
        ax.text(
            value + max(values) * 0.012,
            bar.get_y() + bar.get_height() / 2,
            f"{value:,}",
            va="center",
            fontsize=9,
            color=PALETTE["navy"],
            fontweight="bold",
        )
    ax.set_xlim(0, max(values) * 1.18)
    ax.set_xlabel("Documents")
    ax.set_title("From public posts to grounded evidence", loc="left")
    ax.grid(axis="x", color=PALETTE["grid"], linewidth=0.7, alpha=0.8)
    ax.set_axisbelow(True)
    _save(fig, path)


def save_source_mix(documents: pd.DataFrame, path: Path) -> None:
    if documents.empty:
        return
    counts = (
        documents.groupby("source_kind")["document_id"]
        .count()
        .sort_values(ascending=True)
    )
    labels = [SOURCE_KIND_LABELS.get(kind, kind) for kind in counts.index]
    fig, ax = plt.subplots(figsize=(8.6, 3.4))
    bars = ax.barh(labels, counts.values, color=PALETTE["teal"], height=0.58)
    for bar, value in zip(bars, counts.values):
        ax.text(
            value + counts.max() * 0.015,
            bar.get_y() + bar.get_height() / 2,
            f"{value:,}",
            va="center",
            fontsize=9,
            color=PALETTE["navy"],
            fontweight="bold",
        )
    ax.set_xlim(0, counts.max() * 1.18)
    ax.set_xlabel("Documents")
    ax.set_title("Source mix", loc="left")
    ax.grid(axis="x", color=PALETTE["grid"], linewidth=0.7, alpha=0.8)
    ax.set_axisbelow(True)
    _save(fig, path)


def save_stage_lapse(stages: pd.DataFrame, path: Path) -> None:
    if stages.empty:
        return
    chart = stages[stages["known_outcomes"] > 0].copy()
    if chart.empty:
        return
    chart["_stage_order"] = chart["journey_stage"].map(STAGE_ORDER).fillna(99)
    chart = chart.sort_values("_stage_order").head(8)
    labels = [STAGE_LABELS.get(stage, stage) for stage in chart["journey_stage"]]
    fig, ax = plt.subplots(figsize=(8.6, 3.6))
    bars = ax.bar(
        labels,
        chart["lapse_rate"] * 100,
        color=PALETTE["teal"],
        width=0.58,
    )
    for bar, value, known in zip(
        bars, chart["lapse_rate"] * 100, chart["known_outcomes"]
    ):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value + 1.5,
            f"{value:.0f}%  (n={int(known)})",
            ha="center",
            fontsize=8,
            color=PALETTE["navy"],
        )
    ax.set_ylim(0, 108)
    ax.set_ylabel("Lapse rate among known outcomes")
    ax.set_title("Journey stage and lapse", loc="left")
    ax.grid(axis="y", color=PALETTE["grid"], linewidth=0.7, alpha=0.8)
    ax.set_axisbelow(True)
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
    fig.text(
        0.01,
        0.005,
        "n = signals with a resolved outcome. Stage is where the post is set, not a cohort survival curve.",
        fontsize=7,
        color=PALETTE["grey"],
    )
    _save(fig, path)


def save_opportunity_matrix(summary: pd.DataFrame, path: Path) -> None:
    if summary.empty:
        return
    chart = summary[
        (summary["kind"] == "problem") & (summary["outcome_known"])
    ].copy()
    chart["x"] = chart["share_signal_docs"] * 100
    chart["y"] = chart["lapse_rate"] * 100
    chart["size"] = chart["documents"].clip(lower=1) * 18
    fig, ax = plt.subplots(figsize=(8.2, 5.4))
    scatter = ax.scatter(
        chart["x"],
        chart["y"],
        s=chart["size"],
        c=chart["opportunity_score"],
        cmap="YlGnBu",
        edgecolors=PALETTE["navy"],
        linewidths=0.6,
        alpha=0.9,
    )
    label_chart = chart[
        chart["documents"] >= 6
    ].sort_values("opportunity_score", ascending=False).head(8)
    plot_labels = {
        "goal_competition": "Fund/goal",
        "cashflow_shock": "Cash-flow",
        "cancellation_friction": "Can't stop/fix",
        "market_panic": "Market noise",
        "forced_pause": "System pause",
    }
    label_positions = {
        "goal_competition": (10, -16, "left", "top"),
        "cashflow_shock": (10, -16, "left", "top"),
        "cancellation_friction": (-12, 14, "right", "bottom"),
        "market_panic": (12, 8, "left", "bottom"),
        "forced_pause": (10, 12, "left", "bottom"),
    }
    for _, row in label_chart.iterrows():
        dx, dy, align, valign = label_positions.get(
            row["slug"], (8, 8, "left", "bottom")
        )
        ax.annotate(
            plot_labels.get(row["slug"], SHORT_NAMES.get(row["slug"], row["name"])),
            (row["x"], row["y"]),
            xytext=(dx, dy),
            textcoords="offset points",
            ha=align,
            va=valign,
            fontsize=7.2,
            color=PALETTE["navy"],
        )
    ax.set_xlim(-0.5, max(chart["x"].max() * 1.35, 5))
    ax.set_xlabel("Reach: share of signal-bearing documents (%)")
    ax.set_ylabel("Lapse rate among known outcomes (%)")
    ax.set_title("Reach vs lapse association", loc="left")
    ax.grid(color=PALETTE["grid"], linewidth=0.7, alpha=0.8)
    ax.set_axisbelow(True)
    cbar = fig.colorbar(scatter, ax=ax, shrink=0.8)
    cbar.set_label("Opportunity score")
    fig.text(
        0.01,
        0.005,
        "Themes without a resolved outcome are scored in the table but not plotted here.",
        fontsize=7,
        color=PALETTE["grey"],
    )
    _save(fig, path)


def save_outcome_mix(signals: pd.DataFrame, path: Path) -> None:
    if signals.empty:
        return
    counts = signals["outcome"].value_counts()
    labels = [OUTCOME_LABELS.get(label, label.title()) for label in counts.index]
    fig, ax = plt.subplots(figsize=(7.4, 3.2))
    bars = ax.bar(labels, counts.values, color=PALETTE["teal"], width=0.58)
    for bar, value in zip(bars, counts.values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value + counts.max() * 0.02,
            f"{value}",
            ha="center",
            fontsize=9,
            color=PALETTE["navy"],
            fontweight="bold",
        )
    ax.set_ylim(0, counts.max() * 1.18)
    ax.set_ylabel("Signals")
    ax.set_title("Coded outcomes", loc="left")
    ax.grid(axis="y", color=PALETTE["grid"], linewidth=0.7, alpha=0.8)
    ax.set_axisbelow(True)
    _save(fig, path)


def build_all_charts(output_dir: Path) -> dict[str, Path]:
    setup_matplotlib()
    data = load_report_data()
    output_dir.mkdir(parents=True, exist_ok=True)
    charts = {
        "theme_scores": output_dir / "theme_scores.png",
        "funnel": output_dir / "funnel.png",
        "source_mix": output_dir / "source_mix.png",
        "stage_lapse": output_dir / "stage_lapse.png",
        "opportunity_matrix": output_dir / "opportunity_matrix.png",
        "outcome_mix": output_dir / "outcome_mix.png",
    }
    save_theme_scores(data["summary"], charts["theme_scores"])
    save_funnel(data["facts"], charts["funnel"])
    save_source_mix(data["documents"], charts["source_mix"])
    save_stage_lapse(data["stages"], charts["stage_lapse"])
    save_opportunity_matrix(data["summary"], charts["opportunity_matrix"])
    save_outcome_mix(data["signals"], charts["outcome_mix"])
    return charts


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default
