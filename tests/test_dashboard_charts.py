"""Unit tests for ``src.dashboard.charts``."""

from __future__ import annotations

import json

import pandas as pd
import plotly.graph_objects as go
import pytest

from src.dashboard.charts import (
    COLOR_HIGH,
    COLOR_LOW,
    COLOR_MEDIUM,
    COLOR_OK,
    COLOR_WARNING,
    COLOR_CRITICAL,
    FAITHFULNESS_COLOR_MAP,
    PREDICTION_COLOR_MAP,
    build_accuracy_by_ticker_chart,
    build_confidence_drop_chart,
    build_prediction_distribution_chart,
    build_temporal_leakage_chart,
)
from src.dashboard.metrics import accuracy_by_ticker


def _is_serializable(fig: go.Figure) -> bool:
    """A Figure is testable when its JSON round-trips without errors."""
    try:
        json.loads(fig.to_json())
        return True
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# build_prediction_distribution_chart
# ---------------------------------------------------------------------------


def test_prediction_distribution_chart_has_three_bars() -> None:
    df = pd.DataFrame({"prediction": ["UP", "UP", "DOWN", "HOLD"]})
    fig = build_prediction_distribution_chart(df)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1
    bar = fig.data[0]
    assert isinstance(bar, go.Bar)
    assert list(bar.x) == ["UP", "DOWN", "HOLD"]
    assert list(bar.y) == [2, 1, 1]


def test_prediction_distribution_chart_handles_empty_input() -> None:
    fig = build_prediction_distribution_chart(pd.DataFrame())
    bar = fig.data[0]
    assert list(bar.y) == [0, 0, 0]


def test_prediction_distribution_chart_uses_prediction_colors() -> None:
    df = pd.DataFrame({"prediction": ["UP", "DOWN"]})
    fig = build_prediction_distribution_chart(df)
    bar = fig.data[0]
    assert list(bar.marker.color) == [
        PREDICTION_COLOR_MAP["UP"],
        PREDICTION_COLOR_MAP["DOWN"],
        PREDICTION_COLOR_MAP["HOLD"],
    ]


def test_prediction_distribution_chart_is_serializable() -> None:
    fig = build_prediction_distribution_chart(pd.DataFrame({"prediction": ["UP"]}))
    assert _is_serializable(fig)


# ---------------------------------------------------------------------------
# build_confidence_drop_chart
# ---------------------------------------------------------------------------


def test_confidence_drop_chart_scatter_per_sample() -> None:
    df = pd.DataFrame(
        {
            "sample_id": ["S1", "S2", "S3"],
            "confidence_drop": [0.25, 0.10, 0.01],
        }
    )
    fig = build_confidence_drop_chart(df)
    scatter = fig.data[0]
    assert isinstance(scatter, go.Scatter)
    assert list(scatter.x) == ["S1", "S2", "S3"]
    assert list(scatter.y) == pytest.approx([0.25, 0.10, 0.01])


def test_confidence_drop_chart_colors_by_level() -> None:
    df = pd.DataFrame(
        {
            "sample_id": ["S1", "S2", "S3"],
            "confidence_drop": [0.25, 0.10, 0.01],
        }
    )
    fig = build_confidence_drop_chart(df)
    scatter = fig.data[0]
    colors = list(scatter.marker.color)
    assert colors[0] == COLOR_HIGH or colors[0] == FAITHFULNESS_COLOR_MAP["high"]
    assert colors[1] == COLOR_MEDIUM or colors[1] == FAITHFULNESS_COLOR_MAP["medium"]
    assert colors[2] == COLOR_LOW or colors[2] == FAITHFULNESS_COLOR_MAP["low"]


def test_confidence_drop_chart_empty_input_is_empty_figure() -> None:
    fig = build_confidence_drop_chart(pd.DataFrame())
    # Empty figure still serializes; just no data points.
    assert _is_serializable(fig)


def test_confidence_drop_chart_legend_is_hidden() -> None:
    df = pd.DataFrame({"sample_id": ["S1"], "confidence_drop": [0.3]})
    fig = build_confidence_drop_chart(df)
    assert fig.layout.showlegend is False


# ---------------------------------------------------------------------------
# build_temporal_leakage_chart
# ---------------------------------------------------------------------------


def test_temporal_leakage_chart_groups_by_ticker() -> None:
    df = pd.DataFrame(
        {
            "ticker": ["AAPL", "AAPL", "GOOGL", "META"],
        }
    )
    fig = build_temporal_leakage_chart(df)
    bar = fig.data[0]
    assert isinstance(bar, go.Bar)
    assert set(bar.x) == {"AAPL", "GOOGL", "META"}
    assert sum(bar.y) == 4


def test_temporal_leakage_chart_empty() -> None:
    fig = build_temporal_leakage_chart(pd.DataFrame())
    assert _is_serializable(fig)


def test_temporal_leakage_chart_warning_color() -> None:
    df = pd.DataFrame({"ticker": ["AAPL"]})
    fig = build_temporal_leakage_chart(df)
    bar = fig.data[0]
    assert bar.marker.color == COLOR_WARNING


# ---------------------------------------------------------------------------
# build_accuracy_by_ticker_chart
# ---------------------------------------------------------------------------


def test_accuracy_by_ticker_chart_from_dataframe() -> None:
    df = pd.DataFrame(
        {
            "ticker": ["AAPL", "AAPL", "GOOGL"],
            "prediction": ["UP", "DOWN", "UP"],
            "label": ["UP", "DOWN", "DOWN"],
        }
    )
    acc = accuracy_by_ticker(df)
    fig = build_accuracy_by_ticker_chart(acc)
    bar = fig.data[0]
    assert isinstance(bar, go.Bar)
    assert set(bar.x) == {"AAPL", "GOOGL"}


def test_accuracy_by_ticker_chart_empty() -> None:
    fig = build_accuracy_by_ticker_chart(pd.DataFrame())
    assert _is_serializable(fig)


def test_accuracy_by_ticker_chart_y_axis_capped_at_one() -> None:
    df = pd.DataFrame(
        {
            "ticker": ["AAPL", "AAPL"],
            "prediction": ["UP", "UP"],
            "label": ["UP", "UP"],
        }
    )
    acc = accuracy_by_ticker(df)
    fig = build_accuracy_by_ticker_chart(acc)
    # Plotly serializes range as a tuple; convert for comparison.
    assert list(fig.layout.yaxis.range) == [0, 1]


# ---------------------------------------------------------------------------
# Color constants sanity
# ---------------------------------------------------------------------------


def test_color_constants_three_levels() -> None:
    """The dashboard reuses the same color for the matching pair
    (high/ok, medium/warning, low/critical). That is intentional — the
    three categorical states map to the same three colors. We assert
    the pairing, not the uniqueness of the six names.
    """
    assert COLOR_HIGH == COLOR_OK
    assert COLOR_MEDIUM == COLOR_WARNING
    assert COLOR_LOW == COLOR_CRITICAL


def test_color_constants_format() -> None:
    for color in (COLOR_HIGH, COLOR_LOW, COLOR_OK, COLOR_WARNING, COLOR_CRITICAL):
        assert color.startswith("#")
        assert len(color) == 7