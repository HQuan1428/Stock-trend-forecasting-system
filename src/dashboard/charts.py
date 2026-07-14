"""Plotly figure builders for the dashboard.

Pure functions: take pre-aggregated data (from ``metrics``/DataFrames),
return ``plotly.graph_objects.Figure``. No Streamlit, no I/O. Color
constants carried over from the previous dashboard for visual
continuity.
"""

from __future__ import annotations

from typing import Dict, List, Sequence

import pandas as pd
import plotly.graph_objects as go

COLOR_HIGH = "#2ca02c"
COLOR_MEDIUM = "#ffbb33"
COLOR_LOW = "#d62728"
COLOR_ACCENT = "#1f77b4"

FAITHFULNESS_COLOR_MAP: Dict[str, str] = {
    "HIGH": COLOR_HIGH,
    "MEDIUM": COLOR_MEDIUM,
    "LOW": COLOR_LOW,
}

PREDICTION_COLOR_MAP: Dict[str, str] = {
    "UP": COLOR_HIGH,
    "DOWN": COLOR_LOW,
    "HOLD": COLOR_MEDIUM,
}

REGIME_COLOR_MAP: Dict[str, str] = {
    "bull": COLOR_HIGH,
    "bear": COLOR_LOW,
    "sideways": COLOR_MEDIUM,
}


def build_prediction_distribution_chart(distribution: Dict[str, int]) -> go.Figure:
    """A7: bar chart UP/DOWN/HOLD counts."""
    labels = list(distribution.keys())
    fig = go.Figure(
        go.Bar(
            x=labels,
            y=[distribution[k] for k in labels],
            marker_color=[PREDICTION_COLOR_MAP.get(k, COLOR_ACCENT) for k in labels],
            hovertemplate="%{x}: %{y}<extra></extra>",
        )
    )
    fig.update_layout(
        title="Phân bố prediction",
        xaxis_title="Prediction",
        yaxis_title="Số sample",
    )
    return fig


def build_confidence_drop_chart(samples: pd.DataFrame) -> go.Figure:
    """A7: per-sample confidence drop, colored by HIGH/MEDIUM/LOW."""
    fig = go.Figure()
    for level, color in FAITHFULNESS_COLOR_MAP.items():
        part = samples[samples["faithfulness_label"] == level]
        if part.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=part["sample_id"],
                y=part["confidence_drop"],
                mode="markers",
                name=level,
                marker={"color": color, "size": 8},
                hovertemplate=(
                    "sample=%{x}<br>drop=%{y:.3f}<br>" + level + "<extra></extra>"
                ),
            )
        )
    fig.update_layout(
        title="Confidence drop khi bỏ cited evidence (màu theo faithfulness)",
        xaxis_title="sample_id",
        yaxis_title="confidence_drop",
        xaxis={"showticklabels": False},
    )
    return fig


def build_faithfulness_radar_chart(
    axes: Sequence[str], values: Sequence[float]
) -> go.Figure:
    """§9: 5-axis radar (all values in [0, 1]); closes the polygon."""
    theta = list(axes) + [axes[0]]
    r = list(values) + [values[0]]
    fig = go.Figure(
        go.Scatterpolar(
            r=r,
            theta=theta,
            fill="toself",
            line={"color": COLOR_ACCENT},
            hovertemplate="%{theta}: %{r:.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        title="Faithfulness radar (trung bình toàn dataset)",
        polar={"radialaxis": {"range": [0, 1]}},
        showlegend=False,
    )
    return fig


def build_class_confidences_chart(class_confidences: Dict[str, float]) -> go.Figure:
    """Live Demo: UP/DOWN/HOLD vote breakdown for one sample."""
    order = ["UP", "DOWN", "HOLD"]
    fig = go.Figure(
        go.Bar(
            x=order,
            y=[float(class_confidences.get(k, 0.0)) for k in order],
            marker_color=[PREDICTION_COLOR_MAP[k] for k in order],
            hovertemplate="%{x}: %{y:.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        title="Phân rã vote UP/DOWN/HOLD",
        yaxis={"range": [0, 1]},
        yaxis_title="class confidence",
    )
    return fig


def build_sufficiency_chart(samples: pd.DataFrame) -> go.Figure:
    """B1: sufficiency_score vs counterfactual_delta scatter."""
    fig = go.Figure(
        go.Scatter(
            x=samples["sufficiency_score"],
            y=samples["counterfactual_delta"],
            mode="markers",
            marker={"color": COLOR_ACCENT, "size": 8},
            text=samples["sample_id"],
            hovertemplate=(
                "sample=%{text}<br>sufficiency=%{x:.2f}"
                "<br>counterfactual Δ=%{y:.2f}<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        title="B1 — Sufficiency vs Counterfactual delta",
        xaxis_title="sufficiency_score",
        yaxis_title="counterfactual_delta",
    )
    return fig


def build_coverage_chart(samples: pd.DataFrame) -> go.Figure:
    """B2: histogram of counterevidence coverage."""
    fig = go.Figure(
        go.Histogram(
            x=samples["counterevidence_coverage"],
            xbins={"start": 0.0, "end": 1.0001, "size": 0.25},
            marker_color=COLOR_ACCENT,
            hovertemplate="coverage=%{x}<br>count=%{y}<extra></extra>",
        )
    )
    fig.update_layout(
        title="B2 — Phân bố Counterevidence Coverage",
        xaxis_title="counterevidence_coverage",
        yaxis_title="Số sample",
    )
    return fig


def build_regime_chart(regimes: Dict[str, int]) -> go.Figure:
    """B3: regime breakdown bar chart."""
    labels = list(regimes.keys())
    fig = go.Figure(
        go.Bar(
            x=labels,
            y=[regimes[k] for k in labels],
            marker_color=[REGIME_COLOR_MAP.get(k, COLOR_ACCENT) for k in labels],
            hovertemplate="%{x}: %{y}<extra></extra>",
        )
    )
    fig.update_layout(
        title="B3 — Phân bố regime",
        xaxis_title="Regime",
        yaxis_title="Số sample",
    )
    return fig


__all__ = [
    "COLOR_ACCENT",
    "COLOR_HIGH",
    "COLOR_LOW",
    "COLOR_MEDIUM",
    "FAITHFULNESS_COLOR_MAP",
    "PREDICTION_COLOR_MAP",
    "REGIME_COLOR_MAP",
    "build_class_confidences_chart",
    "build_confidence_drop_chart",
    "build_coverage_chart",
    "build_faithfulness_radar_chart",
    "build_prediction_distribution_chart",
    "build_regime_chart",
    "build_sufficiency_chart",
]