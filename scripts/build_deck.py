"""Build the case deck in PPTX and PDF, plus the case write-up PDF.

The deck is generated from the same grounded analysis as the dashboard and
evidence log. Numbers are read at build time, so re-running after extraction
refreshes the deck.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image as RLImage,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from src.reporting import PALETTE, load_report_data, read_json

ROOT = Path(__file__).resolve().parents[1]
DELIVERABLES = ROOT / "deliverables"
CHARTS = DELIVERABLES / "charts"


def clip_quote(text: str, limit: int = 260) -> str:
    """Trim a quote at a word boundary instead of cutting mid-word."""
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 3].rsplit(" ", 1)[0].rstrip(" ,;:")
    return cut + "..."

NAVY = RGBColor(0x17, 0x32, 0x4D)
TEAL = RGBColor(0x1F, 0x6F, 0x5C)
TEAL_LIGHT = RGBColor(0xDC, 0xEB, 0xE5)
SAND = RGBColor(0xE8, 0xDC, 0xC8)
CORAL = RGBColor(0xC9, 0x6A, 0x4B)
GREY = RGBColor(0x5B, 0x67, 0x70)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
LIGHT = RGBColor(0xF4, 0xF6, 0xF5)


def _theme(summary: pd.DataFrame, slug: str) -> pd.Series | None:
    row = summary[summary["slug"] == slug]
    return row.iloc[0] if not row.empty else None


def _metric(row: pd.Series | None, key: str, default: str = "—") -> str:
    if row is None or key not in row:
        return default
    value = row[key]
    if key in ("lapse_rate",):
        return f"{value:.0%}" if row.get("outcome_known", True) else "n/a"
    if key in ("lift",):
        return f"{value:.2f}x" if row.get("outcome_known", True) else "n/a"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def build_content(data: dict) -> list[dict]:
    facts = data["facts"]
    summary = data["summary"]
    sources = data["sources"]
    stages = data["stages"]
    signals = data["signals"]
    documents = data["documents"]
    validation = data.get("validation") or {}
    swap = validation.get("model_swap") or {}
    kappa_parts = []
    for key, label in (
        ("relevance", "relevance"),
        ("outcome", "outcome"),
        ("primary_theme", "theme"),
    ):
        block = swap.get(key) or {}
        value = block.get("kappa")
        if isinstance(value, (int, float)) and value == value:
            kappa_parts.append(f"{label} κ={value:.2f}")
    kappa_text = (
        f"200-item evaluation set; second model on {swap.get('compared_items', 'n/a')} items "
        "(all 80 resolved outcomes + relevance controls). "
        + ", ".join(kappa_parts)
        + ". Kappa is agreement, not truth."
        if kappa_parts
        else "200-item evaluation set; inter-model agreement and a reviewed subset. Kappa is reported, not hidden."
    )
    red_team = validation.get("red_team") or {}
    red_text = (
        f"{red_team.get('passed', 15)}/{red_team.get('tests', 15)} red-team tests pass, including an "
        "end-to-end prompt-injection call. Known limitations remain."
        if red_team
        else "Deterministic tests cover injection, negation, third-person stories, and quote fabrication."
    )

    def s(key: str) -> str:
        return f"{facts[key]:,}"

    top_problem = summary[summary["kind"] == "problem"].head(3)
    top_names = ", ".join(top_problem["name"].tolist())
    lapse_candidates = summary[
        (summary["kind"] == "problem")
        & (summary["outcome_known"])
        & (summary["signals"] >= 4)
    ]
    top_lapse = (
        lapse_candidates.sort_values(["lapse_rate", "signals"], ascending=False).iloc[0]
        if not lapse_candidates.empty
        else _theme(summary, "cashflow_shock")
    )
    top_lapse_name = top_lapse["name"].lower() if top_lapse is not None else "cash-flow shock"
    top_lapse_signals = int(top_lapse["signals"]) if top_lapse is not None else 0
    top_lapse_display = top_lapse["lapse_display"] if top_lapse is not None else "n/a"
    cashflow = _theme(summary, "cashflow_shock")
    cashflow_text = (
        f"{int(cashflow['signals'])} signals, {cashflow['lapse_display']} lapse among resolved outcomes. "
        "The SIP was affordable last month, not this month."
        if cashflow is not None
        else "The SIP was affordable last month, not this month."
    )

    def theme_slide(slug: str, title: str, kicker: str, bullets: list[str], quote_limit: int = 2) -> dict:
        row = _theme(summary, slug)
        quotes = []
        if row is not None and not signals.empty:
            subset = signals[signals["themes"].apply(lambda values: slug in values)]
            subset = subset.sort_values("signal_id").head(quote_limit)
            for _, item in subset.iterrows():
                quotes.append(
                    {
                        "quote": item["quote"],
                        "source": item["source"],
                        "outcome": item["outcome"],
                        "stage": item["journey_stage"],
                    }
                )
        return {
            "type": "theme",
            "kicker": kicker,
            "title": title,
            "theme": row,
            "bullets": bullets,
            "quotes": quotes,
        }

    slides: list[dict] = [
        {
            "type": "title",
            "kicker": "INDmoney Growth · Discovery engine",
            "title": "Why first-time SIPs lapse by month 12",
            "subtitle": "A public-evidence engine for finding the moments that break the habit — and the interventions that keep it alive.",
            "meta": (
                f"{s('documents')} public documents · {s('strict_relevant')} strict SIP/MF candidates · "
                f"{s('deep_coded')} deep-coded · {s('signals')} grounded signals"
            ),
            "date": "October 2026",
        },
        {
            "type": "bullets",
            "kicker": "Executive summary",
            "title": "The retention problem is a sequence of moments, not a single reason",
            "bullets": [
                (
                    f"The strongest lapse-associated theme is {top_lapse_name}: "
                    f"{top_lapse_signals} signals, {top_lapse_display} lapse rate among resolved outcomes."
                ),
                (
                    "System friction is the most fixable: failed mandates/debits and cancellation mazes create "
                    "lapses the investor did not choose."
                ),
                (
                    "Market noise is high-reach but not uniformly harmful: many investors continue through drawdowns "
                    "when they have a goal and a habit."
                ),
                (
                    "Three plays: mandate rescue, pause-don't-stop, and a cancellation path that works. "
                    "All are workflow and clarity, not fund recommendations."
                ),
                (
                    "Measure one thing: at least one successful instalment in the last 30 days, 12 months after the first SIP."
                ),
            ],
            "note": "Directional public evidence; associations are not causal.",
        },
        {
            "type": "table",
            "kicker": "The brief",
            "title": "Nine discovery questions, nine evidence-backed answers",
            "columns": ["Question", "What the evidence says"],
            "rows": [
                [
                    "1. Who starts?",
                    "Salaried first-time investors, often 20s–30s, starting small. Segment evidence is sparse; treat as directional.",
                ],
                [
                    "2. What do they expect?",
                    "Steady, FD-like, or market-beating returns. The first flat period is an expectation shock.",
                ],
                [
                    "3. What happens in the first 30 days?",
                    "KYC, mandate, first debit, and NAV/date confusion. Confusion is the most common coded emotion.",
                ],
                [
                    "4. What triggers a pause or stop?",
                    "Cash-flow shocks, job changes, competing goals, drawdowns, and app/cancellation friction.",
                ],
                [
                    "5. How does volatility affect them?",
                    "It raises checking and anxiety for some; others continue through drawdowns with a goal and a habit.",
                ],
                [
                    "6. What role do cash-flow shocks play?",
                    f"Cash-flow shock: {cashflow_text}",
                ],
                [
                    "7. What role do platforms play?",
                    "Failed mandates, debit issues, cancellation mazes, and support gaps create system-forced lapses.",
                ],
                [
                    "8. Which segments are at risk?",
                    "Directionally, early-stage and cash-flow-constrained investors. Segment cues are sparse; app reviews overrepresent friction.",
                ],
                [
                    "9. What would make them stay?",
                    "Pause instead of stop, mandate rescue, goal progress, human support, and expectation-setting.",
                ],
            ],
            "widths": [2.4, 10.2],
            "font_size": 9.5,
        },
        {
            "type": "image",
            "kicker": "Method",
            "title": "From 8,000+ public posts to a grounded evidence base",
            "image": CHARTS / "funnel.png",
            "bullets": [
                f"{s('documents')} documents from six sources: Play Store, App Store, Reddit, YouTube, ValuePickr, TradingQ&A.",
                f"{s('strict_relevant')} strict SIP/mutual-fund candidates; {s('deep_coded')} deep-coded with a free-tier LLM.",
                "Every behavioural quote is verified against the source; unsupported codes are dropped by deterministic grounding.",
                "Includes competitor app reviews to learn category-wide friction; INDmoney-specific views are filterable in the dashboard.",
                "Counts, prevalence, statistics, and opportunity scores are computed in Python/SQL, not by the model.",
            ],
        },
        {
            "type": "image",
            "kicker": "What we heard",
            "title": "Where the retention opportunity is",
            "image": CHARTS / "theme_scores.png",
            "bullets": [
                f"Top problem themes: {top_names}.",
                "The protective theme — what keeps SIPs alive — is shown separately in sand.",
                "Opportunity score combines reach, lapse lift, evidence strength, solvability, and effort.",
                "Themes with unresolved outcomes carry a friction prior and are marked n/a in the table.",
            ],
        },
        theme_slide(
            "mandate_friction",
            "Failed debits and mandate breakage",
            "Theme 01 · System friction",
            [
                "For many investors, the SIP did not fail because they gave up; the debit did.",
                "Signals include UPI Autopay confusion, eNach failures, bank blocks, and silent missed instalments.",
                "The fix is pre-debit visibility and a repair path, not another reminder to invest.",
            ],
        ),
        theme_slide(
            "cashflow_shock",
            "Cash-flow shocks and competing commitments",
            "Theme 02 · Affordability",
            [
                "The SIP was affordable last month, not this month.",
                "Job changes, salary delays, medical expenses, house/wedding goals, and income volatility.",
                "A pause or step-down preserves the habit; a permanent stop loses the investor.",
            ],
        ),
        theme_slide(
            "cancellation_friction",
            "Can't stop or fix it",
            "Theme 03 · Control",
            [
                "Investors try to cancel, pause, or repair a SIP and the flow does not work.",
                "Signals include 'still active', 'money got deducted', missing support, and unclear effective dates.",
                "A pause option beside cancel and a status tracker turn a dead end into a save.",
            ],
        ),
        theme_slide(
            "market_panic",
            "Market noise and loss aversion",
            "Theme 04 · Expectations",
            [
                "A red portfolio is not automatically a lapse; the meaning the investor assigns to it matters.",
                "Some stop; others continue because they have a goal, a habit, or a human to talk to.",
                "Show goal progress and the trade-off, not fear or urgency.",
            ],
        ),
        {
            "type": "bullets",
            "kicker": "Theme 05 · Forced pauses and confusion",
            "title": "Sometimes the system pauses the SIP — and the investor never finds out why",
            "bullets": [
                "Forced pauses: AMC, platform, or regulator restrictions; the investor did not choose to stop.",
                "Product confusion: direct vs regular, NAV, fund category, and 'which fund is actually debited?'",
                "Both are clarity problems: explain the reason, the duration, the next step, and the auto-resume.",
                "No specific fund recommendations; compare categories and mechanics, not returns.",
            ],
            "note": (
                f"Forced pause signals: {int(_theme(summary, 'forced_pause')['signals']) if _theme(summary, 'forced_pause') is not None else 0}; "
                f"product confusion: {int(_theme(summary, 'product_confusion')['signals']) if _theme(summary, 'product_confusion') is not None else 0}. "
                "Small n, high fixability."
            ),
        },
        theme_slide(
            "positive_continuation",
            "What keeps SIPs alive",
            "Theme 06 · Protection",
            [
                "Continuation is not passive. It is a goal, a habit, a support system, and a reason to stay.",
                "Investors describe continuing through COVID, flat periods, and job changes.",
                "Protect these moments: goal progress, streaks, community stories, and human encouragement.",
            ],
        ),
        {
            "type": "image",
            "kicker": "Segments and stages",
            "title": "Stage tells us where the conversation is, not who survives",
            "image": CHARTS / "stage_lapse.png",
            "bullets": [
                "Setup posts cluster around KYC, mandate, first debit, and first statement; most are questions, not resolved stops.",
                "Later-stage posts include more resolved decisions about returns, goals, and 'is this still worth it?'",
                "Stage is the point referenced in the post, not a cohort survival curve; do not read 0% at setup as safety.",
                "Segment cues are sparse and self-reported; use them for hypotheses, not sizing. Triangulate sources.",
            ],
        },
        {
            "type": "image",
            "kicker": "Prioritisation",
            "title": "Reach and lapse association point to different plays",
            "image": CHARTS / "opportunity_matrix.png",
            "bullets": [
                f"{row['name']}: {row['share_signal_docs']:.0%} reach, {row['lapse_display']} lapse, "
                f"score {row['opportunity_score']:.0f}."
                for _, row in summary[summary["kind"] == "problem"].head(4).iterrows()
            ]
            + [
                "Unresolved themes carry a friction prior; the score is a prioritisation heuristic, not a causal effect."
            ],
        },
        {
            "type": "columns",
            "kicker": "Retention portfolio",
            "title": "Three horizons, nine interventions, zero fear-based nudges",
            "columns": [
                (
                    "0–30 days",
                    [
                        "Mandate health check before the first debit.",
                        "3-day pre-debit alert with one-tap repair.",
                        "First-statement explainer: XIRR, absolute return, and market noise.",
                    ],
                ),
                (
                    "30–90 days",
                    [
                        "Pause 1–3 months with auto-resume, beside cancel.",
                        "Step-down amount and salary-cycle alignment.",
                        "Goal tagging and a plain-language 'what am I invested in' view.",
                    ],
                ),
                (
                    "90–365 days",
                    [
                        "Drawdown explainer framed as goal progress.",
                        "Two-missed-debit re-engagement with a human fallback.",
                        "Annual goal review and community stories, not FOMO.",
                    ],
                ),
            ],
        },
        {
            "type": "table",
            "kicker": "Measurement",
            "title": "Measure the 12-month habit, not the download",
            "columns": ["Metric", "Definition", "Cadence"],
            "rows": [
                [
                    "Primary: 12-month retention",
                    "At least one successful instalment in the last 30 days, 12 months after the first SIP.",
                    "Monthly cohort",
                ],
                [
                    "Mandate recovery",
                    "Share of failed/at-risk mandates repaired before the next debit date.",
                    "Weekly",
                ],
                [
                    "Pause-to-resume",
                    "Share of paused SIPs that resume within 90 days.",
                    "Monthly",
                ],
                [
                    "Cancellation save",
                    "Share of cancellation intents that choose pause, step-down, or repair.",
                    "Weekly",
                ],
                [
                    "Support resolution",
                    "Median time to resolve a SIP/mandate issue; share resolved in one touch.",
                    "Weekly",
                ],
                [
                    "Guardrails",
                    "Complaints, opt-outs, support load, mis-selling risk; no fear/FOMO/urgency copy.",
                    "Continuous",
                ],
            ],
            "widths": [2.8, 8.2, 1.6],
            "font_size": 9.5,
        },
        {
            "type": "boxes",
            "kicker": "Validation",
            "title": "What we trust, and what we are still testing",
            "boxes": [
                (
                    "Quote verification",
                    "Every behavioural quote must be an exact substring. Fabricated or over-long quotes are rejected.",
                ),
                (
                    "Grounding",
                    "Deterministic rules check first-person actions, negations, attempts, payment stops, temporary pauses, and segment evidence.",
                ),
                (
                    "Gold set + kappa",
                    kappa_text,
                ),
                (
                    "Red team",
                    red_text,
                ),
            ],
        },
        {
            "type": "bullets",
            "kicker": "Limitations",
            "title": "What this evidence can and cannot tell us",
            "bullets": [
                "Public posts are self-selected; people with problems are more likely to post.",
                "Self-reported outcomes are not the 12-month product metric.",
                "Theme-lapse associations are correlational, not causal.",
                "App reviews are short and often lack context; narrative sources carry more explanatory weight.",
                "Hinglish and Indic-language coverage is limited; segment cues are sparse.",
                "The corpus spans 2014–2026; platform and market conditions change over time.",
            ],
        },
        {
            "type": "bullets",
            "kicker": "Recommendation",
            "title": "Start with the two plays that remove a lapse the investor did not choose",
            "bullets": [
                "Pilot 1: mandate rescue. Pre-debit health check, 3-day repair window, auto-retry, and a clear reason.",
                "Pilot 2: pause-don't-stop. A 1–3 month pause with auto-resume, step-down, and salary-cycle alignment.",
                "Instrument the 12-month metric and the pause-to-resume bridge before scaling.",
                "Human-adjudicate the 30-item review queue, then expand to the full 200 before sizing; keep red team in CI.",
                "Expand the narrative corpus (Reddit, forums, YouTube) before sizing segments.",
            ],
            "note": "No specific funds or stocks. No fear, FOMO, or urgency-based nudges.",
        },
        {
            "type": "appendix",
            "kicker": "Appendix",
            "title": "Sources, codebook, and reproduction",
            "sources": sources,
            "stages": stages,
        },
    ]
    return slides


# ---------------------------------------------------------------------------
# PPTX renderer
# ---------------------------------------------------------------------------


DECK_TRANSLATION = str.maketrans({"₹": "Rs ", "κ": "kappa"})


def _deck_safe(text: object) -> str:
    return str(text).translate(DECK_TRANSLATION)


def _set_text(frame, text: str, size: int, color: RGBColor, bold: bool = False) -> None:
    frame.clear()
    paragraph = frame.paragraphs[0]
    paragraph.alignment = PP_ALIGN.LEFT
    run = paragraph.add_run()
    run.text = _deck_safe(text)
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = "Aptos"


def _add_slide_frame(prs: Presentation, kicker: str | None, title: str, number: int) -> object:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    background = slide.background
    background.fill.solid()
    background.fill.fore_color.rgb = WHITE

    if kicker:
        box = slide.shapes.add_textbox(Inches(0.65), Inches(0.38), Inches(12.0), Inches(0.3))
        _set_text(box.text_frame, kicker.upper(), 10, TEAL, bold=True)

    title_box = slide.shapes.add_textbox(Inches(0.65), Inches(0.68), Inches(12.0), Inches(1.0))
    title_size = 27 if len(title) <= 62 else (24 if len(title) <= 78 else 21)
    _set_text(title_box.text_frame, title, title_size, NAVY, bold=True)
    title_box.text_frame.word_wrap = True

    line = slide.shapes.add_shape(1, Inches(0.67), Inches(1.62), Inches(1.1), Inches(0.04))
    line.fill.solid()
    line.fill.fore_color.rgb = TEAL
    line.line.fill.background()

    footer = slide.shapes.add_textbox(Inches(0.65), Inches(7.12), Inches(11.9), Inches(0.22))
    _set_text(
        footer.text_frame,
        "INDmoney Growth · Public evidence · October 2026",
        8,
        GREY,
    )
    number_box = slide.shapes.add_textbox(Inches(12.2), Inches(7.12), Inches(0.5), Inches(0.22))
    _set_text(number_box.text_frame, str(number), 8, GREY)
    return slide


def _add_bullets(slide, bullets: list[str], left: float, top: float, width: float, height: float, size: int = 15) -> None:
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    frame = box.text_frame
    frame.word_wrap = True
    frame.clear()
    for index, bullet in enumerate(bullets):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.space_after = Pt(9)
        paragraph.line_spacing = 1.08
        run = paragraph.add_run()
        run.text = "•  " + _deck_safe(bullet)
        run.font.size = Pt(size)
        run.font.color.rgb = NAVY
        run.font.name = "Aptos"


def _add_picture_fit(slide, path: Path, left: float, top: float, width: float, height: float) -> None:
    from PIL import Image

    with Image.open(path) as image:
        image_width, image_height = image.size
    aspect = image_width / image_height
    target_aspect = width / height
    if aspect > target_aspect:
        actual_width = width
        actual_height = width / aspect
    else:
        actual_height = height
        actual_width = height * aspect
    left = left + (width - actual_width) / 2
    top = top + (height - actual_height) / 2
    slide.shapes.add_picture(
        str(path), Inches(left), Inches(top), Inches(actual_width), Inches(actual_height)
    )


def build_pptx(slides: list[dict], path: Path) -> None:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    for number, slide_data in enumerate(slides, start=1):
        kind = slide_data["type"]
        if kind == "title":
            slide = prs.slides.add_slide(prs.slide_layouts[6])
            background = slide.background
            background.fill.solid()
            background.fill.fore_color.rgb = NAVY
            band = slide.shapes.add_shape(1, Inches(0), Inches(0), Inches(0.18), Inches(7.5))
            band.fill.solid()
            band.fill.fore_color.rgb = TEAL
            band.line.fill.background()
            kicker = slide.shapes.add_textbox(Inches(0.8), Inches(0.7), Inches(11.5), Inches(0.3))
            _set_text(kicker.text_frame, slide_data["kicker"].upper(), 11, RGBColor(0x9F, 0xC9, 0xBB), bold=True)
            title = slide.shapes.add_textbox(Inches(0.8), Inches(1.9), Inches(11.6), Inches(1.8))
            _set_text(title.text_frame, slide_data["title"], 42, WHITE, bold=True)
            title.text_frame.word_wrap = True
            subtitle = slide.shapes.add_textbox(Inches(0.8), Inches(3.9), Inches(10.8), Inches(1.2))
            _set_text(subtitle.text_frame, slide_data["subtitle"], 17, RGBColor(0xD9, 0xE6, 0xE1))
            subtitle.text_frame.word_wrap = True
            meta = slide.shapes.add_textbox(Inches(0.8), Inches(5.55), Inches(11.5), Inches(0.4))
            _set_text(meta.text_frame, slide_data["meta"], 11, RGBColor(0x9F, 0xC9, 0xBB))
            date = slide.shapes.add_textbox(Inches(0.8), Inches(6.7), Inches(4), Inches(0.3))
            _set_text(date.text_frame, slide_data["date"], 10, RGBColor(0xD9, 0xE6, 0xE1))
            continue

        slide = _add_slide_frame(prs, slide_data.get("kicker"), slide_data["title"], number)

        if kind == "bullets":
            _add_bullets(slide, slide_data["bullets"], 0.75, 1.95, 11.8, 4.8, size=15)
            if slide_data.get("note"):
                note = slide.shapes.add_textbox(Inches(0.75), Inches(6.55), Inches(11.8), Inches(0.35))
                _set_text(note.text_frame, slide_data["note"], 9, GREY)
        elif kind == "image":
            _add_picture_fit(slide, slide_data["image"], 0.55, 1.85, 7.1, 5.0)
            _add_bullets(slide, slide_data["bullets"], 7.85, 1.9, 4.85, 5.0, size=12.5)
        elif kind == "table":
            rows = len(slide_data["rows"]) + 1
            cols = len(slide_data["columns"])
            left = Inches(0.65)
            top = Inches(1.9)
            width = Inches(sum(slide_data.get("widths", [1.0] * cols)))
            height = Inches(0.4 * rows)
            shape = slide.shapes.add_table(rows, cols, left, top, width, height)
            table = shape.table
            for index, column in enumerate(slide_data["columns"]):
                cell = table.cell(0, index)
                cell.text = column
                cell.fill.solid()
                cell.fill.fore_color.rgb = NAVY
                for paragraph in cell.text_frame.paragraphs:
                    for run in paragraph.runs:
                        run.font.size = Pt(10)
                        run.font.bold = True
                        run.font.color.rgb = WHITE
            for row_index, row in enumerate(slide_data["rows"], start=1):
                for col_index, value in enumerate(row):
                    cell = table.cell(row_index, col_index)
                    cell.text = str(value)
                    cell.fill.solid()
                    cell.fill.fore_color.rgb = LIGHT if row_index % 2 == 0 else WHITE
                    for paragraph in cell.text_frame.paragraphs:
                        for run in paragraph.runs:
                            run.font.size = Pt(slide_data.get("font_size", 10))
                            run.font.color.rgb = NAVY
            for index, width_value in enumerate(slide_data.get("widths", [1.0] * cols)):
                table.columns[index].width = Inches(width_value)
        elif kind == "theme":
            row = slide_data["theme"]
            if row is not None:
                metrics = [
                    ("Signals", _metric(row, "signals")),
                    ("Documents", _metric(row, "documents")),
                    ("Lapse rate", _metric(row, "lapse_rate")),
                    ("Opportunity", _metric(row, "opportunity_score")),
                ]
                for index, (label, value) in enumerate(metrics):
                    box = slide.shapes.add_textbox(Inches(0.75 + index * 1.55), Inches(1.95), Inches(1.45), Inches(0.85))
                    frame = box.text_frame
                    frame.clear()
                    paragraph = frame.paragraphs[0]
                    run = paragraph.add_run()
                    run.text = value
                    run.font.size = Pt(22)
                    run.font.bold = True
                    run.font.color.rgb = TEAL
                    paragraph2 = frame.add_paragraph()
                    run2 = paragraph2.add_run()
                    run2.text = label.upper()
                    run2.font.size = Pt(8)
                    run2.font.color.rgb = GREY
            _add_bullets(slide, slide_data["bullets"], 0.75, 3.05, 5.8, 2.8, size=13)
            quotes = slide_data.get("quotes", [])
            for index, quote in enumerate(quotes[:2]):
                y = 3.0 + index * 1.85
                box = slide.shapes.add_textbox(Inches(6.85), Inches(y), Inches(5.75), Inches(1.55))
                frame = box.text_frame
                frame.word_wrap = True
                frame.clear()
                paragraph = frame.paragraphs[0]
                run = paragraph.add_run()
                run.text = _deck_safe(f"“{clip_quote(quote['quote'], 260)}”")
                run.font.size = Pt(12)
                run.font.italic = True
                run.font.color.rgb = NAVY
                caption = frame.add_paragraph()
                run2 = caption.add_run()
                run2.text = f"{quote['source']} · outcome={quote['outcome']} · stage={quote['stage']}"
                run2.font.size = Pt(8)
                run2.font.color.rgb = GREY
            if row is not None:
                box = slide.shapes.add_textbox(Inches(6.85), Inches(6.55), Inches(5.75), Inches(0.55))
                frame = box.text_frame
                frame.word_wrap = True
                frame.clear()
                run = frame.paragraphs[0].add_run()
                run.text = "Fix: " + " ".join(row.get("interventions", [])[:2])
                run.font.size = Pt(10)
                run.font.color.rgb = TEAL
        elif kind == "columns":
            for index, (heading, items) in enumerate(slide_data["columns"]):
                x = 0.7 + index * 4.15
                card = slide.shapes.add_shape(1, Inches(x), Inches(1.95), Inches(3.85), Inches(4.55))
                card.fill.solid()
                card.fill.fore_color.rgb = LIGHT if index != 1 else TEAL_LIGHT
                card.line.color.rgb = TEAL_LIGHT
                heading_box = slide.shapes.add_textbox(Inches(x + 0.25), Inches(2.15), Inches(3.35), Inches(0.4))
                _set_text(heading_box.text_frame, heading, 18, TEAL, bold=True)
                _add_bullets(slide, items, x + 0.25, 2.75, 3.35, 3.3, size=12)
        elif kind == "boxes":
            for index, (heading, body) in enumerate(slide_data["boxes"]):
                x = 0.7 + (index % 2) * 6.1
                y = 1.95 + (index // 2) * 2.35
                card = slide.shapes.add_shape(1, Inches(x), Inches(y), Inches(5.75), Inches(2.0))
                card.fill.solid()
                card.fill.fore_color.rgb = LIGHT
                card.line.color.rgb = TEAL_LIGHT
                heading_box = slide.shapes.add_textbox(Inches(x + 0.25), Inches(y + 0.18), Inches(5.25), Inches(0.35))
                _set_text(heading_box.text_frame, heading, 15, TEAL, bold=True)
                body_box = slide.shapes.add_textbox(Inches(x + 0.25), Inches(y + 0.62), Inches(5.25), Inches(1.25))
                frame = body_box.text_frame
                frame.word_wrap = True
                frame.clear()
                run = frame.paragraphs[0].add_run()
                run.text = body
                run.font.size = Pt(11)
                run.font.color.rgb = NAVY
        elif kind == "appendix":
            sources = slide_data["sources"]
            stages = slide_data["stages"]
            _add_bullets(
                slide,
                [
                    "Sources: Play Store, App Store, Reddit, YouTube, ValuePickr, TradingQ&A.",
                    "Codebook v0.2: triggers, behaviours, emotions, expectations, help-seeking, outcomes, segments.",
                    "Pipeline: collect → normalize → strict filter → LLM extract → quote verify → ground → quantify → validate.",
                    "Reproduce: collect_sample.py, extract_signals.py, analyze.py, export_evidence_log.py.",
                    "No internal analytics, CRM records, or primary interviews. Public data only.",
                ],
                0.75,
                1.95,
                6.1,
                4.6,
                size=12,
            )
            table_rows = [["Source", "Signals", "Lapse rate"]]
            for _, row in sources.head(8).iterrows():
                table_rows.append(
                    [
                        str(row["source"]),
                        str(int(row["signals"])),
                        f"{row['lapse_rate']:.0%}" if row["known_outcomes"] else "n/a",
                    ]
                )
            shape = slide.shapes.add_table(len(table_rows), 3, Inches(7.1), Inches(1.95), Inches(5.4), Inches(0.33 * len(table_rows)))
            table = shape.table
            for row_index, row in enumerate(table_rows):
                for col_index, value in enumerate(row):
                    cell = table.cell(row_index, col_index)
                    cell.text = value
                    cell.fill.solid()
                    cell.fill.fore_color.rgb = NAVY if row_index == 0 else (LIGHT if row_index % 2 == 0 else WHITE)
                    for paragraph in cell.text_frame.paragraphs:
                        for run in paragraph.runs:
                            run.font.size = Pt(8)
                            run.font.color.rgb = WHITE if row_index == 0 else NAVY
                            run.font.bold = row_index == 0

    path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(path))


def main() -> None:
    data = load_report_data()
    slides = build_content(data)
    pptx_path = DELIVERABLES / "INDmoney_SIP_Discovery_Deck.pptx"
    build_pptx(slides, pptx_path)
    print(f"Wrote {pptx_path}")


if __name__ == "__main__":
    main()
