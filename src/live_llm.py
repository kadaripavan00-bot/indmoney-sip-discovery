"""
Live LLM features for the deployed discovery engine.
Provides RAG Q&A, live extraction, theme narratives, and segment comparison.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import faiss
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
import litellm

ROOT = Path(__file__).resolve().parents[1]
INDEX_DIR = ROOT / "data" / "vector_index"
INDEX_DIR.mkdir(parents=True, exist_ok=True)

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
LLM_MODEL = "gemini/gemini-3.5-flash-lite"  # free-tier


class LiveLLMEngine:
    """Live LLM features for the deployed dashboard."""

    def __init__(self):
        self.embedder = SentenceTransformer(EMBED_MODEL)
        self.index = None
        self.metadata = None
        self._load_or_build_index()

    def _load_or_build_index(self):
        """Load existing FAISS index or build from current signals."""
        index_path = INDEX_DIR / "signals.faiss"
        meta_path = INDEX_DIR / "signals_metadata.json"

        if index_path.exists() and meta_path.exists():
            self.index = faiss.read_index(str(index_path))
            with open(meta_path, "r", encoding="utf-8") as f:
                self.metadata = json.load(f)
        else:
            self._build_index()

    def _build_index(self):
        """Build FAISS index from current grounded signals."""
        from src.db import get_session
        from src.analysis import signals_frame

        with get_session() as session:
            signals, _ = signals_frame(session)

        if signals.empty:
            # Create empty index
            self.index = faiss.IndexFlatIP(384)
            self.metadata = []
            return

        texts = []
        for _, row in signals.iterrows():
            text = f"Source: {row.get('source', '')}\n"
            text += f"Theme: {', '.join(row.get('themes', []))}\n"
            text += f"Outcome: {row.get('outcome', '')}\n"
            text += f"Stage: {row.get('journey_stage', '')}\n"
            text += f"Quote: {row.get('quote', '')}"
            texts.append(text)

        embeddings = self.embedder.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        self.index = faiss.IndexFlatIP(embeddings.shape[1])
        self.index.add(embeddings.astype(np.float32))

        self.metadata = signals[
            ["signal_id", "source", "quote", "outcome", "journey_stage", "themes", "confidence", "url"]
        ].to_dict(orient="records")

        faiss.write_index(self.index, str(INDEX_DIR / "signals.faiss"))
        with open(INDEX_DIR / "signals_metadata.json", "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, ensure_ascii=False, default=str)

    def search(self, query: str, k: int = 10) -> list[dict]:
        """Search for relevant signals using semantic similarity."""
        if self.index is None or self.index.ntotal == 0:
            return []

        query_emb = self.embedder.encode([query], normalize_embeddings=True)
        scores, indices = self.index.search(query_emb.astype(np.float32), k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < len(self.metadata):
                item = self.metadata[idx].copy()
                item["similarity"] = float(score)
                results.append(item)
        return results

    def rag_answer(self, question: str, k: int = 8) -> dict:
        """Answer a question using RAG over grounded signals."""
        if self.index is None or self.index.ntotal == 0:
            return {"answer": "No evidence indexed yet. Run extraction first.", "citations": []}

        hits = self.search(question, k=k)
        if not hits:
            return {"answer": "No relevant evidence found.", "citations": []}

        context = "\n\n".join(
            f"[Signal {h['signal_id']}] Source: {h['source']} | Theme: {', '.join(h.get('themes', []))} "
            f"| Outcome: {h.get('outcome', '')} | Stage: {h.get('journey_stage', '')}\n"
            f"Quote: {h['quote']}"
            for h in hits
        )

        prompt = f"""You are an analyst for INDmoney's Growth team. Answer the question using ONLY the provided evidence.
Cite signals by their ID in square brackets. If the evidence doesn't answer the question, say so.

Evidence:
{context}

Question: {question}

