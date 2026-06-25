"""Dashboard validators.

Pure helpers that assert the schema of loaded DataFrames and aggregate
errors across the four dashboard data files. This module is **IO-free**:
it does not read files, does not call Streamlit, does not call any
external service. It only inspects in-memory DataFrames.

The :class:`DashboardDataError` is a ``ValueError`` subclass so callers
can catch it generically or by class.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

import pandas as pd


class DashboardDataError(ValueError):
    """Raised when a dashboard DataFrame is missing required columns."""


def assert_columns(
    df: pd.DataFrame,
    required_columns: Sequence[str],
    *,
    file_label: str,
) -> None:
    """Raise :class:`DashboardDataError` when ``df`` is missing columns.

    Args:
        df: The DataFrame to inspect. ``None`` and an empty DataFrame
            are both treated as "missing all columns" and will raise.
        required_columns: Column names that MUST be present.
        file_label: Human-readable label for the source file, included
            in the error message (e.g., ``"prediction_results.csv"``).

    Raises:
        DashboardDataError: When one or more required columns are
            missing. The message lists all missing column names.
    """
    if df is None:
        missing = [str(col) for col in required_columns]
        raise DashboardDataError(
            f"{file_label} is missing required columns: {missing}"
        )
    present = set(df.columns)
    missing = [str(col) for col in required_columns if col not in present]
    if missing:
        raise DashboardDataError(
            f"{file_label} is missing required columns: {missing}"
        )


def _coerce_data(data: Any) -> Optional[Mapping[str, pd.DataFrame]]:
    """Best-effort coercion of ``data`` into a mapping of named frames.

    Accepts a :class:`DashboardData` instance (duck-typed — see
    :mod:`src.dashboard.data_loader`) or a plain mapping. Returns
    ``None`` when the object cannot be coerced.
    """
    if data is None:
        return None
    if isinstance(data, Mapping):
        return data
    mapping = getattr(data, "__dict__", None)
    if isinstance(mapping, Mapping):
        return mapping
    return None


def assert_dashboard_data(data: Any) -> None:
    """Validate every non-empty DataFrame inside a :class:`DashboardData`.

    Iterates over the four well-known fields
    (``predictions``, ``evidence``, ``faithfulness``, ``leakage``) and
    runs :func:`assert_columns` on the non-empty ones. A DataFrame that
    is ``None`` (file missing) is allowed and skipped — the Streamlit
    app renders a friendly banner for those. Empty DataFrames (zero
    rows) are also allowed and skipped; the column contract only
    matters when there is data to render.

    Raises:
        DashboardDataError: The first validation error encountered.
            The caller can choose to catch and render each error
            individually; this helper preserves the simple
            "fail fast" contract.
    """
    mapping = _coerce_data(data)
    if mapping is None:
        return
    # The four well-known fields, with their required column lists.
    field_to_columns: List[tuple] = []
    # Import here to avoid a circular import at module load time.
    from src.dashboard.data_loader import (  # noqa: WPS433 — local import
        EVIDENCE_COLUMNS,
        FAITHFULNESS_COLUMNS,
        LEAKAGE_COLUMNS,
        PREDICTION_COLUMNS,
    )

    field_to_columns = [
        ("predictions", PREDICTION_COLUMNS, "prediction_results.csv"),
        ("evidence", EVIDENCE_COLUMNS, "evidence_results.csv"),
        ("faithfulness", FAITHFULNESS_COLUMNS, "faithfulness_results.csv"),
        ("leakage", LEAKAGE_COLUMNS, "temporal_leakage_results.csv"),
    ]
    for field, columns, label in field_to_columns:
        df = mapping.get(field)
        if df is None:
            continue
        if not isinstance(df, pd.DataFrame):
            continue
        if df.empty:
            continue
        assert_columns(df, columns, file_label=label)


__all__ = [
    "DashboardDataError",
    "assert_columns",
    "assert_dashboard_data",
]
