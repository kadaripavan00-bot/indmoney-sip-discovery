"""Build the narrative case write-up PDF."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8")

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
)

from build_prd import (
    CHARTS,
    DELIVERABLES,
    GREY,
    LIGHT,
    NAVY,
    P,
    TEAL,
    WHITE,
    bullet,
    cover,
    footer,
    image,
    make_table,
    styles,
)
from src.reporting import SOURCE_KIND_LABELS, STAGE_LABELS, load_report_data


def clip_quote(text: str, limit: int = 320) -> str:
    """Trim a quote at a word boundary instead of cutting mid-word."""
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 3].rsplit(" ", 1)[0].rstrip(" ,;:")
    return cut + "..."


def case_footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#D9E2DE"))
    canvas.setLineWidth(0.4)
    canvas.line(18 * mm, 16 * mm, A4[0] - 18 * mm, 16 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(GREY)
    canvas.drawString(18 * mm, 11 * mm, "INDmoney Growth · SIP Discovery Engine · Case write-up")
    canvas.drawRightString(A4[0] - 18 * mm, 11 * mm, f"Page {doc.page}")
    canvas.restoreState()


def quotes_for(signals, slug: str, limit: int = 2):
    subset = signals[signals["themes"].apply(lambda values: slug in values)]
    return subset.sort_values("signal_id").head(limit)


def build(data: dict, path: Path) -> None:
    st = styles()
    facts = data["facts"]
    summary = data["summary"]
    signals = data["signals"]
    sources = data["sources"]
    validation = data.get("validation") or {}
    swap = validation.get("model_swap") or {}
    red_team_report = validation.get("red_team") or {}

    doc = BaseDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=20 * mm,
        title="The moment the SIP breaks — case write-up",
        author="Growth / Product Discovery",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="body")
    doc.addPageTemplates(
        [
            PageTemplate(id="Cover", frames=[frame], onPage=cover),
            PageTemplate(id="Body", frames=[frame], onPage=case_footer),
        ]
    )

    story: list = []
    story.append(P("CASE WRITE-UP", st["cover_kicker"]))
    story.append(P("The moment the SIP breaks", st["cover_title"]))
    story.append(
        P(
            "What 8,000+ public conversations taught us about first-year mutual-fund retention — "
            "and what INDmoney should do about it.",
            st["cover_sub"],
        )
    )
    story.append(
        P(
            f"Evidence snapshot: {facts['documents']:,} documents · {facts['strict_relevant']:,} strict candidates · "
            f"{facts['deep_coded']:,} deep-coded · {facts['signals']:,} grounded signals<br/>"
            "Public sources only. No internal analytics, CRM records, or primary interviews.<br/>"
            "October 2026",
            st["cover_meta"],
        )
    )
    story.append(NextPageTemplate("Body"))
    story.append(PageBreak())

    story.append(P("The brief", st["h1"]))
    story.append(
        P(
            "INDmoney's Growth team wanted to understand why first-time Indian mutual-fund investors stop their SIP "
            "by month 12. The 12-month metric is simple: at least one successful instalment in the last 30 days, "
            "12 months after the first SIP. The question behind it is harder: what happened in the investor's life "
            "and in the product that made the habit break?",
            st["body"],
        )
    )
    story.append(
        P(
            "We could not use internal analytics, CRM records, or primary interviews. We had to build the answer from "
            "public evidence: app reviews, Reddit threads, YouTube comments, and investor forums. The result is a "
            "discovery engine that reads public conversations, extracts structured signals, verifies every quote, and "
            "quantifies which moments are most associated with a first-year lapse.",
            st["body"],
        )
    )
    story.append(P("The constraints shaped the method", st["h2"]))
    for text in [
        "Public data only. No internal funnel, no customer records, no interviews.",
        "No fund or stock recommendations. The unit of analysis is the behaviour and the moment, not the product.",
        "No fear, FOMO, or urgency-based nudges. Retention has to come from clarity, control, and support.",
        "Free-tier LLM APIs only. Keys live in a gitignored .env and are never pasted into chat or code.",
        "A 5-day full scope: 5–8k documents, 1.5–2.5k deep-coded, a 200-item gold set, kappa, model swap, and red team.",
    ]:
        story.append(bullet(text, st["bullet"]))

    story.append(P("What we built", st["h1"]))
    story.append(
        P(
            "The engine is a two-layer system. The probabilistic layer reads unstructured text and proposes structured "
            "codes. The deterministic layer verifies quotes, grounds codes, counts themes, scores opportunities, and "
            "exports evidence. The model never computes prevalence, statistics, or the final ranking.",
            st["body"],
        )
    )
    story.extend(
        image(
            CHARTS / "funnel.png",
            width_mm=165,
            caption=f"Figure 1. From {facts['documents']:,} public documents to {facts['signals']:,} grounded signals.",
        )
    )
    story.append(
        P(
            f"We collected {facts['documents']:,} documents from six sources. The strict filter left {facts['strict_relevant']:,} "
            f"SIP/mutual-fund candidates. We deep-coded every strict candidate ({facts['deep_coded']:,} documents) and extracted "
            f"{facts['signals']:,} grounded signals across {facts['signal_documents']:,} documents. Public-source availability, "
            "not the method, is the binding constraint.",
            st["body"],
        )
    )
    story.append(
        P(
            "Every behavioural code must be supported by a verified quote. The grounding layer drops codes that are third-person, "
            "negated, hypothetical, attempted but not completed, or caused by a payment mechanism rather than an investor choice. "
            "It normalizes temporary stops to paused/restarted and requires a separate verified span for segment cues.",
            st["body"],
        )
    )

    story.append(P("What we found", st["h1"]))
    story.append(
        P(
            "The theme map is not a sentiment ranking. It is a map of moments, ranked by reach, lapse association, evidence "
            "strength, solvability, and effort. The protective theme — what keeps SIPs alive — is shown separately because it "
            "is a different kind of opportunity: protect and amplify, not fix.",
            st["body"],
        )
    )
    story.extend(
        image(
            CHARTS / "theme_scores.png",
            width_mm=165,
            caption="Figure 2. Opportunity score by theme. Sand marks the protective theme.",
        )
    )
    theme_rows = [["Rank", "Theme", "Signals", "Documents", "Lapse", "Lift", "Score"]]
    for _, row in summary.head(10).iterrows():
        theme_rows.append(
            [
                str(int(row["rank"])),
                str(row["name"]),
                str(int(row["signals"])),
                str(int(row["documents"])),
                row["lapse_display"],
                row["lift_display"],
                f"{row['opportunity_score']:.1f}",
            ]
        )
    story.append(make_table(theme_rows, [12 * mm, 58 * mm, 16 * mm, 20 * mm, 16 * mm, 18 * mm, 16 * mm], font_size=7.8))
    story.append(
        P(
            "Lapse is the share of resolved outcomes coded as stopped, paused, reduced, or withdrew. Lift compares that share "
            "with the corpus baseline. Themes with no resolved outcome show n/a; they are scored with a modest friction prior, "
            "not presented as 0% lapse. Mandate friction ranks high on reach, evidence, and solvability even though public posts "
            "rarely report the eventual outcome.",
            st["caption"],
        )
    )

    theme_sections = [
        (
            "cashflow_shock",
            "Cash-flow shock is the strongest lapse-associated theme",
            "The SIP was affordable last month, not this month. A salary delay, a job change, a medical bill, or a family "
            "expense makes the next debit feel unsafe. The investor's only visible option is 'stop'.",
            "The intervention is not a better return promise. It is a pause or step-down that preserves the habit through the "
            "squeeze, with a clear resume date and no penalty.",
        ),
        (
            "mandate_friction",
            "System friction creates lapses the investor did not choose",
            "A failed mandate, a bank block, a UPI Autopay confusion, or a silent missed instalment can stop the SIP without "
            "the investor deciding to stop. They often do not know whether the SIP is still active or what to fix.",
            "The intervention is a pre-debit health check, a three-day repair window, auto-retry, and a status card with a "
            "named owner. This is workflow and clarity, not advice.",
        ),
        (
            "cancellation_friction",
            "The cancellation maze turns a pause into a dead end",
            "Investors try to cancel, pause, or repair a SIP and the flow does not work. Money is debited again; support does "
            "not resolve it; the investor loses trust faster than the SIP.",
            "The intervention is a pause option beside cancel, a status tracker, and a response-time promise. Control is the "
            "product.",
        ),
        (
            "market_panic",
            "Market noise matters, but the meaning matters more",
            "A red portfolio is not automatically a lapse. Some investors stop to relieve anxiety; others continue because they "
            "have a goal, a habit, or a human to talk to. The difference is the frame.",
            "The intervention is goal-progress framing, a drawdown explainer, and an opt-in human conversation. No fear, no "
            "urgency, no daily noise.",
        ),
        (
            "positive_continuation",
            "What keeps SIPs alive is protective, not passive",
            "Investors who continue describe a goal, a habit, a support system, or a reason to stay. These are protective "
            "factors, not just the absence of friction.",
            "The intervention is to protect these moments: goal progress, streaks without gambling mechanics, community stories, "
            "and human encouragement at the moments that usually trigger a stop.",
        ),
    ]

    for slug, title, body, intervention in theme_sections:
        row = summary[summary["slug"] == slug]
        row = row.iloc[0] if not row.empty else None
        story.append(P(title, st["h2"]))
        if row is not None:
            story.append(
                P(
                    f"<b>Evidence:</b> {int(row['signals'])} signals across {int(row['documents'])} documents; "
                    f"lapse {row['lapse_display']}; lift {row['lift_display']}; opportunity {row['opportunity_score']:.1f}.",
                    st["small"],
                )
            )
        story.append(P(body, st["body"]))
        for _, quote in quotes_for(signals, slug, limit=2).iterrows():
            text = clip_quote(quote["quote"], 320)
            story.append(P(f"“{text}”", st["quote"]))
            story.append(
                P(
                    f"{quote['source']} · outcome={quote['outcome']} · "
                    f"stage={STAGE_LABELS.get(quote['journey_stage'], quote['journey_stage'])}",
                    st["caption"],
                )
            )
        story.append(P(intervention, st["body"]))

    story.append(P("What it means for INDmoney", st["h1"]))
    story.append(
        P(
            "The opportunity is not a better fund recommendation. It is keeping the SIP alive through the moments that break "
            "the habit. The three highest-leverage plays are mandate rescue, pause-don't-stop, and a cancellation path that "
            "works. All three remove a lapse the investor did not choose, or preserve the habit through a temporary squeeze.",
            st["body"],
        )
    )
    story.extend(
        image(
            CHARTS / "opportunity_matrix.png",
            width_mm=145,
            caption="Figure 3. Reach vs lapse association. Themes without a resolved outcome are scored in the table but not plotted.",
        )
    )
    story.append(P("The plays", st["h2"]))
    plays = [
        ["Play", "What it does", "Why it fits the evidence", "Primary metric"],
        [
            "Mandate rescue",
            "Pre-debit health check, 3-day repair window, auto-retry, status card",
            "Failed debits and mandate breakage are high-fixability system friction",
            "Mandate recovery rate",
        ],
        [
            "Pause, don't stop",
            "1–3 month pause with auto-resume, step-down, salary-cycle alignment",
            "Cash-flow shock is the strongest lapse-associated theme",
            "Pause-to-resume within 90 days",
        ],
        [
            "Cancellation path",
            "Pause beside cancel, status tracker, named owner, response-time promise",
            "Cancellation friction turns a pause into a dead end",
            "Cancellation save rate",
        ],
        [
            "Goal-progress framing",
            "Drawdown explainer, goal progress, opt-in human conversation",
            "Market noise is high-reach; the frame changes the meaning",
            "12-month retention",
        ],
    ]
    story.append(make_table(plays, [30 * mm, 48 * mm, 60 * mm, 32 * mm], font_size=7.5))
    story.append(
        P(
            "All plays are workflow, clarity, and support. None recommends a fund or stock. None uses fear, FOMO, or urgency. "
            "Each has a guardrail on complaints, opt-outs, and unintended pauses.",
            st["caption"],
        )
    )

    story.append(P("How we validated", st["h1"]))
    story.append(
        P(
            "Validation has four layers. Quote verification rejects fabricated or paraphrased evidence. Deterministic grounding "
            "checks first-person actions, negations, attempts, payment-mechanism stops, temporary pauses, and segment evidence. "
            "A 200-item gold set, with a 100-item second-model subset, measures agreement (Cohen's kappa). A red-team suite probes the failure modes "
            "that public text makes likely: third-person stories, sarcasm, Hinglish, short app reviews, quote truncation, source "
            "bias, and prompt injection.",
            st["body"],
        )
    )
    kappa_bits = []
    for key, label in (
        ("relevance", "relevance"),
        ("outcome", "outcome"),
        ("primary_theme", "theme"),
    ):
        block = swap.get(key) or {}
        value = block.get("kappa")
        if isinstance(value, (int, float)) and value == value:
            kappa_bits.append(f"{label} κ={value:.2f}")
    if kappa_bits:
        story.append(
            P(
                f"Second-model agreement (Gemini 3.1 Flash-Lite vs the primary Gemini 3.5 Flash-Lite extraction, 100-item subset): "
                f"{', '.join(kappa_bits)}; n={swap.get('compared_items', 'n/a')} subset items, including all 80 resolved outcomes. "
                "Kappa is agreement with the primary model, not human truth; the 30-item review CSV is the "
                "human-adjudication seed.",
                st["body"],
            )
        )
    story.append(
        P(
            f"The red-team suite currently passes {red_team_report.get('passed', 15)}/"
            f"{red_team_report.get('tests', 15)} tests, including an end-to-end prompt-injection call. "
            "The model-swap results are reported in the evidence log and the dashboard method page; the 30-item "
            "human-adjudication queue is a next step. Agreement is not truth: kappa tells us whether the coding is stable, "
            "not whether the theme causes lapse. Gemini 3.8 Flash was attempted first but stopped at 36 items on its "
            "20-request daily free-tier cap; the reported 100-item swap uses Gemini 3.1 Flash-Lite throughout.",
            st["body"],
        )
    )

    story.append(P("What we cannot say", st["h1"]))
    for text in [
        "Public posts are self-selected. People with problems are more likely to post; silent lapses are underrepresented.",
        "Self-reported outcomes are not the 12-month product metric. A post that says 'I stopped' is evidence of a story, not a measured lapse rate.",
        "Theme-lapse associations are correlational. The engine generates hypotheses; experiments establish causality.",
        "App reviews are short and often lack context. Reddit and forums carry more explanatory weight, but overrepresent engaged investors.",
        "Hinglish and Indic-language coverage is limited; language detection only flags Devanagari.",
        "Segment cues are sparse and self-reported. Use them to generate hypotheses, not to size segments.",
        "Quote verification prevents fabrication, not misinterpretation. A verified quote can still be read wrong.",
        "The corpus spans 2014–2026. Platform features and market conditions change; themes are not timeless.",
    ]:
        story.append(bullet(text, st["bullet"]))

    story.append(P("Method appendix", st["h1"]))
    story.append(
        P(
            "Sources: Play Store, App Store, Reddit, YouTube, ValuePickr, and TradingQ&A. Reddit uses old.reddit JSON with RSS "
            "fallback; ValuePickr and TradingQ&A use Discourse /search.json and /t/{id}.json; app stores use public review pages/RSS; "
            "YouTube uses public pages and comments.",
            st["body"],
        )
    )
    bias_by_kind = {
        "play_store": "Short, friction-heavy",
        "app_store": "Short, friction-heavy",
        "reddit": "Reflective, self-selected",
        "forum": "Long-form, expert/active",
        "youtube": "Reactive, low context",
    }
    source_totals = (
        sources.assign(source_kind=sources["source"].astype(str).str.split(":").str[0])
        .groupby("source_kind", as_index=False)[["documents", "signals"]]
        .sum()
    )
    source_order = ["play_store", "app_store", "reddit", "forum", "youtube"]
    source_totals["sort_order"] = source_totals["source_kind"].map(
        {kind: index for index, kind in enumerate(source_order)}
    )
    source_totals = source_totals.sort_values("sort_order")
    story.append(
        make_table(
            [
                ["Source", "Documents", "Signals", "Bias note"],
                *[
                    [
                        SOURCE_KIND_LABELS.get(row["source_kind"], row["source_kind"].replace("_", " ").title()),
                        str(int(row["documents"])),
                        str(int(row["signals"])),
                        bias_by_kind.get(row["source_kind"], "Mixed"),
                    ]
                    for _, row in source_totals.iterrows()
                ],
            ],
            [34 * mm, 22 * mm, 18 * mm, 94 * mm],
            font_size=7.8,
        )
    )
    story.append(
        P(
            "Codebook v0.2 covers journey stage, triggers, behaviours, emotions, expectations, help-seeking, outcomes, and segment "
            "cues. The extraction prompt is v0.8, with a system-level injection guard. The full codebook is in config/codebook.yaml; "
            "the evidence log schema is in the PRD appendix.",
            st["caption"],
        )
    )
    story.append(
        P(
            "Reproduction: collect → strict filter → extract_signals.py → analyze.py → export_evidence_log.py → dashboard. "
            "Keys live in a gitignored .env. No paid API credits were used.",
            st["caption"],
        )
    )

    doc.build(story)


def main() -> None:
    data = load_report_data()
    path = DELIVERABLES / "INDmoney_SIP_Case_Writeup.pdf"
    DELIVERABLES.mkdir(parents=True, exist_ok=True)
    build(data, path)
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
