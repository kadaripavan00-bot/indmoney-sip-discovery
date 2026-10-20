# Codebook v0.1

## Purpose

This codebook defines how the discovery engine turns a raw public post into a
structured **signal**: a specific, evidence-backed claim about what a person
experienced, expected, did, or needed in relation to a SIP.

The unit of analysis is a **signal**, not a document. One review or post can
contain several signals (for example, a payment failure, followed by shame,
followed by a stop decision).

## Core rules

1. **Code only what is explicit.** Do not infer a segment, emotion, or outcome
   that the author did not state or strongly imply.
2. **One journey stage per signal.** If a post spans stages, split it into
   multiple signals.
3. **Multi-label where the codebook allows it.** A signal can have several
   triggers, behaviours, emotions, expectations, or help-seeking channels.
4. **Use `unknown` rather than guessing.** Unknown is data; false precision is
   worse than a gap.
5. **The quote must be an exact substring** of the source text. The quote is the
   evidence, not a paraphrase.
6. **Separate the stated reason from the proximate trigger.** "Returns were
   low" may be the stated reason; "the auto-debit failed and I did not know how
   to restart" may be the operational trigger. Code both if both appear.
7. **Do not code fund advice, stock tips, or recommendations.** The engine
   discovers user experience; it does not evaluate products.
8. **Preserve Hinglish and regional-language nuance.** Code in the original
   language. Use the notes field for a short English gloss if needed.
9. **No PII in the signal.** Do not copy usernames, phone numbers, account
   numbers, email addresses, or URLs with identifiers.

## Journey stage

| Code | Definition |
|---|---|
| `pre_start` | Considering a SIP; has not started yet. |
| `m0_setup` | Account opening, KYC, mandate, first instalment, or first-week confusion. |
| `m1_first_statement` | First statement, first portfolio review, or first experience of volatility. |
| `m3_early` | Roughly months 2–4; early habit formation. |
| `m6_mid` | Roughly months 5–8; life events, goal drift, declining attention. |
| `m9_late` | Roughly months 9–12; review, recommitment, or quiet lapse. |
| `post_lapse` | Reflecting after pausing or stopping. |
| `unknown` | No stage evidence. |

Infer the stage only from explicit tenure language ("3 months in", "been doing
this for a year") or from the nature of the event (first statement, mandate
failure). Otherwise use `unknown`.

## Triggers

The event or condition that preceded a change in behaviour or emotion.

| Code | Definition |
|---|---|
| `market_drawdown` | A market fall or correction. |
| `negative_returns` | The user's portfolio or fund is flat or negative. |
| `first_statement` | The first statement or first portfolio review. |
| `payment_failure` | A debit, UPI Autopay, or instalment failed. |
| `mandate_issue` | Mandate creation, modification, or revocation problem. |
| `bank_issue` | Bank downtime, account change, or bank-side block. |
| `salary_delay` | Salary or income arrived late. |
| `job_change` | Job loss, switch, or income interruption. |
| `income_volatility` | Variable, gig, or freelance income. |
| `emergency_expense` | Medical, family, or other urgent expense. |
| `liquidity_need` | A planned or unplanned need for cash. |
| `goal_doubt` | Doubt about whether the goal is realistic or still relevant. |
| `goal_achieved` | The goal was reached or is close. |
| `life_event` | Marriage, relocation, child, education, or similar. |
| `trust_shock` | A trust breach: support failure, hidden charge, mis-selling, app error. |
| `news_event` | News or a public event that changed confidence. |
| `finfluencer_advice` | Advice from YouTube, Instagram, or another creator. |
| `friend_family_advice` | Advice from friends, family, or colleagues. |
| `product_comparison` | Comparison with another app, fund, FD, or asset. |
| `app_friction` | Confusing UX, broken flow, or difficulty finding a feature. |
| `product_suspension` | The AMC, platform, or regulator paused, suspended, or closed a SIP/fund; the investor did not choose to stop. |
| `support_failure` | Poor or absent customer support. |
| `notification_fatigue` | Too many or irrelevant notifications. |
| `tax` | Tax-saving or tax-treatment confusion. |
| `bonus_or_raise` | Bonus, raise, or a new inflow. |
| `other` | A clear trigger not listed above; explain in notes. |
| `unknown` | No trigger evidence. |

## Behaviours

