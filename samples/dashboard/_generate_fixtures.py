"""Generate sample dashboard fixtures.

Run from the repository root::

    python3 samples/dashboard/_generate_fixtures.py

Writes three fixture sets under ``samples/dashboard/``:

- ``healthy/`` — five predictions with a mix of UP / DOWN / HOLD, no
  temporal leakage, faithfulness levels covering all three buckets.
- ``leakage/`` — same five predictions but with one cited evidence item
  that violates ``news_time <= forecast_time`` and produces a
  ``TEMPORAL_LEAKAGE_BLOCKED`` warning.
- ``faithfulness_levels/`` — five predictions with one row per
  faithfulness level at the documented boundary confidence drops
  (0.20, 0.10, 0.01).

The generator re-uses the upstream pipeline (``predict_batch`` +
``evaluate_batch``) to produce realistic CSVs, then writes the
proposal-shaped dashboard CSVs by hand. The output is byte-stable
across runs (same inputs, deterministic upstream, same writing order).
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence

import pandas as pd

# Ensure the repo root is on the import path.
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.evidence_selector import select_evidence  # noqa: E402
from src.forecast_model import predict_batch  # noqa: E402
from src.faithfulness_evaluator import evaluate_batch  # noqa: E402


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _evidence_item(
    news_id: str,
    news_time: str,
    evidence_text: str,
    polarity: str,
    direction: str,
) -> Dict[str, Any]:
    return {
        "evidence_id": f"{news_id}_E001",
        "news_id": news_id,
        "news_time": news_time,
        "evidence_text": evidence_text,
        "polarity": polarity,
        "expected_direction": direction,
        "support_score": 1.0,
    }


def _build_record(
    sample_id: str,
    ticker: str,
    forecast_time: str,
    evidence: List[Dict[str, Any]],
    label: str = "",
) -> Dict[str, Any]:
    return {
        "sample_id": sample_id,
        "ticker": ticker,
        "forecast_time": forecast_time,
        "label": label,
        "evidence": evidence,
    }


HEALTHY_RECORDS: List[Dict[str, Any]] = [
    _build_record(
        "DSH-01",
        "AAPL",
        "2025-03-12 09:00",
        [
            _evidence_item("N100", "2025-03-11 08:00", "strong sales", "positive", "UP"),
            _evidence_item("N101", "2025-03-11 09:00", "raised guidance", "positive", "UP"),
            _evidence_item("N102", "2025-03-11 10:00", "analyst upgrade", "positive", "UP"),
        ],
        label="UP",
    ),
    _build_record(
        "DSH-02",
        "AAPL",
        "2025-03-13 09:00",
        [
            _evidence_item("N110", "2025-03-12 08:00", "profit warning", "negative", "DOWN"),
            _evidence_item("N111", "2025-03-12 09:00", "guidance cut", "negative", "DOWN"),
        ],
        label="DOWN",
    ),
    _build_record(
        "DSH-03",
        "GOOGL",
        "2025-03-14 09:00",
        [
            _evidence_item("N120", "2025-03-13 08:00", "mixed results", "neutral", "HOLD"),
            _evidence_item("N121", "2025-03-13 09:00", "in line with estimates", "neutral", "HOLD"),
        ],
        label="HOLD",
    ),
    _build_record(
        "DSH-04",
        "GOOGL",
        "2025-03-15 09:00",
        [
            _evidence_item("N130", "2025-03-14 08:00", "earnings beat", "positive", "UP"),
            _evidence_item("N131", "2025-03-14 09:00", "raised guidance", "positive", "UP"),
        ],
        label="UP",
    ),
    _build_record(
        "DSH-05",
        "META",
        "2025-03-16 09:00",
        [
            _evidence_item("N140", "2025-03-15 08:00", "regulator probe", "negative", "DOWN"),
        ],
        label="DOWN",
    ),
]

# Add a future-news evidence item to the last record to create the
# leakage fixture. We rebuild a copy with the violation, then keep the
# healthy variant untouched.
LEAKAGE_RECORDS: List[Dict[str, Any]] = [
    _build_record(
        "DSH-01",
        "AAPL",
        "2025-03-12 09:00",
        [
            _evidence_item("N100", "2025-03-11 08:00", "strong sales", "positive", "UP"),
            _evidence_item("N101", "2025-03-11 09:00", "raised guidance", "positive", "UP"),
            _evidence_item("N102", "2025-03-11 10:00", "analyst upgrade", "positive", "UP"),
        ],
        label="UP",
    ),
    _build_record(
        "DSH-02",
        "AAPL",
        "2025-03-13 09:00",
        [
            _evidence_item("N110", "2025-03-12 08:00", "profit warning", "negative", "DOWN"),
            _evidence_item("N111", "2025-03-12 09:00", "guidance cut", "negative", "DOWN"),
        ],
        label="DOWN",
    ),
    _build_record(
        "DSH-03",
        "GOOGL",
        "2025-03-14 09:00",
        [
            # The first item has news_time strictly after forecast_time;
            # the model will emit a TEMPORAL_LEAKAGE_BLOCKED warning.
            _evidence_item("N120", "2025-03-14 18:00", "future rumor", "neutral", "HOLD"),
            _evidence_item("N121", "2025-03-13 09:00", "in line with estimates", "neutral", "HOLD"),
        ],
        label="HOLD",
    ),
    _build_record(
        "DSH-04",
        "GOOGL",
        "2025-03-15 09:00",
        [
            _evidence_item("N130", "2025-03-14 08:00", "earnings beat", "positive", "UP"),
            _evidence_item("N131", "2025-03-14 09:00", "raised guidance", "positive", "UP"),
        ],
        label="UP",
    ),
    _build_record(
        "DSH-05",
        "META",
        "2025-03-16 09:00",
        [
            _evidence_item("N140", "2025-03-15 08:00", "regulator probe", "negative", "DOWN"),
        ],
        label="DOWN",
    ),
]

FAITHFULNESS_RECORDS: List[Dict[str, Any]] = [
    # Record that should land in ``high``: 3 UP evidence → UP prediction.
    _build_record(
        "DSH-HIGH",
        "AAPL",
        "2025-03-12 09:00",
        [
            _evidence_item("N100", "2025-03-11 08:00", "strong sales", "positive", "UP"),
            _evidence_item("N101", "2025-03-11 09:00", "raised guidance", "positive", "UP"),
            _evidence_item("N102", "2025-03-11 10:00", "analyst upgrade", "positive", "UP"),
        ],
        label="UP",
    ),
    # Record that should land in ``low``: single HOLD evidence → HOLD
    # prediction; ablation has nothing to remove so drop ≈ 0.
    _build_record(
        "DSH-LOW",
        "META",
        "2025-03-13 09:00",
        [
            _evidence_item("N110", "2025-03-12 08:00", "no clear signal", "neutral", "HOLD"),
        ],
        label="HOLD",
    ),
    # Record that should land in ``medium``: a single UP evidence item.
    # The live pipeline produces UP/0.6 → ablation removes the cited UP
    # → confidence drops to 0.0 (no evidence left) → drop = 0.6 which
    # is ``high``. We override the drop to land in the medium bucket.
    _build_record(
        "DSH-MED",
        "GOOGL",
        "2025-03-14 09:00",
        [
            _evidence_item("N120", "2025-03-13 08:00", "earnings beat", "positive", "UP"),
            _evidence_item("N121", "2025-03-13 09:00", "guidance raise", "positive", "UP"),
        ],
        label="UP",
    ),
]


def _select(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Add the ``selected_evidence`` alias so the model has the chosen list."""
    selected: List[Dict[str, Any]] = []
    for record in records:
        record_with_selected = dict(record)
        # The Forecast Model's pipeline normally runs the Evidence
        # Selector first. For the fixture generator we want realistic
        # per-record inputs without coupling the sample to a specific
        # selector strategy. We expose the raw evidence as both
        # ``evidence`` and ``selected_evidence`` so the model receives
        # an identical view. The selector is still part of the live
        # pipeline; the fixture exercises the loader + adapter layer
        # only.
        record_with_selected["selected_evidence"] = list(record.get("evidence", []))
        selected.append(record_with_selected)
    return selected


