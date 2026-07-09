"""End-to-end faithful evidence-centric forecasting pipeline.

This module orchestrates the six existing stages of the project:

    News CSV  ─►  Temporal Retriever  ─►  Evidence Extractor
              ─►  Evidence Selector    ─►  Forecast Model
              ─►  Faithfulness Evaluator
              ─►  6 dashboard-ready output CSVs

``PipelineRunner`` is glue code only. It does NOT re-implement any
upstream algorithm — it composes the existing stage classes as black
boxes:

* :class:`src.retriever.TemporalRetriever`
* :class:`src.evidence_extractor.EvidenceExtractor`
* :class:`src.evidence_selector.EvidenceSelector`
* :class:`src.forecast_model.ForecastModel`
* :class:`src.faithfulness_evaluator.FaithfulnessEvaluator`
* :class:`src.sufficiency_evaluator.SufficiencyEvaluator`
* :class:`src.market_analyzer.MarketAnalyzer`

Usage from Python:

>>> from src.pipeline import PipelineRunner
>>> result = PipelineRunner().run("data/sample_dataset.csv", "outputs")

Usage from the CLI:

>>> python -m src.pipeline --input data/sample_dataset.csv --output-dir outputs

The pipeline is deterministic: identical inputs produce byte-equal
outputs. It does NOT use any LLM, FinBERT, transformer model, or
external API. It does NOT mutate any file under the input directory.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from src.evidence_extractor import EvidenceExtractor
from src.evidence_selector import EvidenceSelector
from src.faithfulness_evaluator import FaithfulnessEvaluator
from src.forecast_model import ForecastModel
from src.market_analyzer import MarketAnalyzer
from src.retriever import TemporalRetriever
from src.sufficiency_evaluator import SufficiencyEvaluator


class PipelineRunner:
    """Runs every stage for each ``(ticker, forecast_time)`` group and
    writes the six output CSVs.
    """

    PREDICTION_COLUMNS: Tuple[str, ...] = (
        "sample_id",
        "ticker",
        "forecast_time",
        "prediction",
        "confidence",
        "score",
        "label",
        "is_correct",
        "rationale",
        "cited_evidence_count",
        "valid_news_count",
        "invalid_future_news_count",
    )

    EVIDENCE_COLUMNS: Tuple[str, ...] = (
        "sample_id",
        "ticker",
        "forecast_time",
        "news_id",
        "news_time",
        "news_text",
        "evidence_text",
        "polarity",
        "expected_direction",
        "evidence_role",
        "support_score",
        "is_cited",
        "is_temporally_valid",
    )

    FAITHFULNESS_COLUMNS: Tuple[str, ...] = (
        "sample_id",
        "ticker",
        "forecast_time",
        "prediction",
        "original_confidence",
        "confidence_without_cited_evidence",
        "confidence_drop",
        "temporal_validity",
        "evidence_support",
        "faithfulness_label",
        "counterevidence_coverage",
        "counterevidence_detected",
    )

    SUFFICIENCY_COLUMNS: Tuple[str, ...] = (
        "sample_id",
        "ticker",
        "forecast_time",
        "prediction",
        "original_confidence",
        "sufficiency_confidence",
        "sufficiency_score",
        "prediction_on_only_cited",
        "counterfactual_confidence",
        "counterfactual_delta",
    )

    MARKET_COLUMNS: Tuple[str, ...] = (
        "sample_id",
        "ticker",
        "forecast_time",
        "prediction",
        "next_day_return",
        "price_5d_return",
        "market_consistent",
        "regime",
        "market_consistency_score",
    )

    LEAKAGE_COLUMNS: Tuple[str, ...] = (
        "sample_id",
        "ticker",
        "forecast_time",
        "news_id",
        "news_time",
        "news_text",
        "leakage_minutes",
        "leakage_type",
    )

    def __init__(self) -> None:
        self._retriever = TemporalRetriever()
        self._extractor = EvidenceExtractor()
        self._selector = EvidenceSelector()
        self._forecast_model = ForecastModel()
        self._faithfulness_evaluator = FaithfulnessEvaluator()
        self._sufficiency_evaluator = SufficiencyEvaluator()
        self._market_analyzer = MarketAnalyzer()

    # -----------------------------------------------------------------
    # Public entry point
    # -----------------------------------------------------------------

    def run(
        self,
        input_path: str,
        output_dir: str,
        *,
        ticker_column: str = "ticker",
        news_time_column: str = "news_time",
        forecast_time_column: str = "forecast_time",
        label_column: str = "label",
    ) -> Dict[str, Any]:
        """Run the full pipeline on ``input_path`` and write 6 CSVs to ``output_dir``.

        Args:
            input_path: Path to a CSV with at least
                ``news_id, ticker, forecast_time, news_time, news_text``.
            output_dir: Directory where the six CSVs will be written.
            ticker_column: Name of the ticker column in the CSV.
            news_time_column: Name of the news publication-time column.
            forecast_time_column: Name of the forecast-time column.
            label_column: Optional ground-truth label column; missing
                values are written as empty strings.

        Returns:
            A summary dict with keys ``groups``, ``prediction_count``,
            ``evidence_count``, ``leakage_count``, and the six file paths.

        Raises:
            FileNotFoundError: If ``input_path`` does not exist.
            KeyError: If any required column is missing from the CSV.
        """
        input_path_obj = Path(input_path)
        if not input_path_obj.exists():
            raise FileNotFoundError(f"input file not found: {input_path!r}")
        df = pd.read_csv(input_path_obj)

        required = [
            ticker_column,
            news_time_column,
            forecast_time_column,
            "news_id",
            "news_text",
        ]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise KeyError(f"input CSV is missing required columns: {missing}")

        # Group rows by (ticker, forecast_time) preserving input order.
        group_keys: List[Tuple[str, str]] = []
        seen: set = set()
        for _, row in df.iterrows():
            key = (str(row[ticker_column]), str(row[forecast_time_column]))
            if key not in seen:
                seen.add(key)
                group_keys.append(key)

        prediction_rows: List[Dict[str, Any]] = []
        evidence_rows: List[Dict[str, Any]] = []
        faithfulness_rows: List[Dict[str, Any]] = []
        sufficiency_rows: List[Dict[str, Any]] = []
        market_rows: List[Dict[str, Any]] = []
        leakage_rows: List[Dict[str, Any]] = []

        for ticker, forecast_time in group_keys:
            group_df = df[
                (df[ticker_column].astype(str) == ticker)
                & (df[forecast_time_column].astype(str) == forecast_time)
            ]
            group_dicts = group_df.to_dict(orient="records")
            result = self._run_group(group_dicts, label_column=label_column)
            prediction_rows.append(result["prediction_row"])
            evidence_rows.extend(result["evidence_rows"])
            faithfulness_rows.append(result["faithfulness_row"])
            sufficiency_rows.append(result["sufficiency_row"])
            market_rows.append(result["market_row"])
            leakage_rows.extend(result["leakage_rows"])

        output_dir_obj = Path(output_dir)
        output_dir_obj.mkdir(parents=True, exist_ok=True)

        pred_path = output_dir_obj / "prediction_results.csv"
        evid_path = output_dir_obj / "evidence_results.csv"
        faith_path = output_dir_obj / "faithfulness_results.csv"
        suff_path = output_dir_obj / "sufficiency_results.csv"
        market_path = output_dir_obj / "market_consistency_results.csv"
        leak_path = output_dir_obj / "temporal_leakage_results.csv"

        self._write_csv(prediction_rows, self.PREDICTION_COLUMNS, pred_path)
        self._write_csv(evidence_rows, self.EVIDENCE_COLUMNS, evid_path)
        self._write_csv(faithfulness_rows, self.FAITHFULNESS_COLUMNS, faith_path)
        self._write_csv(sufficiency_rows, self.SUFFICIENCY_COLUMNS, suff_path)
        self._write_csv(market_rows, self.MARKET_COLUMNS, market_path)
        self._write_csv(leakage_rows, self.LEAKAGE_COLUMNS, leak_path)

        return {
            "groups": len(group_keys),
            "prediction_count": len(prediction_rows),
            "evidence_count": len(evidence_rows),
            "leakage_count": len(leakage_rows),
            "prediction_results_csv": str(pred_path),
            "evidence_results_csv": str(evid_path),
            "faithfulness_results_csv": str(faith_path),
            "sufficiency_results_csv": str(suff_path),
            "market_consistency_results_csv": str(market_path),
            "temporal_leakage_results_csv": str(leak_path),
        }

    # -----------------------------------------------------------------
    # Per-group orchestration
    # -----------------------------------------------------------------

    def _run_group(
        self,
        group_rows: List[Dict[str, Any]],
        *,
        label_column: str,
    ) -> Dict[str, Any]:
        """Run every stage for one ``(ticker, forecast_time)`` group.

        Returns a dict with the six row dicts (one per output CSV) plus
        intermediate state useful for tests and debugging.
        """
        ticker = str(group_rows[0]["ticker"])
        forecast_time = str(group_rows[0]["forecast_time"])
        sample_id = f"{ticker}_{forecast_time}".replace(" ", "_").replace(":", "")

        # --- 1. Temporal Retriever ------------------------------------------
        raw_news = [
            {
                "news_id": str(r["news_id"]),
                "news_time": str(r["news_time"]),
                "news_text": str(r["news_text"]),
                "ticker": ticker,
            }
            for r in group_rows
        ]
        retrieval = self._retriever.retrieve(
            forecast_time=forecast_time, news=raw_news, ticker=ticker
        )

        valid_news = retrieval.valid_news
        invalid_future_news = retrieval.invalid_future_news
        valid_count = retrieval.valid_count
        invalid_future_count = retrieval.invalid_future_count

        # --- 2. Evidence Extractor (only on valid news) ---------------------
        extractor_inputs = [
            self._build_extractor_input(
                {
                    "news_id": n["news_id"],
                    "ticker": ticker,
                    "forecast_time": forecast_time,
                    "news_time": n["news_time"],
                    "news_text": self._news_text(n),
                }
            )
            for n in valid_news
        ]
        extractor_results = self._extractor.extract_batch(extractor_inputs)
        # Flatten one evidence list per group (each input -> list of items).
        evidence: List[Dict[str, Any]] = []
        evidence_text_by_news: Dict[str, str] = {}
        for n, result in zip(valid_news, extractor_results):
            evidence_text_by_news[n["news_id"]] = self._news_text(n)
            for ev in result["evidence"]:
                ev["news_time"] = n["news_time"]
                evidence.append(ev)

        # --- 3. Forecast Model -----------------------------------------------
        label = ""
        for r in group_rows:
            if label_column and label_column in r and r[label_column] not in (None, ""):
                label = str(r[label_column])
                break
        request = self._build_forecast_request(
            ticker=ticker,
            forecast_time=forecast_time,
            label=label,
            evidence=evidence,
            sample_id=sample_id,
        )
        forecast = self._forecast_model.predict(request)

        # --- 4. Evidence Selector (post-hoc classification for the writer) ---
        selector_request = {
            "ticker": ticker,
            "forecast_time": forecast_time,
            "prediction": forecast["prediction"],
            "confidence": forecast["confidence"],
            "evidence_candidates": [
                {
                    "news_id": ev["news_id"],
                    "ticker": ticker,
                    "news_time": ev["news_time"],
                    "evidence_text": ev.get("evidence_text", ""),
                    "polarity": ev.get("polarity"),
                    "expected_direction": ev.get("expected_direction"),
                    "extractor_score": float(ev.get("support_score", 0.0) or 0.0),
                }
                for ev in evidence
            ],
        }
        selector_result = self._selector.select_batch([selector_request])[0]
        cited_ids = {e["news_id"] for e in selector_result["pro_evidence"]} | {
            e["news_id"] for e in selector_result["counterevidence"]
        }

        # --- 4b. Counterevidence Coverage (B2) ----------------------------
        prediction = forecast["prediction"]
        expected_labels = {
            cand["news_id"]: self._selector.CLASSIFICATION_TABLE.get(
                (prediction, cand.get("expected_direction", "HOLD")), "neutral"
            )
            for cand in selector_request["evidence_candidates"]
        }
        coverage_result = self._selector.compute_coverage(selector_result, expected_labels)

        # --- 5. Faithfulness Evaluator --------------------------------------
        report = self._faithfulness_evaluator.evaluate(request, forecast)

        confidence_drop = float(report["confidence_drop"])
        temporal_validity = float(report["temporal_validity"])
        evidence_support = float(report["evidence_support"])
        confidence_after_removal = float(report["confidence_after_removal"])
        label_faith = self._faithfulness_label(confidence_drop, temporal_validity)

        # --- 6. Build the four output rows ----------------------------------
        is_correct = label != "" and label == forecast["prediction"]

        prediction_row = {
            "sample_id": sample_id,
            "ticker": ticker,
            "forecast_time": forecast_time,
            "prediction": forecast["prediction"],
            "confidence": float(forecast["confidence"]),
            "score": int(forecast["score"]),
            "label": label,
            "is_correct": bool(is_correct),
            "rationale": forecast["rationale"],
            "cited_evidence_count": len(cited_ids),
            "valid_news_count": valid_count,
            "invalid_future_news_count": invalid_future_count,
        }

        evidence_rows = self._build_evidence_rows(
            sample_id,
            ticker,
            forecast_time,
            evidence,
            selector_result,
            evidence_text_by_news,
            cited_ids,
        )

        faithfulness_row = {
            "sample_id": sample_id,
            "ticker": ticker,
            "forecast_time": forecast_time,
            "prediction": forecast["prediction"],
            "original_confidence": float(forecast["confidence"]),
            "confidence_without_cited_evidence": confidence_after_removal,
            "confidence_drop": confidence_drop,
            "temporal_validity": temporal_validity,
            "evidence_support": evidence_support,
            "faithfulness_label": label_faith,
            "counterevidence_coverage": float(coverage_result["counterevidence_coverage"]),
            "counterevidence_detected": bool(
                coverage_result["counterevidence_detected_rate"] == 1.0
            ),
        }

        # --- 6b. Sufficiency + Counterfactual (B1) --------------------------
        suff_result = self._sufficiency_evaluator.evaluate(request, forecast, cited_ids)
        sufficiency_row = {
            "sample_id": sample_id,
            "ticker": ticker,
            "forecast_time": forecast_time,
            "prediction": forecast["prediction"],
            "original_confidence": float(forecast["confidence"]),
            "sufficiency_confidence": float(suff_result["sufficiency_confidence"]),
            "sufficiency_score": float(suff_result["sufficiency_score"]),
            "prediction_on_only_cited": suff_result["prediction_on_only_cited"],
            "counterfactual_confidence": float(suff_result["counterfactual_confidence"]),
            "counterfactual_delta": float(suff_result["counterfactual_delta"]),
        }

        # --- 6c. Market Consistency + Regime (B3) ---------------------------
        first_row = group_rows[0]
        next_day_return = self._safe_float(first_row.get("next_day_return", 0.0))
        price_5d_return = self._safe_float(first_row.get("price_5d_return", 0.0))
        market_result = self._market_analyzer.analyze(
            forecast["prediction"], next_day_return, price_5d_return
        )
        market_row = {
            "sample_id": sample_id,
            "ticker": ticker,
            "forecast_time": forecast_time,
            "prediction": forecast["prediction"],
            "next_day_return": market_result["next_day_return"],
            "price_5d_return": market_result["price_5d_return"],
            "market_consistent": bool(market_result["market_consistent"]),
            "regime": market_result["regime"],
            "market_consistency_score": float(market_result["market_consistency_score"]),
        }

        leakage_rows = [
            {
                "sample_id": sample_id,
                "ticker": ticker,
                "forecast_time": forecast_time,
                "news_id": n["news_id"],
                "news_time": n["news_time"],
                "news_text": self._news_text(n),
                "leakage_minutes": self._compute_leakage_minutes(
                    str(n["news_time"]), forecast_time
                ),
                "leakage_type": "future_news",
            }
            for n in invalid_future_news
        ]

        return {
            "prediction_row": prediction_row,
            "evidence_rows": evidence_rows,
            "faithfulness_row": faithfulness_row,
            "sufficiency_row": sufficiency_row,
            "market_row": market_row,
            "leakage_rows": leakage_rows,
            "forecast": forecast,
            "report": report,
        }

    @staticmethod
    def _build_evidence_rows(
        sample_id: str,
        ticker: str,
        forecast_time: str,
        evidence: List[Dict[str, Any]],
        selector_result: Dict[str, Any],
        evidence_text_by_news: Dict[str, str],
        cited_ids: set,
    ) -> List[Dict[str, Any]]:
        """Merge Evidence Extractor output with Evidence Selector roles."""
        selector_index: Dict[str, str] = {}
        for e in selector_result["pro_evidence"]:
            selector_index[e["news_id"]] = "pro"
        for e in selector_result["counterevidence"]:
            selector_index[e["news_id"]] = "counter"
        for e in selector_result["neutral_evidence"]:
            selector_index.setdefault(e["news_id"], "neutral")

        rows: List[Dict[str, Any]] = []
        for ev in evidence:
            news_id = ev["news_id"]
            rows.append(
                {
                    "sample_id": sample_id,
                    "ticker": ticker,
                    "forecast_time": forecast_time,
                    "news_id": news_id,
                    "news_time": ev["news_time"],
                    "news_text": evidence_text_by_news.get(news_id, ""),
                    "evidence_text": ev.get("evidence_text", ""),
                    "polarity": ev.get("polarity", "neutral"),
                    "expected_direction": ev.get("expected_direction", "HOLD"),
                    "evidence_role": selector_index.get(news_id, "neutral"),
                    "support_score": float(ev.get("support_score", 0.0) or 0.0),
                    "is_cited": news_id in cited_ids,
                    "is_temporally_valid": True,
                }
            )
        return rows

    # -----------------------------------------------------------------
    # Small pure helpers
    # -----------------------------------------------------------------

    @staticmethod
    def _news_text(item: Dict[str, Any]) -> str:
        """Return the body text of a news dict under either ``news_text`` or ``text``."""
        return item.get("news_text", item.get("text", ""))

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        """Parse ``value`` as a float, falling back to ``default`` on any
        falsy or unparseable input (mirrors the CSV's optional B3 columns).
        """
        try:
            return float(value or default)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _build_extractor_input(row: Dict[str, Any]) -> Dict[str, Any]:
        """Adapt a CSV row into the shape the Evidence Extractor expects."""
        return {
            "news_id": str(row["news_id"]),
            "ticker": str(row["ticker"]),
            "forecast_time": str(row["forecast_time"]),
            "news_time": str(row["news_time"]),
            "news_text": str(row["news_text"]),
        }

    @staticmethod
    def _build_forecast_request(
        ticker: str,
        forecast_time: str,
        label: str,
        evidence: List[Dict[str, Any]],
        sample_id: str,
    ) -> Dict[str, Any]:
        """Adapt extracted evidence into the shape ``ForecastModel.predict`` expects."""
        return {
            "sample_id": sample_id,
            "ticker": ticker,
            "forecast_time": forecast_time,
            "label": label,
            "evidence": evidence,
        }

    @staticmethod
    def _faithfulness_label(confidence_drop: float, temporal_validity: float) -> str:
        """Map (confidence_drop, temporal_validity) -> HIGH / MEDIUM / LOW.

        HIGH   if confidence_drop >= 0.20 and temporal_validity == 1.0
        MEDIUM if confidence_drop >= 0.05 and temporal_validity == 1.0
        LOW    otherwise
        """
        if temporal_validity >= 1.0 and confidence_drop >= 0.20:
            return "HIGH"
        if temporal_validity >= 1.0 and confidence_drop >= 0.05:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _compute_leakage_minutes(news_time: str, forecast_time: str) -> int:
        """Return the number of minutes by which ``news_time`` exceeds
        ``forecast_time``. Both inputs are interpreted as UTC. Returns 0
        on parse failure (defensive).
        """
        try:
            nt = datetime.fromisoformat(news_time.replace(" ", "T"))
            ft = datetime.fromisoformat(forecast_time.replace(" ", "T"))
            if nt.tzinfo is None:
                nt = nt.replace(tzinfo=timezone.utc)
            if ft.tzinfo is None:
                ft = ft.replace(tzinfo=timezone.utc)
            delta = (nt - ft).total_seconds() / 60.0
            return max(0, int(delta))
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def _write_csv(rows: List[Dict[str, Any]], columns: Tuple[str, ...], path: Path) -> None:
        """Write ``rows`` to ``path`` enforcing the given ``columns`` order.

        Empty ``rows`` yields a header-only CSV with the column names —
        this keeps the file present and schema-correct so the dashboard
        treats it as a valid (empty) artifact.
        """
        df = pd.DataFrame(rows, columns=columns)
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="src.pipeline",
        description=(
            "Run the faithful evidence-centric forecasting pipeline on a "
            "news CSV and write six dashboard-ready output CSVs."
        ),
    )
    parser.add_argument(
        "--input",
        default="data/sample_dataset.csv",
        help="Path to the input CSV (default: data/sample_dataset.csv).",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs",
        help="Directory for the six output CSVs (default: outputs).",
    )
    parser.add_argument(
        "--ticker-column",
        default="ticker",
        help="Name of the ticker column in the input CSV.",
    )
    parser.add_argument(
        "--news-time-column",
        default="news_time",
        help="Name of the news publication-time column.",
    )
    parser.add_argument(
        "--forecast-time-column",
        default="forecast_time",
        help="Name of the forecast-time column.",
    )
    parser.add_argument(
        "--label-column",
        default="label",
        help="Name of the ground-truth label column (may be absent).",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    summary = PipelineRunner().run(
        args.input,
        args.output_dir,
        ticker_column=args.ticker_column,
        news_time_column=args.news_time_column,
        forecast_time_column=args.forecast_time_column,
        label_column=args.label_column,
    )
    print(
        f"pipeline ok: groups={summary['groups']} "
        f"predictions={summary['prediction_count']} "
        f"evidence={summary['evidence_count']} "
        f"leakage={summary['leakage_count']}"
    )
    for key in (
        "prediction_results_csv",
        "evidence_results_csv",
        "faithfulness_results_csv",
        "sufficiency_results_csv",
        "market_consistency_results_csv",
        "temporal_leakage_results_csv",
    ):
        print(f"  {key}: {summary[key]}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
