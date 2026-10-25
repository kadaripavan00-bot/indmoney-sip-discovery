"""INDmoney SIP Discovery Engine dashboard.

Run:
    streamlit run dashboard/app.py

Deploy:
    Push to GitHub → connect to Streamlit Community Cloud → auto-deploys on push
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis import (  # noqa: E402
    LAPSE_OUTCOMES,
    THEMES,
    code_frequency,
    document_outcomes,
    example_quotes,
    segment_summary,
    signals_frame,
    source_summary,
    stage_summary,
    theme_summary,
)
from src.db import get_session  # noqa: E402
from src.live_llm import get_engine  # noqa: E402
from src.models import Run  # noqa: E402

st.set_page_config(
    page_title="INDmoney SIP Discovery Engine",
    page_icon="🔎",
    layout="wide",
    initial_sidebar_state="expanded",
)

ACCENT = "#1F6F5C"
MUTED = "#5B6770"
PROTECTIVE = "#C9A227"


def load_validation() -> tuple[dict, dict]:
    exports = ROOT / "data" / "exports"
    result = []
    for name in ("model_swap_agreement.json", "red_team_report.json"):
        path = exports / name
        if not path.exists():
            result.append({})
            continue
        try:
            result.append(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            result.append({})
    return result[0], result[1]


@st.cache_data(show_spinner=False)
def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    with get_session() as session:
        signals, documents = signals_frame(session)
    documents = document_outcomes(signals, documents)
    summary = theme_summary(signals, documents)
    return signals, documents, summary


@st.cache_data(show_spinner=False)
def load_run_stats() -> dict:
    with get_session() as session:
        run = session.query(Run).order_by(Run.id.desc()).first()
        if run is None:
            return {}
        return {
            "id": run.id,
            "status": run.status,
            "prompt_version": run.prompt_version,
            "stats": run.stats or {},
            "started_at": run.started_at,
            "finished_at": run.finished_at,
        }


def as_display_list(value) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "—"
    return str(value) if value else "—"


def metric_row(signals: pd.DataFrame, documents: pd.DataFrame) -> None:
    deep_coded = int(documents["deep_coded"].sum()) if "deep_coded" in documents else 0
    relevant = int(documents["model_relevant"].sum()) if "model_relevant" in documents else 0
    cols = st.columns(5)
    cols[0].metric("Corpus", f"{len(documents):,}")
    cols[1].metric("Deep-coded", f"{deep_coded:,}")
    cols[2].metric("Model-relevant", f"{relevant:,}")
    cols[3].metric("Signals", f"{len(signals):,}")
    cols[4].metric("Docs with signals", f"{signals['document_id'].nunique():,}" if not signals.empty else "0")


def sidebar_filters(signals: pd.DataFrame) -> pd.DataFrame:
    if signals.empty:
        return signals
    st.sidebar.header("Filters")
    sources = sorted(signals["source"].dropna().unique().tolist())
    selected_sources = st.sidebar.multiselect("Source", sources, default=sources)
    themes = sorted(
        {theme for values in signals["themes"] for theme in values}
        if len(signals)
        else set()
    )
    selected_themes = st.sidebar.multiselect("Theme", themes, default=themes)
    outcomes = sorted(signals["outcome"].dropna().unique().tolist())
    selected_outcomes = st.sidebar.multiselect("Outcome", outcomes, default=outcomes)
    stages = sorted(signals["journey_stage"].dropna().unique().tolist())
    selected_stages = st.sidebar.multiselect("Journey stage", stages, default=stages)

    filtered = signals[
        signals["source"].isin(selected_sources)
        & signals["outcome"].isin(selected_outcomes)
        & signals["journey_stage"].isin(selected_stages)
    ].copy()
    if selected_themes:
        filtered = filtered[
            filtered["themes"].apply(
                lambda values: bool(set(values) & set(selected_themes))
            )
        ]
    st.sidebar.caption(f"{len(filtered):,} of {len(signals):,} signals")
    return filtered


def overview_tab(signals: pd.DataFrame, documents: pd.DataFrame, summary: pd.DataFrame) -> None:
    metric_row(signals, documents)
    st.markdown("### Where the retention opportunity is")
    st.caption(
        "Opportunity score combines reach, lapse lift, evidence strength, solvability, and effort. "
        "It is a prioritisation heuristic, not a causal estimate."
    )
    if summary.empty:
        st.info("No themes yet. Run extraction and analysis first.")
        return

    chart = summary[summary["slug"] != "other_unclassified"].head(10).copy()
    chart = chart.sort_values("opportunity_score", ascending=True)
    fig = px.bar(
        chart,
        x="opportunity_score",
        y="name",
        orientation="h",
        color="kind",
        color_discrete_map={
            "problem": ACCENT,
            "protective": PROTECTIVE,
            "other": "#9AA7A0",
        },
        labels={
            "opportunity_score": "Opportunity score (0-100)",
            "name": "",
            "kind": "Theme type",
        },
        hover_data={
            "signals": True,
            "documents": True,
            "lapse_display": True,
            "lift_display": True,
            "score_note": True,
        },
    )
    fig.update_layout(
        height=430,
        margin=dict(l=10, r=20, t=10, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "n/a means the theme has no resolved outcome in public posts; its score uses a modest friction prior, "
        "not an observed lapse rate."
    )

    display = summary[
        [
            "rank",
            "name",
            "signals",
            "documents",
            "share_signal_docs",
            "lapse_display",
            "lift_display",
            "opportunity_score",
        ]
    ].copy()
    display["share_signal_docs"] = display["share_signal_docs"].map(lambda value: f"{value:.1%}")
    display.columns = [
        "Rank",
        "Theme",
        "Signals",
        "Docs",
        "Share of signal docs",
        "Lapse rate",
        "Lift vs baseline",
        "Score",
    ]
    st.dataframe(display, width="stretch", hide_index=True)

    st.markdown("### Funnel")
    funnel = pd.DataFrame(
        [
            ("Collected documents", len(documents)),
            ("Keyword-relevant", int(documents["keyword_relevant"].sum())),
            ("Strict SIP/MF candidates", int(documents["strict_relevant"].sum())),
            ("Deep-coded", int(documents["deep_coded"].sum())),
            ("Model-relevant", int(documents["model_relevant"].sum())),
            ("Documents with a grounded signal", signals["document_id"].nunique() if not signals.empty else 0),
        ],
        columns=["Stage", "Documents"],
    )
    st.dataframe(funnel, width="stretch", hide_index=True)


def themes_tab(signals: pd.DataFrame, summary: pd.DataFrame) -> None:
    st.markdown("### Theme deep dives")
    if summary.empty or signals.empty:
        st.info("No themes yet.")
        return
    theme_names = summary["name"].tolist()
    selected = st.selectbox("Choose a theme", theme_names)
    row = summary[summary["name"] == selected].iloc[0]
    cols = st.columns(4)
    cols[0].metric("Signals", int(row["signals"]))
    cols[1].metric("Documents", int(row["documents"]))
    cols[2].metric("Lapse rate", row["lapse_display"])
    cols[3].metric("Opportunity score", f"{row['opportunity_score']:.1f}")
    st.markdown(f"**Definition.** {row['definition']}")
    st.markdown(
        f"**Lift vs baseline.** {row['lift_display']}  ·  "
        f"**Evidence strength.** {row['evidence_strength']:.2f}"
    )
    if not bool(row.get("outcome_known", False)):
        st.caption(
            "No resolved outcome for this theme in public posts. The opportunity score uses a "
            "modest friction prior; do not read it as an observed lapse rate."
        )
    st.markdown("**Suggested interventions**")
    for intervention in row["interventions"]:
        st.markdown(f"- {intervention}")
    st.markdown("**Representative evidence**")
    examples = example_quotes(signals, row["slug"], limit=5)
    for example in examples:
        st.markdown(f"> {example['quote']}")
        st.caption(
            f"{example['source']} · outcome={example['outcome']} · stage={example['journey_stage']} · "
            f"confidence={example['confidence']} · [source link]({example['url']})"
        )


def signals_tab(signals: pd.DataFrame) -> None:
    st.markdown("### Grounded signal explorer")
    if signals.empty:
        st.info("No signals yet.")
        return
    search = st.text_input("Search quote, trigger, or source", "")
    view = signals.copy()
    if search:
        needle = search.lower()
        view = view[
            view.apply(
                lambda row: needle
                in " ".join(
                    [
                        str(row.get("quote", "")),
                        str(row.get("source", "")),
                        " ".join(row.get("triggers", [])),
                        " ".join(row.get("behaviors", [])),
                        " ".join(row.get("themes", [])),
                    ]
                ).lower(),
                axis=1,
            )
        ]
    display = view[
        [
            "signal_id",
            "source",
            "quote",
            "outcome",
            "journey_stage",
            "confidence",
            "themes",
            "url",
        ]
    ].copy()
    display["themes"] = display["themes"].map(as_display_list)
    display["quote"] = display["quote"].map(lambda value: value[:400] + ("…" if len(value) > 400 else ""))
    display.columns = ["ID", "Source", "Quote", "Outcome", "Stage", "Confidence", "Themes", "URL"]
    st.dataframe(
        display,
        width="stretch",
        hide_index=True,
        column_config={"URL": st.column_config.LinkColumn("Source link")},
    )
    st.download_button(
        "Download filtered evidence (CSV)",
        data=display.to_csv(index=False).encode("utf-8-sig"),
        file_name="indmoney_evidence_filtered.csv",
        mime="text/csv",
    )


def segments_tab(signals: pd.DataFrame) -> None:
    st.markdown("### Segment and stage patterns")
    if signals.empty:
        st.info("No signals yet.")
        return
    segments = segment_summary(signals)
    stages = stage_summary(signals)
    sources = source_summary(signals)

    left, right = st.columns(2)
    with left:
        st.markdown("**Lapse rate by journey stage**")
        if not stages.empty:
            stage_plot = stages[stages["known_outcomes"] > 0].sort_values("signals", ascending=False)
            if not stage_plot.empty:
                fig = px.bar(
                    stage_plot,
                    x="journey_stage",
                    y="lapse_rate",
                    color="lapse_rate",
                    color_continuous_scale=["#DCEBE5", ACCENT],
                    labels={"journey_stage": "", "lapse_rate": "Lapse rate"},
                )
                fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10), showlegend=False)
                st.plotly_chart(fig, width="stretch")
            else:
                st.caption("No stage has a resolved outcome yet.")
            stage_display = stages[
                ["journey_stage", "signals", "documents", "lapse_display", "known_outcomes", "top_theme"]
            ].copy()
            stage_display.columns = ["Stage", "Signals", "Docs", "Lapse rate", "Known outcomes", "Top theme"]
            st.dataframe(stage_display, width="stretch", hide_index=True)
        else:
            st.caption("No stage evidence yet.")
    with right:
        st.markdown("**Lapse rate by source**")
        if not sources.empty:
            source_plot = sources[sources["known_outcomes"] > 0].sort_values("signals", ascending=False)
            if not source_plot.empty:
                fig = px.bar(
                    source_plot,
                    x="source",
                    y="lapse_rate",
                    color="lapse_rate",
                    color_continuous_scale=["#DCEBE5", ACCENT],
                    labels={"source": "", "lapse_rate": "Lapse rate"},
                )
                fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10), showlegend=False)
                st.plotly_chart(fig, width="stretch")
            else:
                st.caption("No source has a resolved outcome yet.")
            source_display = sources[
                ["source", "signals", "documents", "lapse_display", "known_outcomes", "top_theme"]
            ].copy()
            source_display.columns = ["Source", "Signals", "Docs", "Lapse rate", "Known outcomes", "Top theme"]
            st.dataframe(source_display, width="stretch", hide_index=True)
        else:
            st.caption("No source summary yet.")

    st.markdown("**Segment table**")
    if not segments.empty:
        display = segments[
            [
                "segment_field",
                "segment_value",
                "signals",
                "share_signals",
                "lapse_display",
                "known_outcomes",
            ]
        ].copy()
        display["share_signals"] = display["share_signals"].map(lambda value: f"{value:.1%}")
        display.columns = ["Field", "Value", "Signals", "Share", "Lapse rate", "Known outcomes"]
        st.dataframe(display, width="stretch", hide_index=True)
    else:
        st.caption("No segment evidence yet. Segment quotes are verified separately from behavioural quotes.")


def method_tab(signals: pd.DataFrame, documents: pd.DataFrame) -> None:
    st.markdown("### How the engine works")
    st.markdown(
        """
        1. **Collect** public posts from six sources: Play Store, App Store, Reddit,
           YouTube comments, ValuePickr, and TradingQ&A.
        2. **Normalize and deduplicate** text, then apply a broad relevance filter and a
           strict SIP/mutual-fund candidate filter.
        3. **Extract** signals with a free-tier LLM. The model must quote the source,
           then assign only the codes the quote supports.
        4. **Ground** every code deterministically: quote verification, sentence-level
           keyword support, first-person action checks, attempt-vs-completed action
           checks, and separate segment-quote verification.
        5. **Quantify** themes, prevalence, lapse lift, segments, stages, and
           opportunity scores with SQL/Python, not the LLM.
        6. **Validate** with a 200-item gold set, inter-coder agreement, a model swap,
           and a red-team review.
        """
    )
    swap, red_team = load_validation()
    if swap or red_team:
        st.markdown("### Validation status")
        cols = st.columns(3)
        for column, key, label in zip(
            cols,
            ("relevance", "outcome", "primary_theme"),
            ("Relevance κ", "Outcome κ", "Theme κ"),
        ):
            block = (swap or {}).get(key) or {}
            value = block.get("kappa")
            column.metric(label, f"{value:.2f}" if isinstance(value, (int, float)) and value == value else "n/a")
        st.caption(
            f"Model swap: {swap.get('compared_items', 'n/a')} quota-sized subset items compared with "
            f"{swap.get('second_model', 'a second model')}. "
            f"Red team: {red_team.get('passed', 'n/a')}/{red_team.get('tests', 'n/a')} tests pass. "
            "Kappa is agreement with the primary model, not human truth."
        )

    st.markdown("### Run statistics")
    run = load_run_stats()
    if not run:
        st.caption("No extraction run yet.")
    else:
        stats = run.get("stats", {})
        cols = st.columns(4)
        cols[0].metric("Run", run["id"])
        cols[1].metric("Prompt", run.get("prompt_version", "—"))
        cols[2].metric("Status", run.get("status", "—"))
        cols[3].metric(
            "Signals",
            stats.get("signals_inserted", 0),
        )
        st.json(
            {
                key: stats.get(key)
                for key in (
                    "docs_processed",
                    "docs_relevant",
                    "signals_inserted",
                    "quote_rejections",
                    "grounding_drops",
                    "validation_errors",
                    "batch_failures",
                    "usage",
                )
                if key in stats
            }
        )
    st.markdown("### Guardrails")
    st.markdown(
        """
        - **No specific funds or stocks.** The engine analyses experiences and
          proposes product/workflow interventions, never a fund recommendation.
        - **No fear, FOMO, or urgency.** Interventions use clarity, flexibility,
          progress, and human support.
        - **Public data only.** No internal analytics, CRM records, or primary
          interviews are used.
        - **Quotes are verified.** A signal without an exact source quote is dropped.
        - **The LLM does not count.** Counts, prevalence, statistics, and opportunity
          scores are deterministic.
        """
    )


def rag_tab(signals: pd.DataFrame) -> None:
    st.markdown("### 🤖 Ask the Evidence (RAG)")
    st.caption("Ask any question about the grounded evidence. The LLM retrieves relevant signals and answers with citations.")

    if signals.empty:
        st.warning("No signals loaded. Run extraction first.")
        return

    question = st.text_input(
        "Your question",
        placeholder="e.g., What are the main reasons people stop SIPs in month 3? How do cash-flow shocks differ from market panic?",
    )

    if st.button("Ask", type="primary", disabled=not question.strip()):
        with st.spinner("Searching evidence and generating answer..."):
            engine = get_engine()
            result = engine.rag_answer(question, k=8)

        st.markdown("#### Answer")
        st.markdown(result["answer"])

        if result["citations"]:
            st.markdown("#### Citations")
            for i, cite in enumerate(result["citations"], 1):
                with st.expander(f"Signal {cite['signal_id']} · {cite['source']} · {cite.get('outcome', 'unknown')} (sim={cite['similarity']:.2f})"):
                    st.markdown(f"> {cite['quote']}")
                    st.caption(f"Themes: {', '.join(cite.get('themes', []))} | Stage: {cite.get('journey_stage', 'unknown')} | [Source]({cite.get('url', '#')})")


def live_extract_tab() -> None:
    st.markdown("### ⚡ Live Extraction")
    st.caption("Paste any review, comment, or forum post. The engine extracts grounded signals in real-time with quote verification.")

    text = st.text_area(
        "Input text",
        height=200,
        placeholder="Paste an App Store review, Reddit comment, YouTube comment, or forum post about SIPs/mutual funds...",
    )

    if st.button("Extract Signals", type="primary", disabled=not text.strip()):
        with st.spinner("Running live extraction..."):
            engine = get_engine()
            result = engine.live_extract(text)

        if result.get("error"):
            st.error(result["error"])
            return

        signals = result.get("signals", [])
        st.metric("Signals extracted", len(signals))

        if not signals:
            st.info("No grounded signals found in this text.")
            return

        for i, sig in enumerate(signals):
            with st.expander(f"Signal {i+1}: {sig.get('primary_theme', 'unknown')} · {sig.get('outcome', 'unknown')}", expanded=True):
                cols = st.columns(2)
                with cols[0]:
                    st.markdown(f"**Triggers:** {', '.join(sig.get('triggers', [])) or '—'}")
                    st.markdown(f"**Behaviors:** {', '.join(sig.get('behaviors', [])) or '—'}")
                    st.markdown(f"**Emotions:** {', '.join(sig.get('emotions', [])) or '—'}")
                with cols[1]:
                    st.markdown(f"**Expectations:** {', '.join(sig.get('expectations', [])) or '—'}")
                    st.markdown(f"**Themes:** {', '.join(sig.get('themes', [])) or '—'}")
                    st.markdown(f"**Outcome:** {sig.get('outcome', 'unknown')}")
                if sig.get("quote"):
                    verified = "✅ Verified" if sig.get("quote_verified") else "⚠️ Not verified"
                    st.markdown(f"**Quote:** {verified}")
                    st.markdown(f"> {sig['quote']}")
                st.caption(f"Confidence: {sig.get('confidence', 'unknown')}")


def theme_narrative_tab(signals: pd.DataFrame, summary: pd.DataFrame) -> None:
    st.markdown("### 📖 Theme Narrative Summaries")
    st.caption("Generate a structured narrative summary for any theme using the LLM, grounded in the theme's evidence.")

    if summary.empty or signals.empty:
        st.info("No themes yet.")
        return

    theme_names = summary["name"].tolist()
    selected = st.selectbox("Choose a theme", theme_names, key="narrative_theme")

    if st.button("Generate Narrative", type="primary"):
        row = summary[summary["name"] == selected].iloc[0]
        with st.spinner("Generating narrative summary..."):
            engine = get_engine()
            narrative = engine.theme_narrative(row["slug"], signals)
        st.markdown(narrative)


def segment_comparison_tab(signals: pd.DataFrame) -> None:
    st.markdown("### 🔍 Segment Comparison")
    st.caption("Compare patterns across user segments (income stability, age, goal type, influence, etc.) using LLM analysis.")

    if signals.empty:
        st.info("No signals yet.")
        return

    segment_fields = ["income_stability", "age_band", "goal_type", "influence", "source_of_money", "ticket_size"]
    selected_field = st.selectbox("Segment field", segment_fields)

    # Get available values for this field
    values = set()
    for cues in signals["segment_cues"].dropna():
        if isinstance(cues, dict) and cues.get(selected_field):
            values.add(cues[selected_field])
    available = sorted([v for v in values if v and v != "unknown"])

    if not available:
        st.warning(f"No segment data available for {selected_field}.")
        return

    selected_values = st.multiselect("Select values to compare", available, default=available[:3] if len(available) >= 3 else available)

    if st.button("Compare Segments", type="primary", disabled=len(selected_values) < 2):
        with st.spinner("Analyzing segment differences..."):
            engine = get_engine()
            comparison = engine.segment_comparison(selected_field, selected_values, signals)
        st.markdown(comparison)


def main() -> None:
    st.title("INDmoney SIP Discovery Engine")
    st.caption(
        "Why first-time Indian mutual-fund investors lapse by month 12 — and where "
        "the retention opportunity is. Public data only; no fund recommendations."
    )

    signals, documents, summary = load_data()
    if signals.empty:
        st.warning("No current signals found. Run the extraction pipeline first.")
        return

    filtered = sidebar_filters(signals)

    tab_overview, tab_themes, tab_signals, tab_segments, tab_method, tab_rag, tab_live, tab_narrative, tab_segcomp = st.tabs(
        [
            "Overview",
            "Themes",
            "Signals",
            "Segments & stages",
            "Method & guardrails",
            "🤖 Ask Evidence (RAG)",
            "⚡ Live Extract",
            "📖 Theme Narratives",
            "🔍 Segment Compare",
        ]
    )

    with tab_overview:
        overview_tab(filtered, documents, summary)
    with tab_themes:
        themes_tab(filtered, summary)
    with tab_signals:
        signals_tab(filtered)
    with tab_segments:
        segments_tab(filtered)
    with tab_method:
        method_tab(filtered, documents)
    with tab_rag:
        rag_tab(filtered)
    with tab_live:
        live_extract_tab()
    with tab_narrative:
        theme_narrative_tab(filtered, summary)
    with tab_segcomp:
        segment_comparison_tab(filtered)


if __name__ == "__main__":
    main()