def _write_predictions_csv(results: Sequence[Dict[str, Any]], path: Path) -> None:
    """Write the proposal-shape ``prediction_results.csv`` from a batch result."""
    columns = [
        "sample_id",
        "ticker",
        "forecast_time",
        "prediction",
        "confidence",
        "score",
        "rationale",
        "label",
        "valid_news_count",
        "invalid_future_news_count",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "sample_id": result.get("sample_id", ""),
                    "ticker": result.get("ticker", ""),
                    "forecast_time": result.get("forecast_time", ""),
                    "prediction": result.get("prediction", "HOLD"),
                    "confidence": result.get("confidence", 0.5),
                    "score": result.get("score", 0),
                    "rationale": result.get("rationale", ""),
                    "label": result.get("label", ""),
                    "valid_news_count": 0,
                    "invalid_future_news_count": 0,
                }
            )


def _write_evidence_csv(results: Sequence[Dict[str, Any]], path: Path) -> None:
    """Expand every evidence list into one row per snippet."""
    columns = [
        "sample_id",
        "news_id",
        "ticker",
        "forecast_time",
        "news_time",
        "news_text",
        "evidence_text",
        "polarity",
        "expected_direction",
        "evidence_role",
        "support_score",
        "is_cited",
        "is_temporally_valid",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for result in results:
            for role in (
                "pro_evidence",
                "counter_evidence",
                "up_evidence",
                "down_evidence",
                "neutral_evidence",
            ):
                items = result.get(role) or []
                for item in items:
                    writer.writerow(
                        {
                            "sample_id": result.get("sample_id", ""),
                            "news_id": item.get("news_id", ""),
                            "ticker": result.get("ticker", ""),
                            "forecast_time": result.get("forecast_time", ""),
                            "news_time": item.get("news_time", ""),
                            "news_text": item.get("evidence_text", ""),
                            "evidence_text": item.get("evidence_text", ""),
                            "polarity": item.get("polarity", ""),
                            "expected_direction": item.get("expected_direction", ""),
                            "evidence_role": role,
                            "support_score": item.get("support_score", 0.0),
                            "is_cited": role in ("pro_evidence", "counter_evidence"),
                            "is_temporally_valid": True,
                        }
                    )


def _write_faithfulness_csv(
    reports: Sequence[Dict[str, Any]],
    path: Path,
    *,
    overrides: Dict[str, Dict[str, Any]] = None,
) -> None:
    """Write the proposal-shape ``faithfulness_results.csv`` from a batch report.

    ``overrides`` lets a generator hand-author specific rows when the
    live pipeline would not produce the desired value. Used for the
    ``faithfulness_levels`` fixture so the medium level is represented
    even when no live record would naturally land there.
    """
    columns = [
        "sample_id",
        "ticker",
        "forecast_time",
        "prediction",
        "original_confidence",
        "confidence_without_cited_evidence",
        "confidence_drop",
        "evidence_support",
        "temporal_validity",
        "faithfulness_label",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    overrides = overrides or {}
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for report in reports:
            sample_id = report.get("sample_id", "")
            drop = report.get("confidence_drop", 0.0)
            if drop >= 0.20:
                label = "high"
            elif drop >= 0.05:
                label = "medium"
            else:
                label = "low"
            row = {
                "sample_id": sample_id,
                "ticker": report.get("ticker", ""),
                "forecast_time": report.get("forecast_time", ""),
                "prediction": report.get("prediction", ""),
                "original_confidence": report.get("original_confidence", 0.0),
                "confidence_without_cited_evidence": report.get(
                    "confidence_after_removal", 0.0
                ),
                "confidence_drop": drop,
                "evidence_support": report.get("evidence_support", 0.0),
                "temporal_validity": report.get("temporal_validity", 0.0),
                "faithfulness_label": label,
            }
            if sample_id in overrides:
                row.update(overrides[sample_id])
                # Re-derive the label from the override drop.
                drop = float(row["confidence_drop"])
                if drop >= 0.20:
                    label = "high"
                elif drop >= 0.05:
                    label = "medium"
                else:
                    label = "low"
                row["faithfulness_label"] = label
            writer.writerow(row)


def _write_leakage_csv(results: Sequence[Dict[str, Any]], path: Path) -> None:
    """Expand ``TEMPORAL_LEAKAGE_BLOCKED`` warnings into the proposal shape."""
    columns = [
        "sample_id",
        "news_id",
        "ticker",
        "forecast_time",
        "news_time",
        "leakage_minutes",
        "news_text",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    rows: List[Dict[str, Any]] = []
    for result in results:
        for warning in result.get("warnings", []) or []:
            if warning.get("code") != "TEMPORAL_LEAKAGE_BLOCKED":
                continue
            news_time = _safe_str(warning.get("news_time", ""))
            forecast_warning_time = _safe_str(
                warning.get("forecast_time", result.get("forecast_time", ""))
            )
            minutes = _compute_leakage_minutes_for_fixture(news_time, forecast_warning_time)
            rows.append(
                {
                    "sample_id": result.get("sample_id", ""),
                    "news_id": warning.get("evidence_id", ""),
                    "ticker": result.get("ticker", ""),
                    "forecast_time": result.get("forecast_time", ""),
                    "news_time": news_time,
                    "leakage_minutes": minutes,
                    "news_text": _safe_str(warning.get("message", "")),
                }
            )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _compute_leakage_minutes_for_fixture(news_time: str, forecast_time: str) -> float:
    """Mirror of :func:`src.dashboard.data_loader._compute_leakage_minutes`."""
    if not news_time or not forecast_time:
        return 0.0
    try:
        news_dt = pd.to_datetime(news_time, errors="raise", utc=True)
        forecast_dt = pd.to_datetime(forecast_time, errors="raise", utc=True)
    except (ValueError, TypeError):
        return 0.0
    if pd.isna(news_dt) or pd.isna(forecast_dt):
        return 0.0
    news_naive = news_dt.tz_convert(None) if news_dt.tzinfo else news_dt
    forecast_naive = forecast_dt.tz_convert(None) if forecast_dt.tzinfo else forecast_dt
    delta = (news_naive - forecast_naive).total_seconds() / 60.0
    return abs(float(delta))


def _write_jsonl(results: Sequence[Dict[str, Any]], path: Path) -> None:
    """Write the JSON sibling for the adapter tests."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(list(results), handle, ensure_ascii=False, indent=2)


def _emit(
    label: str,
    records: List[Dict[str, Any]],
    target: Path,
    *,
    faithfulness_overrides: Dict[str, Dict[str, Any]] = None,
) -> None:
    selected = _select(records)
    target.mkdir(parents=True, exist_ok=True)

    # Run predict_batch with no CSV/JSON output, just the in-memory results.
    results = predict_batch(selected, output_csv_path=None, output_json_path=None)
    # Re-run evaluate_batch with no CSV/JSON output.
    pairs = [
        (selected[i], results[i])
        for i in range(len(results))
    ]
    reports = evaluate_batch(pairs, output_csv_path=None, output_json_path=None)

    _write_predictions_csv(results, target / "prediction_results.csv")
    _write_evidence_csv(results, target / "evidence_results.csv")
    _write_faithfulness_csv(
        reports,
        target / "faithfulness_results.csv",
        overrides=faithfulness_overrides,
    )
    _write_leakage_csv(results, target / "temporal_leakage_results.csv")
    _write_jsonl(results, target / "prediction_results.json")
    print(f"  [{label}] wrote {target}/")


def main() -> None:
    base = Path(__file__).resolve().parent
    _emit("healthy", HEALTHY_RECORDS, base / "healthy")
    _emit("leakage", LEAKAGE_RECORDS, base / "leakage")
    # The ``faithfulness_levels`` fixture hand-overrides one row so
    # the medium bucket is represented — the live pipeline produces
    # only high and low for these inputs.
    _emit(
        "faithfulness_levels",
        FAITHFULNESS_RECORDS,
        base / "faithfulness_levels",
        faithfulness_overrides={
            "DSH-MED": {
                "confidence_drop": 0.10,
                "original_confidence": 0.65,
                "confidence_without_cited_evidence": 0.55,
            }
        },
    )
    print("Done.")


if __name__ == "__main__":
    main()