| Code | Definition |
|---|---|
| `started_sip` | Started a SIP. |
| `increased_sip` | Increased the instalment or added a SIP. |
| `decreased_sip` | Reduced the instalment. |
| `paused_sip` | Temporarily paused. |
| `stopped_sip` | Stopped or cancelled. |
| `restarted_sip` | Resumed after a gap. |
| `switched_product` | Moved to another app, fund, or asset. |
| `withdrew` | Redeemed or withdrew. |
| `checked_frequently` | Checks daily or several times a week. |
| `checked_rarely` | Checks monthly or less. |
| `avoided_app` | Avoids opening the app because of anxiety or confusion. |
| `sought_help` | Asked a person, community, or support channel for help. |
| `complained` | Public complaint or negative review. |
| `recommended` | Recommends the product or SIP to others. |
| `did_nothing` | Considered acting but did not. |
| `other` | A clear behaviour not listed above; explain in notes. |
| `unknown` | No behaviour evidence. |

## Emotions

Use the author's explicit emotional language or a very strong implication.
Do not infer emotion from a negative rating alone.

`anxiety`, `fear`, `shame`, `embarrassment`, `confusion`, `frustration`,
`anger`, `distrust`, `disappointment`, `apathy`, `regret`, `relief`, `pride`,
`confidence`, `neutral`, `unknown`.

## Expectations

What the author expected to happen when they started.

| Code | Definition |
|---|---|
| `guaranteed_returns` | Believes returns are guaranteed or cannot be negative. |
| `linear_growth` | Expects steady, line-goes-up growth. |
| `fd_like_safety` | Expects FD-like capital safety. |
| `quick_returns` | Expects meaningful returns within weeks or a few months. |
| `beat_inflation` | Wants to beat inflation over the long run. |
| `build_wealth` | Wants long-term wealth creation. |
| `goal_progress` | Wants visible progress toward a named goal. |
| `learn_investing` | Wants to learn how investing works. |
| `tax_saving` | Motivated by tax saving. |
| `discipline` | Wants a forced savings habit. |
| `other` | A clear expectation not listed above. |
| `unknown` | No expectation evidence. |

## Help-seeking

Where the author went when unsure: `friend_family`, `youtube`, `reddit`,
`google_search`, `customer_support`, `bank`, `ca_advisor`, `app_help`,
`social_media`, `none`, `other`, `unknown`.

## Outcome

| Code | Definition |
|---|---|
| `continues` | Explicitly still investing. |
| `paused` | Temporarily stopped, with intent to resume. |
| `stopped` | Cancelled or stopped. |
| `returned` | Stopped or paused, then restarted. |
| `reduced` | Still investing but at a lower amount. |
| `increased` | Still investing and increased the amount. |
| `unknown` | No outcome evidence. |

## Segment cues

Tag a segment only when the author states it or it is unmistakable from the
text. Otherwise use `unknown`.

| Segment | Codes |
|---|---|
| Income stability | `salaried`, `variable`, `gig`, `student`, `business`, `retired`, `unknown` |
| Age band | `18-24`, `25-29`, `30-35`, `36-45`, `46+`, `unknown` |
| Source of money | `own_income`, `family`, `bonus`, `savings`, `loan`, `unknown` |
| Influence | `self`, `friend_family`, `youtube`, `employer`, `ca_advisor`, `social_media`, `unknown` |
| Ticket size | `small`, `medium`, `large`, `unknown` (relative to stated income) |
| Goal type | `named_goal`, `wealth`, `tax`, `retirement`, `education`, `emergency`, `unspecified`, `unknown` |

## Confidence

| Code | Definition |
|---|---|
| `high` | Explicit language for the trigger, behaviour, and outcome; quote is unambiguous. |
| `medium` | One element is inferred from strong context; quote is clear. |
| `low` | Sarcasm, mixed languages, or ambiguity; needs human review. |

## Quote verification

The extractor returns `quote`, `quote_start`, and `quote_end`. The pipeline
checks that:

1. `quote` is an exact substring of the normalized source text.
2. `quote_start` and `quote_end` match the first occurrence.
3. The quote contains the evidence for the codes.

If verification fails, the signal is rejected and logged. It is not silently
repaired.

## Versioning

Every signal records the codebook version, prompt version, model ID, model
version, temperature, and run ID. Changes to the codebook require a new version
and a re-run of the gold set.
