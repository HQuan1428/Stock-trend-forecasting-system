"""Unit tests for ``src.dashboard.metrics``."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from src.dashboard.metrics import (
    FAITHFULNESS_HIGH_THRESHOLD,
    FAITHFULNESS_LEVELS,
    FAITHFULNESS_MEDIUM_THRESHOLD,
    LEAKAGE_CRITICAL_THRESHOLD,
    LEAKAGE_SEVERITIES,
    LEAKAGE_WARNING_THRESHOLD,
    VALID_PREDICTIONS,
    accuracy,
    accuracy_by_ticker,
    apply_filters,
    average_confidence,
    average_confidence_drop,
    average_temporal_validity,
    classify_faithfulness_level,
    leakage_severity,
    prediction_distribution,
    temporal_leakage_count,
)


# ---------------------------------------------------------------------------
# prediction_distribution
# ---------------------------------------------------------------------------


def test_prediction_distribution_counts_each_class() -> None:
    df = pd.DataFrame({"prediction": ["UP", "DOWN", "UP", "HOLD", "UP", "DOWN"]})
    assert prediction_distribution(df) == {"UP": 3, "DOWN": 2, "HOLD": 1}


def test_prediction_distribution_reports_missing_classes_as_zero() -> None:
    df = pd.DataFrame({"prediction": ["UP", "UP"]})
    assert prediction_distribution(df) == {"UP": 2, "DOWN": 0, "HOLD": 0}


def test_prediction_distribution_ignores_invalid_values() -> None:
    df = pd.DataFrame({"prediction": ["UP", "?", None, "DOWN"]})
    assert prediction_distribution(df) == {"UP": 1, "DOWN": 1, "HOLD": 0}


def test_prediction_distribution_handles_empty_input() -> None:
    assert prediction_distribution(pd.DataFrame()) == {"UP": 0, "DOWN": 0, "HOLD": 0}
    assert prediction_distribution(pd.DataFrame({"prediction": []})) == {
        "UP": 0,
        "DOWN": 0,
        "HOLD": 0,
    }


def test_prediction_distribution_handles_missing_column() -> None:
    assert prediction_distribution(pd.DataFrame({"other": [1, 2]})) == {
        "UP": 0,
        "DOWN": 0,
        "HOLD": 0,
    }


# ---------------------------------------------------------------------------
# accuracy
# ---------------------------------------------------------------------------


def test_accuracy_returns_mean_when_label_present() -> None:
    df = pd.DataFrame(
        {"prediction": ["UP", "DOWN", "UP", "DOWN"], "label": ["UP", "DOWN", "DOWN", "UP"]}
    )
    assert accuracy(df) == 0.5


def test_accuracy_returns_none_when_label_missing() -> None:
    df = pd.DataFrame({"prediction": ["UP", "DOWN"]})
    assert accuracy(df) is None


def test_accuracy_returns_none_when_label_all_nan() -> None:
    df = pd.DataFrame({"prediction": ["UP", "DOWN"], "label": [None, None]})
    assert accuracy(df) is None


def test_accuracy_handles_empty_input() -> None:
    assert accuracy(pd.DataFrame()) is None


def test_accuracy_casts_to_string_for_comparison() -> None:
    df = pd.DataFrame({"prediction": ["UP", "DOWN"], "label": [1, 2]})
    assert accuracy(df) == 0.0
    df = pd.DataFrame({"prediction": ["UP", "DOWN"], "label": [True, False]})
    assert accuracy(df) == 0.0


# ---------------------------------------------------------------------------
# averages
# ---------------------------------------------------------------------------


def test_average_confidence_returns_mean() -> None:
    df = pd.DataFrame({"confidence": [0.5, 0.7, 0.9]})
    assert average_confidence(df) == pytest.approx(0.7)


def test_average_confidence_zero_on_empty() -> None:
    assert average_confidence(pd.DataFrame()) == 0.0
    assert average_confidence(pd.DataFrame({"confidence": []})) == 0.0


def test_average_confidence_handles_non_numeric() -> None:
    df = pd.DataFrame({"confidence": [0.5, "bad", 0.9]})
    # Non-numeric is coerced to NaN and replaced with 0.0
    assert average_confidence(df) == pytest.approx((0.5 + 0.0 + 0.9) / 3)


def test_average_confidence_drop_returns_mean() -> None:
    df = pd.DataFrame({"confidence_drop": [0.1, 0.2, 0.3]})
    assert average_confidence_drop(df) == pytest.approx(0.2)


def test_average_confidence_drop_zero_on_empty() -> None:
    assert average_confidence_drop(pd.DataFrame()) == 0.0


# ---------------------------------------------------------------------------
# temporal validity / leakage
# ---------------------------------------------------------------------------


def test_temporal_leakage_count_from_leakage_dataframe() -> None:
    df = pd.DataFrame({"sample_id": ["S1", "S2", "S3"]})
    assert temporal_leakage_count(leakage_df=df) == 3


def test_temporal_leakage_count_from_evidence_dataframe() -> None:
    df = pd.DataFrame(
        {"is_temporally_valid": [True, False, True, False, True]}
    )
    assert temporal_leakage_count(evidence_df=df) == 2


def test_temporal_leakage_count_prefers_leakage_dataframe() -> None:
    leak = pd.DataFrame({"sample_id": ["S1"]})
    ev = pd.DataFrame({"is_temporally_valid": [True, False, False]})
    assert temporal_leakage_count(leakage_df=leak, evidence_df=ev) == 1


def test_temporal_leakage_count_zero_when_neither_provided() -> None:
    assert temporal_leakage_count() == 0


def test_temporal_leakage_count_zero_when_columns_missing() -> None:
    df = pd.DataFrame({"other": [1, 2, 3]})
    assert temporal_leakage_count(evidence_df=df) == 0


def test_average_temporal_validity_returns_mean() -> None:
    df = pd.DataFrame({"temporal_validity": [1.0, 0.5, 0.0]})
    assert average_temporal_validity(df) == pytest.approx(0.5)


def test_average_temporal_validity_one_on_empty() -> None:
    assert average_temporal_validity(pd.DataFrame()) == 1.0
    assert average_temporal_validity(pd.DataFrame({"temporal_validity": []})) == 1.0


# ---------------------------------------------------------------------------
# classify_faithfulness_level — boundary cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "drop, expected",
    [
        (FAITHFULNESS_HIGH_THRESHOLD, "high"),       # 0.20 → high (boundary)
        (0.20, "high"),
        (0.21, "high"),
        (0.199, "medium"),
        (FAITHFULNESS_MEDIUM_THRESHOLD, "medium"),    # 0.05 → medium (boundary)
        (0.10, "medium"),
        (0.05, "medium"),
        (0.049, "low"),
        (0.0, "low"),
        (-0.1, "low"),
        (float("nan"), "low"),
    ],
)
def test_classify_faithfulness_level_boundaries(drop: float, expected: str) -> None:
    assert classify_faithfulness_level(drop) == expected


def test_classify_faithfulness_level_handles_none_and_non_numeric() -> None:
    assert classify_faithfulness_level(None) == "low"
    assert classify_faithfulness_level("not-a-number") == "low"


def test_classify_faithfulness_level_levels_constant() -> None:
    assert set(FAITHFULNESS_LEVELS) == {"high", "medium", "low"}


# ---------------------------------------------------------------------------
# leakage_severity — boundary cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "count, expected",
    [
        (0, "ok"),
        (-1, "ok"),                  # negative treated as 0
        (LEAKAGE_WARNING_THRESHOLD, "warning"),    # 1 → warning (boundary)
        (1, "warning"),
        (LEAKAGE_CRITICAL_THRESHOLD, "warning"),   # 3 → warning (boundary)
        (3, "warning"),
        (4, "critical"),
        (100, "critical"),
    ],
)
def test_leakage_severity_boundaries(count: int, expected: str) -> None:
    assert leakage_severity(count) == expected


def test_leakage_severity_handles_invalid_input() -> None:
    assert leakage_severity(None) == "ok"
    assert leakage_severity("not-a-number") == "ok"


def test_leakage_severities_constant() -> None:
    assert set(LEAKAGE_SEVERITIES) == {"ok", "warning", "critical"}


# ---------------------------------------------------------------------------
# accuracy_by_ticker
# ---------------------------------------------------------------------------


def test_accuracy_by_ticker_returns_count_and_accuracy() -> None:
    df = pd.DataFrame(
        {
            "ticker": ["AAPL", "AAPL", "GOOGL", "GOOGL"],
            "prediction": ["UP", "DOWN", "UP", "UP"],
            "label": ["UP", "DOWN", "DOWN", "UP"],
        }
    )
    result = accuracy_by_ticker(df)
    assert "count" in result.columns
    assert "accuracy" in result.columns
    # Sorted by count desc, so GOOGL (2) before AAPL (2) — order between
    # equal counts is implementation-defined. Both must have count=2.
    counts = dict(zip(result.index.astype(str), result["count"]))
    assert counts["AAPL"] == 2
    assert counts["GOOGL"] == 2
    aapl_acc = result.loc[result.index.astype(str) == "AAPL", "accuracy"].iloc[0]
    googl_acc = result.loc[result.index.astype(str) == "GOOGL", "accuracy"].iloc[0]
    assert float(aapl_acc) == 1.0  # 2/2
    assert float(googl_acc) == 0.5  # 1/2


def test_accuracy_by_ticker_none_when_labels_missing() -> None:
    df = pd.DataFrame({"ticker": ["AAPL", "AAPL"], "prediction": ["UP", "DOWN"]})
    result = accuracy_by_ticker(df)
    assert result.loc["AAPL", "accuracy"] is None or pd.isna(
        result.loc["AAPL", "accuracy"]
    )


def test_accuracy_by_ticker_empty() -> None:
    result = accuracy_by_ticker(pd.DataFrame())
    assert result.empty
    assert list(result.columns) == ["count", "accuracy"]


def test_accuracy_by_ticker_no_ticker_column() -> None:
    df = pd.DataFrame({"prediction": ["UP"]})
    result = accuracy_by_ticker(df)
    assert result.empty


# ---------------------------------------------------------------------------
# apply_filters
# ---------------------------------------------------------------------------


def _full_predictions() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sample_id": ["S1", "S2", "S3", "S4"],
            "ticker": ["AAPL", "GOOGL", "AAPL", "META"],
            "forecast_time": [
                "2025-03-10 09:00",
                "2025-03-11 09:00",
                "2025-03-12 09:00",
                "2025-03-13 09:00",
            ],
            "prediction": ["UP", "DOWN", "HOLD", "UP"],
        }
    )


def _full_evidence() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sample_id": ["S1", "S1", "S2", "S3"],
            "ticker": ["AAPL", "AAPL", "GOOGL", "AAPL"],
            "is_cited": [True, False, True, True],
            "is_temporally_valid": [True, True, False, True],
            "forecast_time": [
                "2025-03-10 09:00",
                "2025-03-10 09:00",
                "2025-03-11 09:00",
                "2025-03-12 09:00",
            ],
        }
    )


def _full_faithfulness() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sample_id": ["S1", "S2", "S3", "S4"],
            "ticker": ["AAPL", "GOOGL", "AAPL", "META"],
            "prediction": ["UP", "DOWN", "HOLD", "UP"],
            "confidence_drop": [0.25, 0.10, 0.01, 0.30],
            "faithfulness_label": ["high", "medium", "low", "high"],
        }
    )


def test_apply_filters_ticker_list() -> None:
    out = apply_filters(
        _full_predictions(), {"tickers": ["AAPL"]}
    )
    assert set(out["ticker"].unique()) == {"AAPL"}


def test_apply_filters_prediction_list() -> None:
    out = apply_filters(
        _full_predictions(), {"predictions": ["UP"]}
    )
    assert set(out["prediction"].unique()) == {"UP"}


def test_apply_filters_faithfulness_label_list() -> None:
    out = apply_filters(
        _full_faithfulness(), {"faithfulness_levels": ["high"]}
    )
    assert set(out["faithfulness_label"].unique()) == {"high"}


def test_apply_filters_faithfulness_level_derived_from_verdict() -> None:
    """Faithfulness levels should also work on the un-normalized frame."""
    raw = _full_faithfulness().drop(columns=["faithfulness_label"])
    # The un-normalized frame carries `confidence_drop`; the filter
    # helper derives the level on the fly when `faithfulness_label`
    # is absent. The raw frame here does NOT have a `verdict` column.
    assert "verdict" not in raw.columns
    out = apply_filters(raw, {"faithfulness_levels": ["high"]})
    assert len(out) == 2
    assert all(float(d) >= 0.20 for d in out["confidence_drop"])


def test_apply_filters_date_range() -> None:
    out = apply_filters(
        _full_predictions(),
        {"date_range": ("2025-03-11", "2025-03-12")},
    )
    assert set(out["sample_id"]) == {"S2", "S3"}


def test_apply_filters_cited_only() -> None:
    out = apply_filters(_full_evidence(), {"cited_only": True})
    assert out["is_cited"].all()


def test_apply_filters_leakage_only() -> None:
    out = apply_filters(_full_evidence(), {"leakage_only": True})
    assert (out["is_temporally_valid"] == False).all()  # noqa: E712


def test_apply_filters_combined() -> None:
    out = apply_filters(
        _full_evidence(),
        {"tickers": ["AAPL"], "cited_only": True},
    )
    assert set(out["ticker"].unique()) == {"AAPL"}
    assert out["is_cited"].all()


def test_apply_filters_no_op_when_filters_empty() -> None:
    df = _full_predictions()
    out = apply_filters(df, {})
    assert len(out) == len(df)


def test_apply_filters_none_inputs() -> None:
    assert apply_filters(None, {}).empty


def test_apply_filters_does_not_mutate_input() -> None:
    df = _full_predictions()
    snapshot = df.copy()
    apply_filters(df, {"tickers": ["AAPL"]})
    assert df.equals(snapshot)


def test_apply_filters_invalid_date_range_is_no_op() -> None:
    df = _full_predictions()
    out = apply_filters(df, {"date_range": (None, None)})
    assert len(out) == len(df)
    out = apply_filters(df, {"date_range": None})
    assert len(out) == len(df)


# ---------------------------------------------------------------------------
# Constants sanity
# ---------------------------------------------------------------------------


def test_constants_thresholds() -> None:
    assert FAITHFULNESS_HIGH_THRESHOLD == 0.20
    assert FAITHFULNESS_MEDIUM_THRESHOLD == 0.05
    assert LEAKAGE_WARNING_THRESHOLD == 1
    assert LEAKAGE_CRITICAL_THRESHOLD == 3


def test_constants_valid_predictions() -> None:
    assert set(VALID_PREDICTIONS) == {"UP", "DOWN", "HOLD"}