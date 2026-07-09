"""Faithfulness Metrics.

The pure-function half of the Faithfulness Evaluator, exposed as
staticmethods on :class:`FaithfulnessMetrics`. Every method is
deterministic, side-effect-free, and operates on plain Python values.
There is no IO, no LLM call, no network access, no model download, no
GPU, and no consultation of price data. The class exposes the eight
metric methods that together form the contract documented in
``openspec/changes/faithfulness-evaluator/specs/faithfulness-evaluation/spec.md``:

- ``calculate_prediction_temporal_validity``
- ``calculate_dataset_temporal_validity``
- ``evidence_support_score``
- ``calculate_evidence_support``
- ``confidence_after_removal_for_original_class``
- ``calculate_confidence_drop``
- ``calculate_faithfulness_score``
- ``classify_faithfulness``

The orchestrator that owns ablation, warning collection, and the
``FaithfulnessReport`` dict lives in ``src/faithfulness_evaluator.py``.

The class reuses :class:`src.retriever.TimeUtils` so temporal
comparisons are consistent across the pipeline.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Sequence

from src.retriever import TimeUtils


VERDICTS = frozenset(
    {
        "invalid_temporal_leakage",
        "unsupported_evidence",
        "strong_faithful_candidate",
        "moderate_faithful_candidate",
        "weak_faithful_candidate",
        "decorative_explanation_risk",
    }
)


class FaithfulnessMetrics:
    """Pure metric functions used by :class:`FaithfulnessEvaluator`."""

    VALID_DIRECTIONS = ("UP", "DOWN", "HOLD")
    VERDICTS = VERDICTS

    # -----------------------------------------------------------------
    # Temporal validity
    # -----------------------------------------------------------------

    @classmethod
    def calculate_prediction_temporal_validity(
        cls,
        cited_evidence: Sequence[Mapping[str, Any]],
        forecast_time: Any,
    ) -> float:
        """Return ``1.0`` if every cited item has ``news_time <= forecast_time``.

        Empty cited lists return ``1.0`` (vacuous truth). Any item whose
        parsed ``news_time`` is strictly greater than ``forecast_time``
        returns ``0.0`` immediately. Items with missing or unparseable
        ``news_time`` are treated as not-future (and surfaced via the
        ``MALFORMED_NEWS_TIME`` warning, not by this method).
        """
        if not cited_evidence:
            return 1.0
        if forecast_time is None:
            # Without a forecast time, temporal validity is undefined; treat
            # the empty case as vacuous truth but any item as suspect.
            return 0.0
        forecast_dt = cls._parse_news_time(forecast_time)
        if forecast_dt is None:
            return 0.0
        for item in cited_evidence:
            news_dt = cls._parse_news_time(item.get("news_time"))
            if news_dt is None:
                continue
            if news_dt > forecast_dt:
                return 0.0
        return 1.0

    @classmethod
    def calculate_dataset_temporal_validity(
        cls,
        records: Sequence[Mapping[str, Any]],
    ) -> float:
        """Return the fraction of records whose ``news_time <= forecast_time``.

        An empty batch returns ``1.0`` (no leakage). A record missing or
        with an unparseable ``news_time`` is treated as valid (defensive
        default, matches the Forecast Model).
        """
        total = len(records)
        if total == 0:
            return 1.0
        valid = 0
        for record in records:
            forecast_time = record.get("forecast_time")
            news_time = record.get("news_time")
            if news_time is None or forecast_time is None:
                valid += 1
                continue
            forecast_dt = cls._parse_news_time(forecast_time)
            news_dt = cls._parse_news_time(news_time)
            if forecast_dt is None or news_dt is None:
                valid += 1
                continue
            if news_dt > forecast_dt:
                continue
            valid += 1
        return valid / total

    # -----------------------------------------------------------------
    # Evidence support
    # -----------------------------------------------------------------

    @classmethod
    def evidence_support_score(cls, prediction: str, expected_direction: str) -> float:
        """Return the per-item support score for a single cited evidence item.

        The score is ``1.0`` on an exact directional match, ``0.5`` when
        one side is ``HOLD``, and ``0.0`` for an opposite directional
        match. Unknown ``expected_direction`` values are treated as
        ``HOLD`` (defensive default).
        """
        if not isinstance(prediction, str) or not isinstance(expected_direction, str):
            return 0.0
        if prediction not in cls.VALID_DIRECTIONS:
            return 0.0
        normalized = (
            expected_direction if expected_direction in cls.VALID_DIRECTIONS else "HOLD"
        )
        if prediction == normalized:
            return 1.0
        if prediction == "HOLD" or normalized == "HOLD":
            return 0.5
        return 0.0

    @classmethod
    def calculate_evidence_support(
        cls,
        prediction: str,
        cited_evidence: Sequence[Mapping[str, Any]],
    ) -> float:
        """Return the mean evidence support over the cited set."""
        if not cited_evidence:
            return 1.0
        scores = [
            cls.evidence_support_score(prediction, cls._get_expected_direction(item))
            for item in cited_evidence
        ]
        return sum(scores) / len(scores)

    # -----------------------------------------------------------------
    # Confidence drop
    # -----------------------------------------------------------------

    @staticmethod
    def confidence_after_removal_for_original_class(
        original_prediction: str,
        reduced_prediction: str,
        reduced_confidence: float,
        reduced_class_confidences: Optional[Mapping[str, float]] = None,
    ) -> float:
        """Return the post-removal confidence of the original prediction class.

        Prefers a class-confidence distribution when one is provided.
        When no distribution is available, returns the reduced confidence
        if the prediction is unchanged, and falls back to ``0.0`` if the
        prediction has flipped.
        """
        if (
            reduced_class_confidences is not None
            and isinstance(reduced_class_confidences, Mapping)
            and original_prediction in reduced_class_confidences
        ):
            value = reduced_class_confidences[original_prediction]
            try:
                return float(value)
            except (TypeError, ValueError):
                pass
        if reduced_prediction == original_prediction:
            try:
                return float(reduced_confidence)
            except (TypeError, ValueError):
                return 0.0
        return 0.0

    @classmethod
    def calculate_confidence_drop(
        cls,
        original_confidence: float,
        original_prediction: str,
        reduced_prediction: str,
        reduced_confidence: float,
        reduced_class_confidences: Optional[Mapping[str, float]] = None,
    ) -> float:
        """Return ``original_confidence - confidence_after_removal`` (signed)."""
        after = cls.confidence_after_removal_for_original_class(
            original_prediction=original_prediction,
            reduced_prediction=reduced_prediction,
            reduced_confidence=reduced_confidence,
            reduced_class_confidences=reduced_class_confidences,
        )
        try:
            original = float(original_confidence)
        except (TypeError, ValueError):
            original = 0.0
        return original - after

    # -----------------------------------------------------------------
    # Composite score
    # -----------------------------------------------------------------

    @classmethod
    def calculate_faithfulness_score(
        cls,
        temporal_validity: float,
        evidence_support: float,
        confidence_drop: float,
    ) -> float:
        """Return the V1 composite faithfulness score in ``[0.0, 1.0]``.

        Negative ``confidence_drop`` is clamped to ``0.0`` for the
        composite only; the signed drop is preserved in the report.
        """
        tv = cls.clamp01(temporal_validity)
        es = cls.clamp01(evidence_support)
        try:
            cd = float(confidence_drop)
        except (TypeError, ValueError):
            cd = 0.0
        normalized_drop = min(max(cd, 0.0) / 0.30, 1.0)
        score = 0.35 * tv + 0.30 * es + 0.35 * normalized_drop
        return max(0.0, min(1.0, score))

    # -----------------------------------------------------------------
    # Verdict
    # -----------------------------------------------------------------

    @classmethod
    def classify_faithfulness(
        cls,
        temporal_validity: float,
        evidence_support: float,
        confidence_drop: float,
        prediction: str,
        prediction_after_removal: str,
        cited_evidence: Optional[Sequence[Mapping[str, Any]]] = None,
    ) -> str:
        """Return one of the six pinned verdicts via the ordered cascade.

        The branches are evaluated in the documented order and stop at
        the first match. Out-of-range ``temporal_validity`` and
        ``evidence_support`` are clamped to ``[0.0, 1.0]`` before the
        branches run. When ``cited_evidence`` is provided and is empty,
        the classifier short-circuits to ``decorative_explanation_risk``
        — there is no cited evidence to be faithful to.
        """
        if cited_evidence is not None and len(cited_evidence) == 0:
            return "decorative_explanation_risk"
        tv = cls.clamp01(temporal_validity)
        es = cls.clamp01(evidence_support)
        try:
            cd = float(confidence_drop)
        except (TypeError, ValueError):
            cd = 0.0
        if tv < 1.0:
            return "invalid_temporal_leakage"
        if es < 0.5:
            return "unsupported_evidence"
        if prediction_after_removal != prediction:
            return "strong_faithful_candidate"
        if cd >= 0.20:
            return "strong_faithful_candidate"
        if cd >= 0.10:
            return "moderate_faithful_candidate"
        if cd >= 0.05:
            return "weak_faithful_candidate"
        return "decorative_explanation_risk"

    # -----------------------------------------------------------------
    # Per-evidence results (used by the orchestrator)
    # -----------------------------------------------------------------

    @classmethod
    def build_per_evidence_results(
        cls,
        prediction: str,
        cited_evidence: Sequence[Mapping[str, Any]],
        forecast_time: Any,
    ) -> List[Dict[str, Any]]:
        """Return a sorted list of per-evidence result dicts.

        The list is sorted by ``evidence_id`` ascending. Items whose
        ``news_time`` is strictly greater than ``forecast_time`` carry
        the temporal-leakage warning in the ``temporal_warning`` field;
        items with missing or unparseable ``news_time`` carry the
        ``MALFORMED_NEWS_TIME`` warning.
        """
        forecast_dt: Optional[datetime] = None
        if forecast_time is not None:
            forecast_dt = cls._parse_news_time(forecast_time)

        rows: List[Dict[str, Any]] = []
        for item in cited_evidence:
            evidence_id = cls._get_evidence_id(item)
            news_id = item.get("news_id", "")
            if not isinstance(news_id, str):
                news_id = ""
            news_time = item.get("news_time", "")
            if not isinstance(news_time, str):
                news_time = ""
            expected_direction = cls._get_expected_direction(item)
            support_score = cls.evidence_support_score(prediction, expected_direction)
            is_cited = bool(item.get("is_cited", True))
            temporal_warning = ""
            if forecast_dt is not None and news_time:
                news_dt = cls._parse_news_time(news_time)
                if news_dt is None:
                    temporal_warning = f"MALFORMED_NEWS_TIME: evidence_id={evidence_id}"
                elif news_dt > forecast_dt:
                    temporal_warning = f"TEMPORAL_LEAKAGE: evidence_id={evidence_id}"
            elif forecast_dt is not None and not news_time:
                temporal_warning = f"MALFORMED_NEWS_TIME: evidence_id={evidence_id}"
            rows.append(
                {
                    "evidence_id": evidence_id,
                    "news_id": news_id,
                    "news_time": news_time,
                    "expected_direction": expected_direction,
                    "support_score": support_score,
                    "is_cited": is_cited,
                    "temporal_warning": temporal_warning,
                }
            )
        rows.sort(key=lambda row: row.get("evidence_id", ""))
        return rows

    @staticmethod
    def empty_per_evidence_results() -> List[Dict[str, Any]]:
        """Return an empty per-evidence-results list (the empty-cited case)."""
        return []

    # -----------------------------------------------------------------
    # Warning collectors (used by the orchestrator)
    # -----------------------------------------------------------------

    @classmethod
    def collect_temporal_warnings(
        cls,
        cited_evidence: Sequence[Mapping[str, Any]],
        forecast_time: Any,
    ) -> List[str]:
        """Return warning strings for temporal-leakage and malformed items."""
        warnings: List[str] = []
        if not cited_evidence or forecast_time is None:
            return warnings
        forecast_dt = cls._parse_news_time(forecast_time)
        if forecast_dt is None:
            return warnings
        for item in cited_evidence:
            evidence_id = cls._get_evidence_id(item)
            raw_news_time = item.get("news_time")
            if raw_news_time is None or (
                isinstance(raw_news_time, str) and not raw_news_time.strip()
            ):
                warnings.append(f"MALFORMED_NEWS_TIME: evidence_id={evidence_id}")
                continue
            news_dt = cls._parse_news_time(raw_news_time)
            if news_dt is None:
                warnings.append(f"MALFORMED_NEWS_TIME: evidence_id={evidence_id}")
                continue
            if news_dt > forecast_dt:
                warnings.append(
                    f"TEMPORAL_LEAKAGE: evidence_id={evidence_id}, "
                    f"news_time={news_dt.isoformat()}, "
                    f"forecast_time={forecast_dt.isoformat()}"
                )
        return warnings

    @classmethod
    def collect_support_warnings(
        cls,
        prediction: str,
        cited_evidence: Sequence[Mapping[str, Any]],
    ) -> List[str]:
        """Return one warning per cited item whose per-item score is below 1.0."""
        warnings: List[str] = []
        for item in cited_evidence:
            evidence_id = cls._get_evidence_id(item)
            expected_direction = cls._get_expected_direction(item)
            score = cls.evidence_support_score(prediction, expected_direction)
            if score < 1.0:
                warnings.append(
                    f"UNSUPPORTED: evidence_id={evidence_id}, "
                    f"expected_direction={expected_direction}, score={score}"
                )
        return warnings

    # -----------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------

    @staticmethod
    def _parse_news_time(value: Any) -> Optional[datetime]:
        """Parse a ``news_time`` value as a UTC-naive ``datetime``.

        Reuses :class:`TimeUtils` so naive timestamps are interpreted as
        UTC consistently across the pipeline. Returns ``None`` for
        missing, ``None``, or unparseable values.
        """
        if value is None or not isinstance(value, str):
            return None
        try:
            return TimeUtils.parse_utc(value)
        except ValueError:
            return None

    @staticmethod
    def _get_evidence_id(item: Mapping[str, Any]) -> str:
        """Return the ``evidence_id`` of an evidence item, or empty string."""
        value = item.get("evidence_id", "")
        return value if isinstance(value, str) else ""

    @staticmethod
    def _get_expected_direction(item: Mapping[str, Any]) -> str:
        """Return the ``expected_direction`` of an evidence item, or empty string."""
        value = item.get("expected_direction", "")
        return value if isinstance(value, str) else ""

    @staticmethod
    def clamp01(value: Any) -> float:
        try:
            v = float(value)
        except (TypeError, ValueError):
            return 0.0
        if v < 0.0:
            return 0.0
        if v > 1.0:
            return 1.0
        return v
