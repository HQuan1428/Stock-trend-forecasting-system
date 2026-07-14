"""Tests for src.dashboard.charts (pure figure builders)."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from src.dashboard import charts
from src.dashboard.metrics import RADAR_AXES


def _samples() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "sample_id": "S1", "confidence_drop": 0.45,
                "faithfulness_label": "HIGH",
                "sufficiency_score": 0.9, "counterfactual_delta": 0.2,
                "counterevidence_coverage": 1.0,
            },
            {
                "sample_id": "S2", "confidence_drop": 0.0,
                "faithfulness_label": "LOW",
                "sufficiency_score": 0.5, "counterfactual_delta": 0.0,
                "counterevidence_coverage": 0.0,
            },
        ]
    )


def test_prediction_distribution_chart() -> None:
    fig = charts.build_prediction_distribution_chart({"UP": 3, "DOWN": 1, "HOLD": 2})
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1
    assert list(fig.data[0].y) == [3, 1, 2]


def test_confidence_drop_chart_one_trace_per_present_level() -> None:
    fig = charts.build_confidence_drop_chart(_samples())
    names = {trace.name for trace in fig.data}
    assert names == {"HIGH", "LOW"}  # no MEDIUM rows → no MEDIUM trace


def test_radar_chart_closes_polygon() -> None:
    values = [0.9, 0.8, 0.5, 0.7, 0.4]
    fig = charts.build_faithfulness_radar_chart(RADAR_AXES, values)
    trace = fig.data[0]
    assert len(trace.r) == len(RADAR_AXES) + 1
    assert trace.r[0] == trace.r[-1]
    assert trace.theta[0] == trace.theta[-1]


def test_class_confidences_chart_fixed_order() -> None:
    fig = charts.build_class_confidences_chart({"HOLD": 0.2, "UP": 0.7, "DOWN": 0.1})
    assert list(fig.data[0].x) == ["UP", "DOWN", "HOLD"]
    assert list(fig.data[0].y) == [0.7, 0.1, 0.2]


def test_sufficiency_and_coverage_and_regime_charts() -> None:
    samples = _samples()
    assert len(charts.build_sufficiency_chart(samples).data[0].x) == 2
    assert isinstance(charts.build_coverage_chart(samples), go.Figure)
    regime_fig = charts.build_regime_chart({"bull": 2, "bear": 1})
    assert list(regime_fig.data[0].y) == [2, 1]