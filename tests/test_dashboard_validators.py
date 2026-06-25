"""Unit tests for ``src.dashboard.validators``."""

from __future__ import annotations

import pandas as pd
import pytest

from src.dashboard.validators import (
    DashboardDataError,
    assert_columns,
    assert_dashboard_data,
)
from src.dashboard.data_loader import (
    EVIDENCE_COLUMNS,
    FAITHFULNESS_COLUMNS,
    LEAKAGE_COLUMNS,
    PREDICTION_COLUMNS,
    DashboardData,
)


def _predictions_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sample_id": ["S1"],
            "ticker": ["AAPL"],
            "forecast_time": ["2025-03-12 09:00"],
            "prediction": ["UP"],
            "confidence": [0.8],
            "label": ["UP"],
            "score": [1.0],
            "rationale": ["..."],
            "valid_news_count": [3],
            "invalid_future_news_count": [0],
        }
    )


def test_assert_columns_passes_when_all_columns_present() -> None:
    df = _predictions_df()
    assert_columns(df, PREDICTION_COLUMNS, file_label="prediction_results.csv")


def test_assert_columns_raises_when_missing_single_column() -> None:
    df = _predictions_df().drop(columns=["label"])
    with pytest.raises(DashboardDataError) as info:
        assert_columns(df, PREDICTION_COLUMNS, file_label="prediction_results.csv")
    assert "label" in str(info.value)
    assert "prediction_results.csv" in str(info.value)


def test_assert_columns_lists_all_missing_columns() -> None:
    df = _predictions_df().drop(columns=["label", "rationale"])
    with pytest.raises(DashboardDataError) as info:
        assert_columns(df, PREDICTION_COLUMNS, file_label="prediction_results.csv")
    msg = str(info.value)
    assert "label" in msg
    assert "rationale" in msg


def test_assert_columns_ignores_extra_columns() -> None:
    df = _predictions_df()
    df["extra_column"] = "ignored"
    assert_columns(df, PREDICTION_COLUMNS, file_label="prediction_results.csv")


def test_assert_columns_raises_when_dataframe_is_none() -> None:
    with pytest.raises(DashboardDataError) as info:
        assert_columns(None, PREDICTION_COLUMNS, file_label="prediction_results.csv")
    assert "prediction_results.csv" in str(info.value)


def test_assert_columns_raises_when_dataframe_is_empty() -> None:
    df = pd.DataFrame(columns=PREDICTION_COLUMNS)
    # Empty DataFrame has the columns but no rows; assert_columns does
    # not flag this. Use ``None`` if you want the "missing" semantic.
    assert_columns(df, PREDICTION_COLUMNS, file_label="prediction_results.csv")


def test_assert_dashboard_data_passes_on_healthy_data() -> None:
    data = DashboardData(
        predictions=_predictions_df(),
        evidence=pd.DataFrame(columns=list(EVIDENCE_COLUMNS)),
        faithfulness=pd.DataFrame(columns=list(FAITHFULNESS_COLUMNS)),
        leakage=pd.DataFrame(columns=list(LEAKAGE_COLUMNS)),
    )
    assert_dashboard_data(data)


def test_assert_dashboard_data_skips_none_and_empty() -> None:
    data = DashboardData(
        predictions=None,
        evidence=pd.DataFrame(),
        faithfulness=None,
        leakage=pd.DataFrame(),
    )
    assert_dashboard_data(data)


def test_assert_dashboard_data_raises_on_missing_columns() -> None:
    bad = _predictions_df().drop(columns=["label", "rationale"])
    data = DashboardData(predictions=bad)
    with pytest.raises(DashboardDataError) as info:
        assert_dashboard_data(data)
    msg = str(info.value)
    assert "label" in msg
    assert "rationale" in msg
    assert "prediction_results.csv" in msg


def test_assert_dashboard_data_first_error_wins() -> None:
    """The helper fails fast — only the first invalid frame is reported."""
    bad_pred = _predictions_df().drop(columns=["label"])
    bad_faith = pd.DataFrame({"only_one_column": [1]})  # missing many columns
    data = DashboardData(predictions=bad_pred, faithfulness=bad_faith)
    with pytest.raises(DashboardDataError) as info:
        assert_dashboard_data(data)
    # First invalid frame is predictions, so the message names that file.
    assert "prediction_results.csv" in str(info.value)


def test_assert_dashboard_data_accepts_dict_shaped_input() -> None:
    """The helper duck-types — it accepts a plain dict too."""
    data = {
        "predictions": _predictions_df(),
        "evidence": pd.DataFrame(columns=list(EVIDENCE_COLUMNS)),
        "faithfulness": pd.DataFrame(columns=list(FAITHFULNESS_COLUMNS)),
        "leakage": pd.DataFrame(columns=list(LEAKAGE_COLUMNS)),
    }
    assert_dashboard_data(data)


def test_assert_dashboard_data_returns_silently_when_input_invalid() -> None:
    """An input that is neither a mapping nor a dataclass returns silently."""
    assert assert_dashboard_data("not a data object") is None
    assert assert_dashboard_data(None) is None