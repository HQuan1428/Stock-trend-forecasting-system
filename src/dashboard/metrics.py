"""Dashboard metric helpers.

Pure functions that compute summary statistics from the four dashboard
DataFrames. This module is **IO-free**: it does not read files, does
not call Streamlit, does not call any external service. It only
inspects in-memory DataFrames. The single exception is the
:func:`apply_filters` helper, which accepts pre-built DataFrames and a
filter-state dict and returns a filtered DataFrame.

The thresholds are exposed as module-level constants so they can be
referenced from the chart builders, the case-detail template, and the
unit tests without duplication.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

import pandas as pd


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


#: Valid prediction labels — same set the Forecast Model uses.
VALID_PREDICTIONS: Tuple[str, ...] = ("UP", "DOWN", "HOLD")

#: Faithfulness levels (one per row of ``faithfulness_results``).
FAITHFULNESS_LEVELS: Tuple[str, ...] = ("high", "medium", "low")

#: Temporal leakage severities (derived from the leakage row count).
LEAKAGE_SEVERITIES: Tuple[str, ...] = ("ok", "warning", "critical")

#: ``confidence_drop`` at-or-above this value is classified as ``high``.
FAITHFULNESS_HIGH_THRESHOLD: float = 0.20

#: ``confidence_drop`` at-or-above this value (and below the high
#: threshold) is classified as ``medium``.
FAITHFULNESS_MEDIUM_THRESHOLD: float = 0.05

#: Leakage counts at-or-above this value produce a ``warning`` banner.
LEAKAGE_WARNING_THRESHOLD: int = 1

#: Leakage counts above this value produce a ``critical`` banner.
LEAKAGE_CRITICAL_THRESHOLD: int = 3


# ---------------------------------------------------------------------------
# Distribution and accuracy
# ---------------------------------------------------------------------------


def prediction_distribution(df: pd.DataFrame) -> Dict[str, int]:
    """Return counts of ``UP``, ``DOWN``, ``HOLD`` in ``df["prediction"]``.

    Missing classes are reported as ``0``. Values outside the three
    valid predictions are silently ignored (they are not counted in
    either the per-class buckets or the implied total).
    """
    out: Dict[str, int] = {"UP": 0, "DOWN": 0, "HOLD": 0}
    if df is None or df.empty or "prediction" not in df.columns:
        return out
    series = df["prediction"].astype(str)
    for label in VALID_PREDICTIONS:
        out[label] = int((series == label).sum())
    return out


def accuracy(df: pd.DataFrame) -> Optional[float]:
    """Return ``(prediction == label)`` mean, or ``None`` if labels are absent.

    Both columns are cast to string before comparison so boolean /
    numeric labels do not raise. Empty DataFrames return ``None`` (no
    accuracy is defined on an empty batch).
    """
    if df is None or df.empty:
        return None
    if "prediction" not in df.columns or "label" not in df.columns:
        return None
    if df["label"].isna().all():
        return None
    pred = df["prediction"].astype(str)
    label = df["label"].astype(str)
    return float((pred == label).mean())


def average_confidence(df: pd.DataFrame) -> float:
    """Return the mean of ``df["confidence"]``, or ``0.0`` on empty input."""
    if df is None or df.empty or "confidence" not in df.columns:
        return 0.0
    return float(pd.to_numeric(df["confidence"], errors="coerce").fillna(0.0).mean())


def average_confidence_drop(df: pd.DataFrame) -> float:
    """Return the mean of ``df["confidence_drop"]``, or ``0.0`` on empty input."""
    if df is None or df.empty or "confidence_drop" not in df.columns:
        return 0.0
    return float(pd.to_numeric(df["confidence_drop"], errors="coerce").fillna(0.0).mean())


# ---------------------------------------------------------------------------
# Temporal validity
# ---------------------------------------------------------------------------


def temporal_leakage_count(
    leakage_df: Optional[pd.DataFrame] = None,
    evidence_df: Optional[pd.DataFrame] = None,
) -> int:
    """Return the number of temporal-leakage rows.

    The dashboard has two ways to compute this number:

    1. From the synthesized ``temporal_leakage_results`` DataFrame —
       pass ``leakage_df``. Each row in that DataFrame is a leakage
       row, so the count is ``len(leakage_df)``.
    2. From the evidence DataFrame — pass ``evidence_df``. The count
       is the number of rows where ``is_temporally_valid == False``.

    When both are provided, ``leakage_df`` takes precedence. When
    neither is provided, the count is ``0``.
    """
    if leakage_df is not None and not leakage_df.empty:
        return int(len(leakage_df))
    if evidence_df is not None and not evidence_df.empty:
        if "is_temporally_valid" not in evidence_df.columns:
            return 0
        # Cast to bool defensively so a string column does not raise.
        flag = evidence_df["is_temporally_valid"]
        try:
            return int((flag.astype(bool) == False).sum())  # noqa: E712
        except (ValueError, TypeError):
            return 0
    return 0


def average_temporal_validity(df: pd.DataFrame) -> float:
    """Return the mean of ``df["temporal_validity"]``, or ``1.0`` on empty input.

    An empty DataFrame (no evidence) implies no leakage, hence a
    validity of ``1.0``.
    """
    if df is None or df.empty or "temporal_validity" not in df.columns:
        return 1.0
    return float(pd.to_numeric(df["temporal_validity"], errors="coerce").fillna(1.0).mean())


# ---------------------------------------------------------------------------
# Faithfulness classification
# ---------------------------------------------------------------------------


def classify_faithfulness_level(confidence_drop: Any) -> str:
    """Map a single ``confidence_drop`` value to ``high`` / ``medium`` / ``low``.

    - ``drop >= 0.20``              → ``high``
    - ``0.05 <= drop < 0.20``       → ``medium``
    - otherwise                     → ``low`` (covers negative drops and NaN)
    """
    if confidence_drop is None:
        return "low"
    try:
        drop = float(confidence_drop)
    except (TypeError, ValueError):
        return "low"
    if math.isnan(drop):
        return "low"
    if drop >= FAITHFULNESS_HIGH_THRESHOLD:
        return "high"
    if drop >= FAITHFULNESS_MEDIUM_THRESHOLD:
        return "medium"
    return "low"


def leakage_severity(count: Any) -> str:
    """Map a leakage row count to ``ok`` / ``warning`` / ``critical``.

    - ``0``            → ``ok``
    - ``1..3``         → ``warning``
    - ``> 3``          → ``critical``
    - negative counts  → treated as ``0`` (returns ``ok``)
    """
    try:
        n = int(count)
    except (TypeError, ValueError):
        return "ok"
    if n <= 0:
        return "ok"
    if n <= LEAKAGE_CRITICAL_THRESHOLD:
        return "warning"
    return "critical"


def accuracy_by_ticker(df: pd.DataFrame) -> pd.DataFrame:
    """Return a DataFrame indexed by ticker with columns ``count`` and ``accuracy``.

    ``accuracy`` is ``None`` for tickers whose rows have no labels. The
    result is sorted by ``count`` descending so the busier tickers
    surface first in the chart.
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=["count", "accuracy"]).astype(
            {"count": "int64", "accuracy": "float64"}
        )
    if "ticker" not in df.columns:
        return pd.DataFrame(columns=["count", "accuracy"]).astype(
            {"count": "int64", "accuracy": "float64"}
        )
    grouped = df.groupby("ticker", dropna=False)
    counts = grouped.size().rename("count")
    if "label" in df.columns and "prediction" in df.columns:
        def _acc(sub: pd.DataFrame) -> Any:
            if sub["label"].isna().all():
                return None
            return float(
                (sub["prediction"].astype(str) == sub["label"].astype(str)).mean()
            )
        accs = grouped.apply(_acc, include_groups=False).rename("accuracy")
    else:
        accs = pd.Series(
            [None] * len(counts), index=counts.index, name="accuracy", dtype="float64"
        )
    out = pd.concat([counts, accs], axis=1).sort_values(
        "count", ascending=False
    )
    return out


