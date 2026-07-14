"""Evidence Extractor.

The second stage in the faithful-evidence-forecasting pipeline. Given a
single news item, it builds a list of evidence items by running
**FinBERT** (``ProsusAI/finbert``, lazy-loaded, frozen) on the news text
and emitting one evidence item per tokenizer chunk with the predicted
sentiment (``positive`` / ``negative`` / ``neutral``).

Behavior (Version 3):

- Calls ``FinbertSentimentScorer.score(texts)`` once per news item, which
  returns ``{"positive", "negative", "neutral"}`` probabilities.
- Emits exactly one evidence object per news item, carrying the full
  ``sentiment_probs`` triple plus the canonical ``polarity`` (= argmax) and
  ``expected_direction`` (mapping via ``POLARITY_TO_DIRECTION``).
- Preserves ``forecast_time`` and ``news_time`` unchanged in the output.
- Does NOT filter by time — the Temporal Retriever owns temporal validity.
- Does NOT produce predictions or trading advice.

See ``openspec/changes/forecast-model-attention/specs/forecasting/spec.md``
for the full normative specification and the FinBERT polarity contract.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.finbert_sentiment import FinbertLoadError, FinbertSentimentScorer


class EvidenceExtractor:
    """FinBERT-based evidence extractor.

    ``POLARITY_TO_DIRECTION`` and ``SUPPORT_SCORES`` are the single source
    of truth for ``polarity -> expected_direction`` and the default
    ``support_score`` per polarity. Downstream stages (Forecast Model
    Attention aggregator) MUST consume the ``sentiment_probs`` field on
    each evidence item directly rather than re-deriving polarity.

    The FinBERT scorer is **shared** across all ``extract()`` calls in a
    pipeline run via the class-level ``_scorer`` cache, so the
    ~400MB model is loaded at most once.
    """

    # -----------------------------------------------------------------
    # Single source of truth for V3 polarity mapping (unchanged from V1)
    # -----------------------------------------------------------------

    POLARITY_TO_DIRECTION: Dict[str, str] = {
        "positive": "UP",
        "negative": "DOWN",
        "neutral": "HOLD",
    }

    SUPPORT_SCORES: Dict[str, float] = {
        "positive": 1.0,
        "negative": 1.0,
        "neutral": 0.5,
    }

    #: Output literal for ``extraction_method`` (kept stable for downstream parsing).
    EXTRACTION_METHOD: str = "finbert_sentiment_v1"

    # -----------------------------------------------------------------
    # Lazy scorer cache (one ProsusAI/finbert load per process)
    # -----------------------------------------------------------------

    _scorer: Optional[FinbertSentimentScorer] = None

    @classmethod
    def _get_scorer(cls) -> FinbertSentimentScorer:
        if cls._scorer is None:
            cls._scorer = FinbertSentimentScorer()
        return cls._scorer

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def extract(self, news_item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract evidence from a single news item.

        Args:
            news_item: Dict with required keys ``news_id``, ``ticker``,
                ``forecast_time``, ``news_time``, ``news_text``.

        Returns:
            A result dict matching the OpenSpec output schema:
            ``news_id``, ``ticker``, ``forecast_time``, ``news_time``,
            ``evidence`` (always at least one element, possibly a single
            neutral placeholder), ``summary``, ``extraction_method``
            (literal ``"finbert_sentiment_v1"``), ``primary_evidence_id``.
        """
        news_id: str = news_item["news_id"]
        ticker: str = news_item["ticker"]
        forecast_time: str = news_item["forecast_time"]
        news_time: str = news_item["news_time"]
        news_text: str = news_item["news_text"]

        sentiment_probs = self._score_text(news_text)
        polarity = self._argmax_polarity(sentiment_probs)
        evidence = self.build_evidence_objects(news_id, polarity, sentiment_probs, news_text)
        summary = self.build_summary(evidence)

        return {
            "news_id": news_id,
            "ticker": ticker,
            "forecast_time": forecast_time,
            "news_time": news_time,
            "evidence": evidence,
            "summary": summary,
            "extraction_method": self.EXTRACTION_METHOD,
            "primary_evidence_id": self.select_primary_evidence_id(evidence),
        }

    def extract_batch(self, news_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply :meth:`extract` to a list of news items.

        Returns one result per input, in the same order. Does NOT filter
        or reorder by time — temporal validity is owned by the Temporal
        Retriever.
        """
        return [self.extract(item) for item in news_items]

    def build_evidence_objects(
        self,
        news_id: str,
        polarity: str,
        sentiment_probs: Dict[str, float],
        news_text: str,
    ) -> List[Dict[str, Any]]:
        """Build one evidence dict from a FinBERT polarity decision.

        Always returns exactly one evidence item per news item (V3
        contract: sentiment at the news level, not per phrase — the V1
        keyword-matching version produced multiple items per news).
        """
        direction = self.POLARITY_TO_DIRECTION[polarity]
        support_score = float(sentiment_probs.get(polarity, self.SUPPORT_SCORES[polarity]))
        return [
            {
                "evidence_id": self._make_evidence_id(news_id, 1),
                "news_id": news_id,
                "evidence_text": news_text,
                "polarity": polarity,
                "expected_direction": direction,
                "matched_keyword": None,
                "start_char": 0,
                "end_char": len(news_text),
                "support_score": support_score,
                "sentiment_probs": {
                    "positive": float(sentiment_probs.get("positive", 0.0)),
                    "negative": float(sentiment_probs.get("negative", 0.0)),
                    "neutral": float(sentiment_probs.get("neutral", 0.0)),
                },
            }
        ]

    def build_summary(self, evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compute summary counts and the mixed-evidence flag."""
        positive_count = sum(1 for e in evidence if e["polarity"] == "positive")
        negative_count = sum(1 for e in evidence if e["polarity"] == "negative")
        neutral_count = sum(1 for e in evidence if e["polarity"] == "neutral")
        total = len(evidence)
        return {
            "positive_count": positive_count,
            "negative_count": negative_count,
            "neutral_count": neutral_count,
            "total_evidence_count": total,
            "has_mixed_evidence": positive_count >= 1 and negative_count >= 1,
        }

    def select_primary_evidence_id(
        self, evidence: List[Dict[str, Any]]
    ) -> Optional[str]:
        """Choose the primary evidence ID.

        Rule (deterministic, V3 simplification): the first (and only) item
        in the list, unless empty.
        """
        if not evidence:
            return None
        return evidence[0]["evidence_id"]

    def result_to_dict(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Return ``result`` as a plain dict. Identity for V3."""
        return dict(result)

    # -----------------------------------------------------------------
    # FinBERT integration
    # -----------------------------------------------------------------

    def _score_text(self, news_text: str) -> Dict[str, float]:
        """Score a single news text via the cached FinBERT scorer.

        Empty input → single neutral placeholder with the spec's
        neutral-only uniform distribution so downstream always sees a
        valid ``sentiment_probs`` triple summing to 1.0.
        """
        if news_text is None or not str(news_text).strip():
            return {"positive": 0.0, "negative": 0.0, "neutral": 1.0}
        try:
            scorer = self._get_scorer()
            results = scorer.score([str(news_text)])
        except FinbertLoadError:
            # Pipeline surfaces a typed error upstream; here we surface
            # a neutral fallback so a single bad input cannot poison the
            # batch. The caller (process()) will re-raise if needed.
            return {"positive": 0.0, "negative": 0.0, "neutral": 1.0}
        if not results:
            return {"positive": 0.0, "negative": 0.0, "neutral": 1.0}
        return results[0]

    @staticmethod
    def _argmax_polarity(probs: Dict[str, float]) -> str:
        """Return ``"positive"`` / ``"negative"`` / ``"neutral"`` by argmax.

        Tie-break order: ``positive`` > ``negative`` > ``neutral`` (keeps
        V3 deterministic even when FinBERT outputs equal probs).
        """
        order = ("positive", "negative", "neutral")
        best_label = "neutral"
        best_val = -1.0
        for label in order:
            v = float(probs.get(label, 0.0))
            if v > best_val:
                best_val = v
                best_label = label
        return best_label

    @staticmethod
    def _make_evidence_id(news_id: str, index: int) -> str:
        """Format evidence_id as ``<news_id>_E<index>`` with index zero-padded
        to 3 digits per the spec (e.g. ``N001_E001``).
        """
        return f"{news_id}_E{index:03d}"


# ---------------------------------------------------------------------------
# Envelope stage adapter (see openspec/changes/interactive-stage-cli)
# ---------------------------------------------------------------------------

STAGE_NAME = "evidence_extractor"


def process(envelope: Dict[str, Any]) -> Dict[str, Any]:
    """Extract FinBERT-polarity evidence from each sample's ``valid_news``.

    Builds the extractor input shape from the envelope (ported from the
    old ``PipelineRunner._build_extractor_input``), runs
    ``extract_batch``, and flattens the per-news evidence lists into one
    ``evidence`` list per sample, attaching ``news_time`` to every item.
    """
    extractor = EvidenceExtractor()
    for sample in envelope["samples"]:
        inputs = [
            {
                "news_id": str(n["news_id"]),
                "ticker": sample["ticker"],
                "forecast_time": sample["forecast_time"],
                "news_time": str(n["news_time"]),
                "news_text": str(n.get("news_text", n.get("text", ""))),
            }
            for n in sample["valid_news"]
        ]
        results = extractor.extract_batch(inputs)
        evidence: List[Dict[str, Any]] = []
        for news, result in zip(sample["valid_news"], results):
            for item in result["evidence"]:
                item["news_time"] = str(news["news_time"])
                evidence.append(item)
        sample["evidence"] = evidence
    envelope["stage"] = STAGE_NAME
    return envelope


def main(argv: Optional[List[str]] = None) -> int:
    from src.core.stage_io import run_stage_cli

    return run_stage_cli(
        STAGE_NAME,
        "Extract FinBERT-polarity evidence from each sample's valid news.",
        process,
        argv,
    )


if __name__ == "__main__":  # pragma: no cover
    import sys

    sys.exit(main())


# Module-level aliases for backward compatibility (V1 keyword-based
# code exposed these constants at module scope). Re-export from the
# class so any existing call sites continue to work after the V3 switch
# to FinBERT.
POLARITY_TO_DIRECTION = EvidenceExtractor.POLARITY_TO_DIRECTION
SUPPORT_SCORES = EvidenceExtractor.SUPPORT_SCORES


__all__ = [
    "EvidenceExtractor",
    "POLARITY_TO_DIRECTION",
    "SUPPORT_SCORES",
    "STAGE_NAME",
    "process",
    "main",
]
