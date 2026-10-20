"""Run a second model over a gold-set sample and store grounded labels.

This is a validation tool, not the production path. It uses the same prompt,
quote verification, and deterministic grounding as the primary extractor so
that disagreements reflect model judgement rather than a different pipeline.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.config import settings
from src.db import get_session
from src.grounding import ground_signal_payload, is_meaningful
from src.models import Document
from src.pipeline.extract import (
    EXTRACTION_CONFIG,
    MAX_QUOTE_CHARS,
    MAX_SIGNALS_PER_DOC,
    PROMPT_VERSION,
    build_messages,
    verify_quote,
)
from src.pipeline.llm_client import LLMClient
from src.schemas import BatchDocumentExtraction, DocumentExtraction
from src.taxonomy import normalize_signal_payload, validate_signal_payload


def load_existing_ids(path: Path) -> set[int]:
    if not path.exists():
        return set()
    ids = set()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                ids.add(int(record["document_id"]))
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
    return ids


def parse_batch_results(data: dict) -> list[DocumentExtraction]:
    """Validate results one document at a time.

    A single malformed segment_cues object should not discard the other five
    documents in the batch. The primary extractor already sanitizes these
    shapes; the swap runner needs the same tolerance.
    """
    raw_results = data.get("results", []) if isinstance(data, dict) else []
    sanitized: list[dict] = []
    for raw in raw_results:
        if not isinstance(raw, dict):
            continue
        item = copy.deepcopy(raw)
        if not isinstance(item.get("signals"), list):
            item["signals"] = []
        for signal in item["signals"]:
            if not isinstance(signal, dict):
                continue
            if not isinstance(signal.get("segment_cues"), dict):
                signal["segment_cues"] = {}
            for key in ("triggers", "behaviors", "emotions", "expectations", "help_seeking"):
                if not isinstance(signal.get(key), list):
                    signal[key] = []
        sanitized.append(item)

    try:
        return BatchDocumentExtraction.model_validate({"results": sanitized}).results
    except Exception:
        results: list[DocumentExtraction] = []
        for item in sanitized:
            try:
                results.append(DocumentExtraction.model_validate(item))
            except Exception:
                continue
        return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", default="data/exports/gold_set_200.csv")
    parser.add_argument("--output", default="data/exports/model_swap_gemini_flash.jsonl")
    parser.add_argument("--provider", choices=["gemini", "groq"], default="gemini")
    parser.add_argument("--model", default=None)
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=8000,
        help="Completion budget. Gemini 3.5 Flash spends part of this on reasoning.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0,
        help="Seconds to sleep between batches; useful for low tokens-per-minute limits.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Per-request timeout in seconds; reasoning models need more headroom.",
    )
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    gold_path = Path(args.gold)
    if not gold_path.exists():
        raise SystemExit(f"Gold set not found: {gold_path}")
    gold = pd.read_csv(gold_path)
    document_ids = gold["document_id"].astype(int).tolist()
    if args.limit:
        document_ids = document_ids[: args.limit]

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    done = load_existing_ids(output_path) if args.resume else set()
    document_ids = [doc_id for doc_id in document_ids if doc_id not in done]
    if not document_ids:
        print("All gold-set documents already processed.")
        return

    config = copy.deepcopy(settings()["models"])
    config["routing"]["bulk"] = [args.provider]
    if args.model:
        config["providers"][args.provider]["models"]["bulk"] = args.model
    client = LLMClient(config)
    codebook = settings().get("codebook", {})
    batch_size = max(1, args.batch_size)

    print(
        f"Running {len(document_ids)} gold-set documents with {args.provider} "
        f"({config['providers'][args.provider]['models']['bulk']}) in batches of {batch_size}."
    )

    with output_path.open("a", encoding="utf-8") as handle:
        for batch_index, offset in enumerate(range(0, len(document_ids), batch_size)):
            if batch_index and args.sleep:
                time.sleep(args.sleep)
            batch_ids = document_ids[offset : offset + batch_size]
            with get_session() as session:
                documents = session.scalars(
                    select(Document)
                    .options(selectinload(Document.source))
                    .where(Document.id.in_(batch_ids))
                    .order_by(Document.id)
                ).all()
            if not documents:
                continue
            messages = build_messages(documents, codebook)
            try:
                result = client.complete_json(
                    messages,
                    role="bulk",
                    max_tokens=args.max_tokens,
                    timeout=args.timeout,
                )
                items = parse_batch_results(result.data)
            except Exception as exc:  # noqa: BLE001
                print(f"[batch {offset // batch_size + 1}] FAILED: {type(exc).__name__}: {exc}")
                handle.write(
                    json.dumps(
                        {
                            "document_ids": batch_ids,
                            "error": f"{type(exc).__name__}: {exc}",
                            "provider": args.provider,
                            "model": config["providers"][args.provider]["models"]["bulk"],
                            "at": datetime.utcnow().isoformat() + "Z",
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                handle.flush()
                continue

            by_id = {document.id: document for document in documents}
            for item in items:
                document = by_id.get(item.doc_id)
                if document is None:
                    continue
                record = {
                    "document_id": document.id,
                    "provider": result.provider,
                    "model": result.model,
                    "relevant": bool(item.relevant),
                    "signals": [],
                    "quote_rejections": 0,
                    "grounding_drops": 0,
                    "validation_errors": 0,
                    "at": datetime.utcnow().isoformat() + "Z",
                }
                if item.relevant:
                    for signal in item.signals[:MAX_SIGNALS_PER_DOC]:
                        payload = signal.model_dump()
                        payload, normalize_warnings = normalize_signal_payload(payload)
                        quote = (signal.quote or "").strip()
                        if len(quote) > MAX_QUOTE_CHARS:
                            record["quote_rejections"] += 1
                            continue
                        match = verify_quote(document, quote)
                        if match is None or match.get("soft"):
                            record["quote_rejections"] += 1
                            continue

                        segment_quote = (signal.segment_quote or "").strip() or None
                        if segment_quote:
                            segment_match = verify_quote(document, segment_quote)
                            if (
                                len(segment_quote) > MAX_QUOTE_CHARS
                                or segment_match is None
                                or segment_match.get("soft")
                            ):
                                segment_quote = None

                        grounded, grounding_warnings = ground_signal_payload(
                            payload, quote, segment_quote=segment_quote
                        )
                        validation_errors = validate_signal_payload(grounded)
                        if validation_errors:
                            record["validation_errors"] += 1
                            continue
                        if not is_meaningful(grounded):
                            record["grounding_drops"] += 1
                            continue
                        record["signals"].append(
                            {
                                **grounded,
                                "quote": quote,
                                "segment_quote": segment_quote,
                                "validation_warnings": normalize_warnings,
                                "grounding_warnings": grounding_warnings,
                                "quote_match": match["field"],
                            }
                        )
                handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

            returned_ids = {item.doc_id for item in items}
            missing_ids = [doc_id for doc_id in batch_ids if doc_id not in returned_ids]
            if missing_ids:
                print(f"[batch {offset // batch_size + 1}] missing {len(missing_ids)} document(s) from response")
                handle.write(
                    json.dumps(
                        {
                            "document_ids": missing_ids,
                            "error": "missing from model response",
                            "provider": result.provider,
                            "model": result.model,
                            "at": datetime.utcnow().isoformat() + "Z",
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            handle.flush()
            print(
                f"[{min(offset + batch_size, len(document_ids))}/{len(document_ids)}] "
                f"provider={result.provider} model={result.model}"
            )

    if client.usage_totals:
        print(json.dumps(client.usage_totals, indent=2))


if __name__ == "__main__":
    main()