# ---------------------------------------------------------------------------
# Filter application
# ---------------------------------------------------------------------------


def _normalize_date_range(
    value: Any,
) -> Tuple[Optional[pd.Timestamp], Optional[pd.Timestamp]]:
    """Coerce a date-range filter value to a ``(start, end)`` tuple."""
    if value is None:
        return (None, None)
    if isinstance(value, (list, tuple)) and len(value) == 2:
        start_raw, end_raw = value
    else:
        start_raw = end_raw = None
    start = pd.to_datetime(start_raw, errors="coerce") if start_raw else None
    end = pd.to_datetime(end_raw, errors="coerce") if end_raw else None
    if isinstance(start, pd.Timestamp) and pd.isna(start):
        start = None
    if isinstance(end, pd.Timestamp) and pd.isna(end):
        end = None
    return (start, end)


def apply_filters(
    df: pd.DataFrame,
    filters: Mapping[str, Any],
    *,
    frame_kind: str = "generic",
) -> pd.DataFrame:
    """Apply the six sidebar filters to any of the four dashboard DataFrames.

    Args:
        df: The DataFrame to filter. ``None`` is treated as an empty
            DataFrame and returned unchanged.
        filters: A mapping with any of the keys ``tickers``,
            ``predictions``, ``faithfulness_levels``, ``date_range``,
            ``cited_only``, ``leakage_only``. Missing keys are treated
            as "no constraint".
        frame_kind: One of ``"predictions"``, ``"evidence"``,
            ``"faithfulness"``, ``"leakage"``, or ``"generic"``. The
            filter helper picks which columns to inspect based on this
            hint so the same helper works on all four shapes.

    The function is **pure** and **side-effect-free**; it does not
    mutate ``df``. Calling with all-empty filters returns a shallow
    copy of ``df`` (or an empty DataFrame when ``df`` is ``None``).
    """
    if df is None:
        return df if isinstance(df, pd.DataFrame) else pd.DataFrame()
    if df.empty:
        return df.copy()
    out = df

    tickers = filters.get("tickers") if isinstance(filters, Mapping) else None
    if tickers:
        if "ticker" in out.columns:
            out = out[out["ticker"].astype(str).isin([str(t) for t in tickers])]

    predictions = filters.get("predictions") if isinstance(filters, Mapping) else None
    if predictions:
        if "prediction" in out.columns:
            out = out[out["prediction"].astype(str).isin([str(p) for p in predictions])]

    faithfulness_levels = (
        filters.get("faithfulness_levels") if isinstance(filters, Mapping) else None
    )
    if faithfulness_levels:
        target_levels = [str(level) for level in faithfulness_levels]
        if "faithfulness_label" in out.columns:
            out = out[out["faithfulness_label"].astype(str).isin(target_levels)]
        elif "confidence_drop" in out.columns:
            # Fallback: derive the level on the fly from
            # ``confidence_drop`` so the filter still works whether the
            # frame is the normalized (proposal-shape) or the raw
            # upstream shape.
            drops = pd.to_numeric(out["confidence_drop"], errors="coerce")
            derived = drops.apply(classify_faithfulness_level)
            out = out[derived.isin(target_levels)]

    date_range = (
        filters.get("date_range") if isinstance(filters, Mapping) else None
    )
    start, end = _normalize_date_range(date_range)
    if start is not None or end is not None:
        if "forecast_time" in out.columns:
            times = pd.to_datetime(out["forecast_time"], errors="coerce")
            if start is not None:
                out = out[times >= start]
                times = times.loc[out.index]
            if end is not None:
                out = out[times <= end + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)]

    cited_only = filters.get("cited_only") if isinstance(filters, Mapping) else None
    if cited_only:
        if "is_cited" in out.columns:
            flag = out["is_cited"]
            try:
                out = out[flag.astype(bool) == True]  # noqa: E712
            except (ValueError, TypeError):
                pass

    leakage_only = (
        filters.get("leakage_only") if isinstance(filters, Mapping) else None
    )
    if leakage_only:
        if "is_temporally_valid" in out.columns:
            flag = out["is_temporally_valid"]
            try:
                out = out[flag.astype(bool) == False]  # noqa: E712
            except (ValueError, TypeError):
                pass

    return out.copy()


__all__ = [
    # constants
    "VALID_PREDICTIONS",
    "FAITHFULNESS_LEVELS",
    "LEAKAGE_SEVERITIES",
    "FAITHFULNESS_HIGH_THRESHOLD",
    "FAITHFULNESS_MEDIUM_THRESHOLD",
    "LEAKAGE_WARNING_THRESHOLD",
    "LEAKAGE_CRITICAL_THRESHOLD",
    # functions
    "prediction_distribution",
    "accuracy",
    "average_confidence",
    "average_confidence_drop",
    "temporal_leakage_count",
    "average_temporal_validity",
    "classify_faithfulness_level",
    "leakage_severity",
    "accuracy_by_ticker",
    "apply_filters",
]