Answer with citations:"""

        try:
            response = litellm.completion(
                model=LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=1000,
            )
            answer = response.choices[0].message.content or ""
        except Exception as e:
            answer = f"LLM error: {e}"

        return {"answer": answer, "citations": hits}

    def live_extract(self, text: str) -> dict:
        """Extract signals from new text in real-time with quote verification."""
        from src.pipeline.extract import extract_signals_from_text, verify_quote
        from src.analysis import _match_themes, _primary_outcome, _primary_theme

        if not text or len(text.strip()) < 20:
            return {"signals": [], "error": "Text too short"}

        # Use the same extraction pipeline but for single document
        try:
            signals = extract_signals_from_text(text, doc_id=-1, source="live_input")
        except Exception as e:
            return {"signals": [], "error": f"Extraction failed: {e}"}

        verified = []
        for sig in signals:
            quote = sig.get("quote", "").strip()
            match = verify_quote({"raw": text}, quote) if quote else None
            if quote and (match is None or match.get("soft")):
                continue  # Drop unverified quotes

            row = {
                "triggers": sig.get("triggers", []),
                "behaviors": sig.get("behaviors", []),
                "emotions": sig.get("emotions", []),
                "expectations": sig.get("expectations", []),
                "outcome": sig.get("outcome", "unknown"),
                "quote": quote,
            }
            themes = _match_themes(row)
            sig["themes"] = themes
            sig["primary_theme"] = _primary_theme(themes)
            sig["quote_verified"] = bool(quote and match and not match.get("soft"))
            verified.append(sig)

        return {"signals": verified, "count": len(verified)}

    def theme_narrative(self, theme_slug: str, signals_df: pd.DataFrame) -> str:
        """Generate narrative summary for a theme using LLM."""
        theme_signals = signals_df[signals_df["themes"].apply(lambda x: theme_slug in x)]
        if theme_signals.empty:
            return "No signals for this theme."

        quotes = theme_signals["quote"].tolist()[:15]
        outcomes = theme_signals["outcome"].value_counts().to_dict()
        stages = theme_signals["journey_stage"].value_counts().to_dict()
        sources = theme_signals["source"].value_counts().to_dict()

        prompt = f"""Summarize the '{theme_slug}' theme for INDmoney's Growth team.
Use ONLY the provided quotes. Write 3-4 paragraphs:
1. What happens (behaviors, triggers)
2. How it feels (emotions, expectations)
3. What the outcome tends to be
4. One concrete product implication

Quotes:
{chr(10).join(f'- {q}' for q in quotes)}

Outcomes: {outcomes}
Stages: {stages}
Sources: {sources}

Summary:"""

        try:
            response = litellm.completion(
                model=LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=600,
            )
            return response.choices[0].message.content or "Summary unavailable."
        except Exception as e:
            return f"LLM error: {e}"

    def segment_comparison(self, segment_field: str, segment_values: list[str], signals_df: pd.DataFrame) -> str:
        """Compare patterns across segment values using LLM."""
        if segment_field not in ["income_stability", "age_band", "goal_type", "influence", "source_of_money", "ticket_size"]:
            return "Invalid segment field."

        segments_data = {}
        for val in segment_values:
            seg_signals = signals_df[
                signals_df["segment_cues"].apply(
                    lambda x: isinstance(x, dict) and x.get(segment_field) == val
                )
            ]
            if seg_signals.empty:
                continue
            segments_data[val] = {
                "count": len(seg_signals),
                "themes": seg_signals["themes"].explode().value_counts().head(5).to_dict(),
                "outcomes": seg_signals["outcome"].value_counts().to_dict(),
                "quotes": seg_signals["quote"].tolist()[:5],
            }

        if not segments_data:
            return "No signals for selected segments."

        prompt = f"""Compare {segment_field} segments for INDmoney's Growth team.
For each segment, describe: dominant themes, typical outcomes, and one key difference.
Be specific. Use the quotes as evidence.

Data:
{json.dumps(segments_data, ensure_ascii=False, indent=2)}

Comparison:"""

        try:
            response = litellm.completion(
                model=LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=800,
            )
            return response.choices[0].message.content or "Comparison unavailable."
        except Exception as e:
            return f"LLM error: {e}"


# Singleton instance
_engine = None


def get_engine() -> LiveLLMEngine:
    global _engine
    if _engine is None:
        _engine = LiveLLMEngine()
    return _engine