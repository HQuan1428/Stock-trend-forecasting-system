"""Faithfulness Evaluator.

The orchestrator half of the Faithfulness Evaluator. Given a
``ForecastResult`` and the input envelope that produced it, the
``FaithfulnessEvaluator`` class computes the three required metrics
(``temporal_validity``, ``evidence_support``, ``confidence_drop``), the
optional composite ``faithfulness_score``, a readable ``verdict``, and
the warning lists / per-evidence breakdown that the Visualization
Dashboard consumes.

Version 1 is **deterministic, rule-based, and side-effect-free in
single-evaluation mode**. It does NOT use any LLM, FinBERT, transformer,
logistic regression, deep-learning model, or external API. It does NOT
read raw ``news_text`` or price data. It does NOT re-extract or
re-classify evidence. It re-invokes ``ForecastModel.predict_without_evidence``
to produce the post-ablation prediction, and re-uses the pure metric
methods from :class:`src.faithfulness_metrics.FaithfulnessMetrics` for
the math.

The module exposes:

- :class:`FaithfulnessEvaluatorError` — typed error for unrecoverable
  input problems.
- :class:`FaithfulnessEvaluator` — the main class with public methods
  ``evaluate`` (single) and ``evaluate_batch`` (batch, writes CSV/JSON).
- Class constants: ``ABLATION_STRATEGIES``, ``CSV_COLUMNS``,
  ``CSV_DEFAULT_PATH``, ``JSON_DEFAULT_PATH``.

See ``openspec/changes/faithfulness-evaluator/specs/faithfulness-evaluation/spec.md``
for the normative specification.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from src.faithfulness_metrics import FaithfulnessMetrics


class FaithfulnessEvaluatorError(ValueError):
    """Raised for unrecoverable input problems (missing prediction, etc.)."""


class FaithfulnessEvaluator:
    """Evaluate a single ``ForecastResult`` and return a ``FaithfulnessReport``."""

    #: V1 ablation strategies. The first entry is the default.
    ABLATION_STRATEGIES: Tuple[str, ...] = (
        "remove_cited_pro_evidence",
        "remove_all_cited_evidence",
    )

    #: Required columns for the batch CSV output, in order.
    CSV_COLUMNS: Tuple[str, ...] = (
        "ticker",
        "forecast_time",
        "prediction",
        "original_confidence",
        "prediction_after_removal",
        "confidence_after_removal",
        "confidence_drop",
        "temporal_validity",
        "evidence_support",
        "faithfulness_score",
        "verdict",
        "warnings",
    )

    #: Default CSV output path for :meth:`evaluate_batch`.
    CSV_DEFAULT_PATH: str = "outputs/faithfulness_results.csv"

    #: Default JSON output path for :meth:`evaluate_batch`.
    JSON_DEFAULT_PATH: str = "outputs/faithfulness_results.json"

    #: Valid prediction labels.
    VALID_PREDICTIONS: Tuple[str, ...] = ("UP", "DOWN", "HOLD")

    #: The two scenarios when ``confidence_increased_after_removal`` is raised.
    _NEGATIVE_DROP_MARKER = "confidence_increased_after_removal"
    _FORECAST_ERROR_MARKER = "FORECAST_MODEL_ERROR: "
    _EVALUATION_ERROR_MARKER = "EVALUATION_ERROR: "

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def evaluate(
        self,
        original_input: Mapping[str, Any],
        original_result: Mapping[str, Any],
        *,
        ablation_strategy: str = "remove_cited_pro_evidence",
    ) -> Dict[str, Any]:
        """Compute the faithfulness report for one prediction.

        Raises :class:`FaithfulnessEvaluatorError` on unrecoverable
        input problems (missing ``prediction``, invalid
        ``ablation_strategy``, etc.). Defensive defaults apply for
        missing fields inside the evidence list (treated as
        not-future, neutral, etc., to match the Forecast Model).
        """
        if not isinstance(original_input, Mapping):
            raise FaithfulnessEvaluatorError("original_input must be a dict")
        if not isinstance(original_result, Mapping):
            raise FaithfulnessEvaluatorError("original_result must be a dict")
        if ablation_strategy not in self.ABLATION_STRATEGIES:
            raise FaithfulnessEvaluatorError(
                f"ablation_strategy must be one of {self.ABLATION_STRATEGIES}, "
                f"got {ablation_strategy!r}"
            )
        prediction = original_result.get("prediction")
        if prediction not in self.VALID_PREDICTIONS:
            raise FaithfulnessEvaluatorError(
                f"prediction must be one of {self.VALID_PREDICTIONS}, "
                f"got {prediction!r}"
            )
        original_confidence = original_result.get("confidence")
        if not isinstance(original_confidence, (int, float)) or isinstance(
            original_confidence, bool
        ):
            raise FaithfulnessEvaluatorError(
                f"confidence must be numeric, got {original_confidence!r}"
            )

        forecast_time = self._extract_forecast_time(original_input, original_result)
        if not forecast_time:
            raise FaithfulnessEvaluatorError(
                "forecast_time is required (neither original_result nor "
                "original_input carries one)"
            )

        cited_evidence = self._extract_cited_evidence(original_result)

        temporal_validity = FaithfulnessMetrics.calculate_prediction_temporal_validity(
            cited_evidence, forecast_time
        )
        evidence_support = FaithfulnessMetrics.calculate_evidence_support(
            prediction, cited_evidence
        )

        # Ablation. ``predict_without_evidence`` accepts evidence IDs.
        # The news-id collapse is documented in the design as a fallback
        # for a hypothetical model that only accepts news-level input;
        # the current Forecast Model handles evidence IDs directly, so
        # the collapse is a no-op for V1. We still call it to record the
        # expansion warnings when multiple evidence snippets share a
        # news_id — the warnings are surfaced in the report.
        removed_ids, ablation_warnings = self._select_removed_evidence_ids(
            ablation_strategy, original_result
        )
        _collapsed_ids, expand_warnings = self._expand_to_news_ids(
            removed_ids, original_input
        )
        ablation_warnings.extend(expand_warnings)
        # When the Forecast Model accepts evidence IDs (the current
        # contract), prefer the evidence-ID list. The collapsed list
        # would be a no-op pass-through (the model filters by evidence
        # IDs that no longer exist). We use the original ``removed_ids``
        # list here.
        reduced_result, ablation_runtime_warnings = self._invoke_ablation(
            original_input, removed_ids
        )
        ablation_warnings.extend(ablation_runtime_warnings)

        reduced_prediction = reduced_result.get("prediction", "HOLD")
        if reduced_prediction not in self.VALID_PREDICTIONS:
            reduced_prediction = "HOLD"
        reduced_confidence = reduced_result.get("confidence", 0.5)
        if not isinstance(reduced_confidence, (int, float)) or isinstance(
            reduced_confidence, bool
        ):
            reduced_confidence = 0.5
        reduced_class_confidences = reduced_result.get("class_confidences")

        confidence_drop = FaithfulnessMetrics.calculate_confidence_drop(
            original_confidence=float(original_confidence),
            original_prediction=prediction,
            reduced_prediction=reduced_prediction,
            reduced_confidence=float(reduced_confidence),
            reduced_class_confidences=(
                reduced_class_confidences
                if isinstance(reduced_class_confidences, Mapping)
                else None
            ),
        )
        confidence_after_removal = float(original_confidence) - confidence_drop

        if confidence_drop < 0:
            ablation_warnings.append(self._NEGATIVE_DROP_MARKER)

        faithfulness_score = FaithfulnessMetrics.calculate_faithfulness_score(
            temporal_validity, evidence_support, confidence_drop
        )
        verdict = FaithfulnessMetrics.classify_faithfulness(
            temporal_validity=temporal_validity,
            evidence_support=evidence_support,
            confidence_drop=confidence_drop,
            prediction=prediction,
            prediction_after_removal=reduced_prediction,
            cited_evidence=cited_evidence,
        )

        temporal_warnings = FaithfulnessMetrics.collect_temporal_warnings(
            cited_evidence, forecast_time
        )
        support_warnings = FaithfulnessMetrics.collect_support_warnings(
            prediction, cited_evidence
        )

        if cited_evidence:
            per_evidence_results = FaithfulnessMetrics.build_per_evidence_results(
                prediction, cited_evidence, forecast_time
            )
        else:
            per_evidence_results = FaithfulnessMetrics.empty_per_evidence_results()

        # Fall-through safety: verdict must be one of VERDICTS, even if
        # ``prediction_after_removal`` is somehow not a string.
        if verdict not in FaithfulnessMetrics.VERDICTS:
            verdict = "decorative_explanation_risk"

        return {
            "sample_id": self._extract_sample_id(original_input, original_result),
            "ticker": self._extract_ticker(original_input, original_result),
            "forecast_time": forecast_time,
            "prediction": prediction,
            "original_confidence": float(original_confidence),
            "temporal_validity": FaithfulnessMetrics.clamp01(temporal_validity),
            "evidence_support": FaithfulnessMetrics.clamp01(evidence_support),
            "confidence_drop": confidence_drop,
            "confidence_after_removal": confidence_after_removal,
            "prediction_after_removal": reduced_prediction,
            "faithfulness_score": faithfulness_score,
            "verdict": verdict,
            "temporal_warnings": temporal_warnings,
            "support_warnings": support_warnings,
            "ablation_warnings": ablation_warnings,
            "per_evidence_results": per_evidence_results,
        }

    def evaluate_batch(
        self,
        reports: Sequence[Any],
        *,
        output_csv_path: Optional[str] = None,
        output_json_path: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Evaluate a batch of pre-computed (input, result) pairs.

        Each element of ``reports`` is a tuple ``(original_input,
        original_result)``. Returns a list of report dicts in input
        order, writes a CSV when ``output_csv_path`` is provided, and
        writes a JSON sibling when ``output_json_path`` is provided.
        Per-record errors are caught and recorded as a placeholder
        report with ``verdict = "unsupported_evidence"``; the batch
        never raises.
        """
        evaluated: List[Dict[str, Any]] = []
        csv_rows: List[Dict[str, Any]] = []
        for entry in reports:
            if not isinstance(entry, tuple) or len(entry) != 2:
                evaluated.append(
                    self._default_error_report(
                        None, None, "entry must be a (input, result) tuple"
                    )
                )
                csv_rows.append(self._flatten_report_to_csv_row(evaluated[-1]))
                continue
            original_input, original_result = entry
            try:
                report = self.evaluate(original_input, original_result)
            except FaithfulnessEvaluatorError as exc:
                report = self._default_error_report(
                    original_input, original_result, str(exc)
                )
            except Exception as exc:  # pragma: no cover - defensive
                report = self._default_error_report(
                    original_input, original_result, str(exc)
                )
            evaluated.append(report)
            csv_rows.append(self._flatten_report_to_csv_row(report))

        if output_csv_path:
            self._write_csv(csv_rows, Path(output_csv_path))
        if output_json_path:
            self._write_json(evaluated, Path(output_json_path))
        return evaluated

    # -----------------------------------------------------------------
    # Internal extraction helpers
    # -----------------------------------------------------------------

    @staticmethod
    def _extract_forecast_time(
        original_input: Mapping[str, Any],
        original_result: Mapping[str, Any],
    ) -> str:
        """Return the forecast time from the result, falling back to the input."""
        for source in (original_result, original_input):
            value = source.get("forecast_time", "")
            if isinstance(value, str) and value.strip():
                return value
        return ""

    @staticmethod
    def _extract_sample_id(
        original_input: Mapping[str, Any],
        original_result: Mapping[str, Any],
    ) -> str:
        """Return the sample_id from the result, falling back to the input."""
        for source in (original_result, original_input):
            value = source.get("sample_id", "")
            if isinstance(value, str) and value:
                return value
        return ""

    @staticmethod
    def _extract_ticker(
        original_input: Mapping[str, Any],
        original_result: Mapping[str, Any],
    ) -> str:
        """Return the ticker from the result, falling back to the input."""
        for source in (original_result, original_input):
            value = source.get("ticker", "")
            if isinstance(value, str) and value:
                return value
        return ""

    @staticmethod
    def _extract_cited_evidence(
        original_result: Mapping[str, Any],
    ) -> List[Dict[str, Any]]:
        """Return the cited evidence list with documented fallback chain."""
        pro = original_result.get("pro_evidence")
        counter = original_result.get("counter_evidence")
        if isinstance(pro, list) or isinstance(counter, list):
            cited: List[Dict[str, Any]] = []
            if isinstance(pro, list):
                cited.extend(item for item in pro if isinstance(item, Mapping))
            if isinstance(counter, list):
                cited.extend(item for item in counter if isinstance(item, Mapping))
            return cited
        cited_field = original_result.get("cited_evidence")
        if isinstance(cited_field, list):
            return [item for item in cited_field if isinstance(item, Mapping)]
        return []

    @staticmethod
    def _safe_list(value: Any) -> List[Any]:
        if isinstance(value, list):
            return list(value)
        return []

    # -----------------------------------------------------------------
    # Ablation
    # -----------------------------------------------------------------

    def _select_removed_evidence_ids(
        self,
        strategy: str,
        original_result: Mapping[str, Any],
    ) -> Tuple[List[str], List[str]]:
        """Return ``(removed_evidence_ids, ablation_warnings)`` for the strategy."""
        warnings: List[str] = []
        if strategy == "remove_cited_pro_evidence":
            pro = self._safe_list(original_result.get("pro_evidence"))
            ids = [
                str(item.get("evidence_id", ""))
                for item in pro
                if isinstance(item, Mapping) and item.get("evidence_id")
            ]
            return ids, warnings
        if strategy == "remove_all_cited_evidence":
            pro = self._safe_list(original_result.get("pro_evidence"))
            counter = self._safe_list(original_result.get("counter_evidence"))
            ids: List[str] = []
            for group in (pro, counter):
                for item in group:
                    if isinstance(item, Mapping) and item.get("evidence_id"):
                        ids.append(str(item.get("evidence_id")))
            return ids, warnings
        return [], warnings

    @staticmethod
    def _expand_to_news_ids(
        removed_evidence_ids: Sequence[str],
        original_input: Mapping[str, Any],
    ) -> Tuple[List[str], List[str]]:
        """Map each removed ``evidence_id`` to its ``news_id`` and dedupe.

        Returns the collapsed list of news IDs plus a list of warnings
        documenting which news IDs were expanded from which evidence IDs.
        The Forecast Model's ``predict_without_evidence`` accepts an
        evidence-id list; this helper exists to support the documented
        news-level collapse path and to record the expansion in the
        report's ``ablation_warnings``.
        """
        warnings: List[str] = []
        evidence = FaithfulnessEvaluator._safe_list(original_input.get("evidence"))
        if not evidence or not removed_evidence_ids:
            return list(removed_evidence_ids), warnings
        id_to_news: Dict[str, str] = {}
        for item in evidence:
            if not isinstance(item, Mapping):
                continue
            evidence_id = item.get("evidence_id")
            news_id = item.get("news_id", "")
            if evidence_id and isinstance(news_id, str) and news_id:
                id_to_news[str(evidence_id)] = news_id
        groups: Dict[str, List[str]] = {}
        for evidence_id in removed_evidence_ids:
            news_id = id_to_news.get(evidence_id, evidence_id)
            groups.setdefault(news_id, []).append(evidence_id)
        collapsed: List[str] = []
        for news_id, evidence_ids in groups.items():
            collapsed.append(news_id)
            if len(evidence_ids) > 1:
                warnings.append(
                    f"COLLAPSED_BY_NEWS_ID: {news_id} (expanded from "
                    f"{','.join(sorted(evidence_ids))})"
                )
        return collapsed, warnings

    def _invoke_ablation(
        self,
        original_input: Mapping[str, Any],
        removed_evidence_ids: Sequence[str],
    ) -> Tuple[Dict[str, Any], List[str]]:
        """Call the Forecast Model and catch ``ForecastModelError``.

        Returns ``(reduced_result, ablation_warnings)``. On error, the
        reduced result is a default ``{"prediction": "HOLD", "confidence":
        0.5}`` and a ``FORECAST_MODEL_ERROR: <message>`` warning is added.
        This method MUST NOT raise.
        """
        warnings: List[str] = []
        try:
            # Imported lazily to avoid a circular import at module load.
            from src.forecast_model import ForecastModel, ForecastModelError
        except Exception as exc:  # pragma: no cover - defensive
            return (
                {"prediction": "HOLD", "confidence": 0.5},
                [f"{self._FORECAST_ERROR_MARKER}{exc}"],
            )
        try:
            reduced = ForecastModel().predict_without_evidence(
                dict(original_input),
                list(removed_evidence_ids),
            )
        except ForecastModelError as exc:
            return (
                {"prediction": "HOLD", "confidence": 0.5},
                [f"{self._FORECAST_ERROR_MARKER}{exc}"],
            )
        except Exception as exc:  # pragma: no cover - defensive
            return (
                {"prediction": "HOLD", "confidence": 0.5},
                [f"{self._FORECAST_ERROR_MARKER}{exc}"],
            )
        if not isinstance(reduced, Mapping):
            return (
                {"prediction": "HOLD", "confidence": 0.5},
                [f"{self._FORECAST_ERROR_MARKER}non-dict result from predict_without_evidence"],
            )
        return dict(reduced), warnings

    # -----------------------------------------------------------------
    # Batch helpers
    # -----------------------------------------------------------------

    def _flatten_report_to_csv_row(self, report: Mapping[str, Any]) -> Dict[str, Any]:
        """Map a report dict to a single CSV row (12 columns, warnings JSON-encoded)."""
        warnings_combined: List[str] = []
        for key in ("temporal_warnings", "support_warnings", "ablation_warnings"):
            value = report.get(key, [])
            if isinstance(value, list):
                warnings_combined.extend(str(item) for item in value)
        return {
            "ticker": report.get("ticker", ""),
            "forecast_time": report.get("forecast_time", ""),
            "prediction": report.get("prediction", ""),
            "original_confidence": report.get("original_confidence", 0.0),
            "prediction_after_removal": report.get("prediction_after_removal", ""),
            "confidence_after_removal": report.get("confidence_after_removal", 0.0),
            "confidence_drop": report.get("confidence_drop", 0.0),
            "temporal_validity": report.get("temporal_validity", 0.0),
            "evidence_support": report.get("evidence_support", 0.0),
            "faithfulness_score": report.get("faithfulness_score", 0.0),
            "verdict": report.get("verdict", "decorative_explanation_risk"),
            "warnings": json.dumps(warnings_combined),
        }

    def _write_csv(self, rows: Sequence[Mapping[str, Any]], path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(self.CSV_COLUMNS))
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row.get(key, "") for key in self.CSV_COLUMNS})

    @staticmethod
    def _write_json(reports: Sequence[Mapping[str, Any]], path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(list(reports), handle, ensure_ascii=False, indent=2)

    @staticmethod
    def _default_error_report(
        original_input: Any,
        original_result: Any,
        message: str,
    ) -> Dict[str, Any]:
        """Build a placeholder report when evaluation fails on a single record."""
        sample_id = ""
        ticker = ""
        forecast_time = ""
        if isinstance(original_input, Mapping):
            sample_id = (
                str(original_input.get("sample_id", ""))
                if isinstance(original_input.get("sample_id", ""), str)
                else ""
            )
            ticker = (
                str(original_input.get("ticker", ""))
                if isinstance(original_input.get("ticker", ""), str)
                else ""
            )
            forecast_time = (
                str(original_input.get("forecast_time", ""))
                if isinstance(original_input.get("forecast_time", ""), str)
                else ""
            )
        if isinstance(original_result, Mapping):
            if not sample_id:
                sample_id = (
                    str(original_result.get("sample_id", ""))
                    if isinstance(original_result.get("sample_id", ""), str)
                    else ""
                )
            if not ticker:
                ticker = (
                    str(original_result.get("ticker", ""))
                    if isinstance(original_result.get("ticker", ""), str)
                    else ""
                )
            if not forecast_time:
                forecast_time = (
                    str(original_result.get("forecast_time", ""))
                    if isinstance(original_result.get("forecast_time", ""), str)
                    else ""
                )
        prediction = (
            original_result.get("prediction")
            if isinstance(original_result, Mapping)
            and isinstance(original_result.get("prediction"), str)
            else "HOLD"
        )
        return {
            "sample_id": sample_id,
            "ticker": ticker,
            "forecast_time": forecast_time,
            "prediction": prediction,
            "original_confidence": 0.0,
            "temporal_validity": 0.0,
            "evidence_support": 0.0,
            "confidence_drop": 0.0,
            "confidence_after_removal": 0.0,
            "prediction_after_removal": "HOLD",
            "faithfulness_score": 0.0,
            "verdict": "unsupported_evidence",
            "temporal_warnings": [],
            "support_warnings": [],
            "ablation_warnings": [
                f"{FaithfulnessEvaluator._EVALUATION_ERROR_MARKER}{message}"
            ],
            "per_evidence_results": [],
        }
