"""Dashboard data loader and proposal-vs-source adapter.

This module owns the dashboard's column contract. It reads the four
proposal-defined upstream CSV outputs and resolves them into the
proposal-shape DataFrames the dashboard consumes.

A **contract-bridging adapter** is necessary because the proposal-
specified column names do not exactly match what the current source
code emits. The bridge lives entirely inside this module so the rest
of the dashboard can consume a single, stable shape:

- ``valid_news_count`` / ``invalid_future_news_count`` are derived from
  the synthesized evidence DataFrame grouped by ``sample_id``.
- ``evidence_results.csv`` is synthesized from ``prediction_results.json``'s
  ``pro_evidence`` / ``counter_evidence`` / ``up_evidence`` / ``down_evidence``
  / ``neutral_evidence`` lists.
- ``temporal_leakage_results.csv`` is synthesized from the
  ``TEMPORAL_LEAKAGE_BLOCKED`` warnings in ``prediction_results.json``.
- ``confidence_without_cited_evidence`` is the renamed
  ``confidence_after_removal``; ``faithfulness_label`` is the
  high/medium/low classification derived from ``confidence_drop``.

This module is **read-only with respect to disk**: it never writes to
``outputs/``. It does NOT call the upstream pipeline (Forecast Model,
Faithfulness Evaluator); it only reads the artifacts they produced.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from src.dashboard.validators import DashboardDataError


# ---------------------------------------------------------------------------
# Column contracts
# ---------------------------------------------------------------------------


#: Required columns for ``prediction_results.csv`` (post-enrichment).
PREDICTION_COLUMNS: Tuple[str, ...] = (
    "sample_id",
    "ticker",
    "forecast_time",
    "prediction",
    "confidence",
    "label",
    "score",
    "rationale",
    "valid_news_count",
    "invalid_future_news_count",
)

#: Required columns for ``evidence_results.csv`` (synthesized).
EVIDENCE_COLUMNS: Tuple[str, ...] = (
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
)

#: Required columns for ``faithfulness_results.csv`` (post-normalization).
FAITHFULNESS_COLUMNS: Tuple[str, ...] = (
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
    "counterevidence_coverage",
    "counterevidence_detected",
)

#: Required columns for ``market_consistency_results.csv``.
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

#: Required columns for ``sufficiency_results.csv``.
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

#: Required columns for ``temporal_leakage_results.csv`` (synthesized).
LEAKAGE_COLUMNS: Tuple[str, ...] = (
    "sample_id",
    "news_id",
    "ticker",
    "forecast_time",
    "news_time",
    "leakage_minutes",
    "news_text",
)


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass
class DashboardData:
    """The dashboard's view of the four upstream CSVs.

    Each field is either a populated DataFrame, an empty DataFrame
    (file present but empty), or ``None`` (file missing). The
    ``missing_files`` and ``empty_files`` lists carry the same
    information as plain strings for easy rendering.
    """

    predictions: Optional[pd.DataFrame] = None
    evidence: Optional[pd.DataFrame] = None
    faithfulness: Optional[pd.DataFrame] = None
    leakage: Optional[pd.DataFrame] = None
    sufficiency: Optional[pd.DataFrame] = None
    market: Optional[pd.DataFrame] = None
    agent_trace: List[Dict[str, Any]] = field(default_factory=list)
    missing_files: List[str] = field(default_factory=list)
    empty_files: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Low-level readers
# ---------------------------------------------------------------------------


def _read_csv_or_none(
    path: Path,
    *,
    file_label: str,
) -> Tuple[Optional[pd.DataFrame], bool]:
    """Read ``path`` and return ``(df, is_empty)``.

    - File absent → returns ``(None, False)``.
    - File present but zero rows → returns ``(empty_df, True)``.
    - File present and non-empty → returns ``(df, False)``.

    The function does NOT validate columns; that is the caller's
    responsibility (so this helper stays dumb and reusable).
    """
    if not path.exists():
        return (None, False)
    try:
        df = pd.read_csv(path)
    except (OSError, pd.errors.ParserError, UnicodeDecodeError):
        # Treat unreadable files as missing — the app will render a
        # user-friendly banner rather than crashing.
        return (None, False)
    if df.empty:
        # Preserve the column schema as empty so downstream code can
        # safely check for column presence.
        return (df, True)
    return (df, False)


def _read_json_or_none(path: Path) -> Optional[List[Dict[str, Any]]]:
    """Read a JSON file containing a list of records, or return ``None``."""
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, list):
        return None
    return payload


# ---------------------------------------------------------------------------
# Synthesizers
# ---------------------------------------------------------------------------


_EVIDENCE_ROLE_LISTS: Tuple[str, ...] = (
    "pro_evidence",
    "counter_evidence",
    "up_evidence",
    "down_evidence",
    "neutral_evidence",
)


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _synthesize_evidence_rows(
    prediction_records: Optional[Sequence[Dict[str, Any]]],
) -> pd.DataFrame:
    """Build the evidence DataFrame from ``prediction_results.json``."""
    columns = list(EVIDENCE_COLUMNS)
    if not prediction_records:
        return pd.DataFrame(columns=columns)
    rows: List[Dict[str, Any]] = []
    for record in prediction_records:
        if not isinstance(record, dict):
            continue
        sample_id = _safe_str(record.get("sample_id"))
        ticker = _safe_str(record.get("ticker"))
        forecast_time = _safe_str(record.get("forecast_time"))
        for role in _EVIDENCE_ROLE_LISTS:
            items = record.get(role)
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                is_cited = role in ("pro_evidence", "counter_evidence")
                rows.append(
                    {
                        "sample_id": sample_id,
                        "news_id": _safe_str(item.get("news_id", "")),
                        "ticker": ticker,
                        "forecast_time": forecast_time,
                        "news_time": _safe_str(item.get("news_time", "")),
                        "news_text": _safe_str(item.get("news_text", "")),
                        "evidence_text": _safe_str(item.get("evidence_text", "")),
                        "polarity": _safe_str(item.get("polarity", "")),
                        "expected_direction": _safe_str(
                            item.get("expected_direction", "")
                        ),
                        "evidence_role": role,
                        "support_score": _coerce_float(item.get("support_score", 0.0)),
                        "is_cited": bool(is_cited),
                        "is_temporally_valid": True,
                    }
                )
    return pd.DataFrame(rows, columns=columns)


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if result != result:  # NaN check
        return default
    return result


def _coerce_minutes(value: Any) -> float:
    minutes = _coerce_float(value, default=0.0)
    return abs(minutes)


def _synthesize_leakage_rows(
    prediction_records: Optional[Sequence[Dict[str, Any]]],
) -> pd.DataFrame:
    """Build the leakage DataFrame from ``prediction_results.json`` warnings."""
    columns = list(LEAKAGE_COLUMNS)
    if not prediction_records:
        return pd.DataFrame(columns=columns)
    rows: List[Dict[str, Any]] = []
    for record in prediction_records:
        if not isinstance(record, dict):
            continue
        sample_id = _safe_str(record.get("sample_id"))
        ticker = _safe_str(record.get("ticker"))
        forecast_time = _safe_str(record.get("forecast_time"))
        warnings = record.get("warnings")
        if not isinstance(warnings, list):
            continue
        for warning in warnings:
            if not isinstance(warning, dict):
                continue
            if warning.get("code") != "TEMPORAL_LEAKAGE_BLOCKED":
                continue
            news_time = _safe_str(warning.get("news_time", ""))
            forecast_warning_time = _safe_str(warning.get("forecast_time", forecast_time))
            minutes = _compute_leakage_minutes(news_time, forecast_warning_time)
            rows.append(
                {
                    "sample_id": sample_id,
                    "news_id": _safe_str(warning.get("evidence_id", "")),
                    "ticker": ticker,
                    "forecast_time": forecast_time,
                    "news_time": news_time,
                    "leakage_minutes": minutes,
                    "news_text": _safe_str(warning.get("message", "")),
                }
            )
    return pd.DataFrame(rows, columns=columns)


def _compute_leakage_minutes(news_time: str, forecast_time: str) -> float:
    """Return the positive minutes between ``news_time`` and ``forecast_time``.

    Returns ``0.0`` when either timestamp cannot be parsed. The sign is
    forced to positive (the warning already filters to
    ``news_time > forecast_time``). Both timestamps are normalized to
    tz-naive UTC before subtraction so a tz-aware forecast and a
    tz-naive news_time do not raise.
    """
    if not news_time or not forecast_time:
        return 0.0
    try:
        news_dt = pd.to_datetime(news_time, errors="raise", utc=True)
        forecast_dt = pd.to_datetime(forecast_time, errors="raise", utc=True)
    except (ValueError, TypeError):
        return 0.0
    if pd.isna(news_dt) or pd.isna(forecast_dt):
        return 0.0
    # Strip timezone to allow subtraction; both are now UTC.
    news_naive = news_dt.tz_convert(None) if news_dt.tzinfo else news_dt
    forecast_naive = forecast_dt.tz_convert(None) if forecast_dt.tzinfo else forecast_dt
    delta = (news_naive - forecast_naive).total_seconds() / 60.0
    return abs(float(delta))


# ---------------------------------------------------------------------------
# Enrich / normalize
# ---------------------------------------------------------------------------


def _enrich_predictions(
    predictions_df: pd.DataFrame,
    evidence_df: Optional[pd.DataFrame],
) -> pd.DataFrame:
    """Add ``valid_news_count`` and ``invalid_future_news_count`` to ``predictions_df``.

    The counts are derived from ``evidence_df`` grouped by ``sample_id``;
    rows missing from ``evidence_df`` (or ``sample_id`` missing) get a
    count of ``0``.
    """
    out = predictions_df.copy()
    if evidence_df is None or evidence_df.empty:
        out["valid_news_count"] = 0
        out["invalid_future_news_count"] = 0
        return out
    if "sample_id" not in evidence_df.columns:
        out["valid_news_count"] = 0
        out["invalid_future_news_count"] = 0
        return out

    grouped = evidence_df.groupby("sample_id", dropna=False)
    if "is_temporally_valid" in evidence_df.columns:
        valid_series = grouped["is_temporally_valid"].apply(
            lambda s: int((s.astype(bool) == True).sum())  # noqa: E712
        )
        invalid_series = grouped["is_temporally_valid"].apply(
            lambda s: int((s.astype(bool) == False).sum())  # noqa: E712
        )
    else:
        valid_series = grouped.size().apply(lambda _: 0)
        invalid_series = grouped.size().apply(lambda _: 0)
    sample_index = out["sample_id"].astype(str) if "sample_id" in out.columns else None
    if sample_index is None:
        out["valid_news_count"] = 0
        out["invalid_future_news_count"] = 0
        return out
    counts_valid = sample_index.map(valid_series).fillna(0).astype(int)
    counts_invalid = sample_index.map(invalid_series).fillna(0).astype(int)
    out["valid_news_count"] = counts_valid
    out["invalid_future_news_count"] = counts_invalid
    return out


def _normalize_faithfulness(faithfulness_df: pd.DataFrame) -> pd.DataFrame:
    """Rename / derive the proposal-shaped faithfulness columns."""
    out = faithfulness_df.copy()
    if "confidence_after_removal" in out.columns and "confidence_without_cited_evidence" not in out.columns:
        out = out.rename(
            columns={"confidence_after_removal": "confidence_without_cited_evidence"}
        )
    if "verdict" in out.columns and "faithfulness_label" not in out.columns:
        from src.dashboard.metrics import classify_faithfulness_level

        out["verdict_legacy"] = out["verdict"]
        out["faithfulness_label"] = (
            pd.to_numeric(out.get("confidence_drop", 0.0), errors="coerce")
            .fillna(0.0)
            .apply(classify_faithfulness_level)
        )
    elif "confidence_drop" in out.columns and "faithfulness_label" not in out.columns:
        from src.dashboard.metrics import classify_faithfulness_level

        out["faithfulness_label"] = (
            pd.to_numeric(out["confidence_drop"], errors="coerce")
            .fillna(0.0)
            .apply(classify_faithfulness_level)
        )
    if "counterevidence_coverage" not in out.columns:
        out["counterevidence_coverage"] = 0.0
    if "counterevidence_detected" not in out.columns:
        out["counterevidence_detected"] = False
    return out


# ---------------------------------------------------------------------------
# Agent trace loader
# ---------------------------------------------------------------------------


def load_agent_trace(output_dir: str = "outputs") -> List[Dict[str, Any]]:
    """Load the agent trace log from ``output_dir/run_log.json``.

    Returns an empty list when the file is missing or unreadable — never raises.
    """
    path = Path(output_dir) / "run_log.json"
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    return [e for e in payload if isinstance(e, dict)]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def load_dashboard_data(
    output_dir: str = "outputs",
) -> DashboardData:
    """Load and adapt the four upstream CSV outputs into ``DashboardData``.

    Args:
        output_dir: Directory containing the four upstream CSVs and the
            ``prediction_results.json`` sibling. Defaults to ``"outputs"``.

    Returns:
        A :class:`DashboardData` instance with all four DataFrames
        populated (or marked ``None`` / empty when missing), plus
        ``missing_files`` and ``empty_files`` lists for the Streamlit
        banner layer to consume.
    """
    base = Path(output_dir)
    data = DashboardData()

    # --- predictions ---
    pred_csv = base / "prediction_results.csv"
    pred_df, pred_empty = _read_csv_or_none(pred_csv, file_label="prediction_results.csv")
    pred_json_records = _read_json_or_none(base / "prediction_results.json")

    # Synthesize evidence and leakage from the JSON sibling regardless
    # of whether the proposal-shaped CSVs are present.
    evidence_df = _synthesize_evidence_rows(pred_json_records)
    leakage_df = _synthesize_leakage_rows(pred_json_records)

    # The proposal asks for an ``evidence_results.csv``; use it when
    # present, otherwise fall back to the synthesized frame.
    direct_evidence_df, direct_evidence_empty = _read_csv_or_none(
        base / "evidence_results.csv", file_label="evidence_results.csv"
    )
    if direct_evidence_df is not None:
        evidence_df = direct_evidence_df
        if direct_evidence_empty:
            data.empty_files.append("evidence_results.csv")
    elif evidence_df.empty:
        data.missing_files.append("evidence_results.csv")

    # Enrich the predictions DataFrame with the synthesized counts.
    if pred_df is not None:
        if pred_empty:
            data.empty_files.append("prediction_results.csv")
            pred_df = pred_df.copy()
            for col in PREDICTION_COLUMNS:
                if col not in pred_df.columns:
                    pred_df[col] = [] if col not in {"confidence", "score"} else 0.0
        else:
            pred_df = _enrich_predictions(pred_df, evidence_df)
            # Ensure all proposal columns exist (add missing as empty).
            for col in PREDICTION_COLUMNS:
                if col not in pred_df.columns:
                    pred_df[col] = "" if col not in {"confidence", "score", "valid_news_count", "invalid_future_news_count"} else 0
        data.predictions = pred_df
    else:
        data.missing_files.append("prediction_results.csv")

    # --- evidence ---
    if direct_evidence_df is None:
        data.evidence = evidence_df
    else:
        data.evidence = evidence_df

    # --- leakage ---
    direct_leakage_df, direct_leakage_empty = _read_csv_or_none(
        base / "temporal_leakage_results.csv", file_label="temporal_leakage_results.csv"
    )
    if direct_leakage_df is not None:
        if direct_leakage_empty:
            data.empty_files.append("temporal_leakage_results.csv")
        data.leakage = direct_leakage_df
    elif not leakage_df.empty:
        data.leakage = leakage_df
    else:
        data.missing_files.append("temporal_leakage_results.csv")
        data.leakage = leakage_df

    # --- faithfulness ---
    faith_df, faith_empty = _read_csv_or_none(
        base / "faithfulness_results.csv", file_label="faithfulness_results.csv"
    )
    if faith_df is not None:
        if faith_empty:
            data.empty_files.append("faithfulness_results.csv")
        else:
            faith_df = _normalize_faithfulness(faith_df)
            for col in FAITHFULNESS_COLUMNS:
                if col not in faith_df.columns:
                    faith_df[col] = "" if col not in {"original_confidence", "confidence_without_cited_evidence", "confidence_drop", "evidence_support", "temporal_validity"} else 0.0
        data.faithfulness = faith_df
    else:
        data.missing_files.append("faithfulness_results.csv")

    # --- sufficiency ---
    suff_df, suff_empty = _read_csv_or_none(
        base / "sufficiency_results.csv", file_label="sufficiency_results.csv"
    )
    if suff_df is not None:
        if suff_empty:
            data.empty_files.append("sufficiency_results.csv")
        data.sufficiency = suff_df
    # Missing sufficiency file is non-fatal — data.sufficiency stays None.

    # --- market consistency ---
    market_df, market_empty = _read_csv_or_none(
        base / "market_consistency_results.csv",
        file_label="market_consistency_results.csv",
    )
    if market_df is not None:
        if market_empty:
            data.empty_files.append("market_consistency_results.csv")
        data.market = market_df
    # Missing market file is non-fatal — data.market stays None.

    # --- agent trace ---
    data.agent_trace = load_agent_trace(output_dir)

    return data


__all__ = [
    "DashboardData",
    "PREDICTION_COLUMNS",
    "EVIDENCE_COLUMNS",
    "FAITHFULNESS_COLUMNS",
    "SUFFICIENCY_COLUMNS",
    "MARKET_COLUMNS",
    "LEAKAGE_COLUMNS",
    "load_dashboard_data",
    "load_agent_trace",
]