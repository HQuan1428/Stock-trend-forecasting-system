"""Plotly chart builders for the dashboard.

Each builder accepts a :class:`pandas.DataFrame` (or a small derived
structure, e.g., the result of :func:`accuracy_by_ticker`) and returns a
:class:`plotly.graph_objects.Figure`. The builders **do not** import
Streamlit; they are pure with respect to the plotting library and can
be unit-tested by inspecting the returned ``Figure`` object.

The builders are **deterministic** given the same input: the same
DataFrame produces the same ``Figure.data`` and ``Figure.layout``
(byte-equal under the standard Plotly serialization).

The color constants are exported so the case-detail panel and the
severity banner can reuse them.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import pandas as pd
import plotly.graph_objects as go

from src.dashboard.metrics import (
    FAITHFULNESS_LEVELS,
    LEAKAGE_SEVERITIES,
    VALID_PREDICTIONS,
    classify_faithfulness_level,
    leakage_severity,
)


# ---------------------------------------------------------------------------
# Color constants (exported for the rest of the dashboard)
# ---------------------------------------------------------------------------


#: Green for the ``high`` faithfulness level.
COLOR_HIGH: str = "#2ca02c"
#: Amber for the ``medium`` faithfulness level.
COLOR_MEDIUM: str = "#ffbb33"
#: Red for the ``low`` faithfulness level.
COLOR_LOW: str = "#d62728"
#: Green for the ``ok`` leakage severity.
COLOR_OK: str = "#2ca02c"
#: Amber for the ``warning`` leakage severity.
COLOR_WARNING: str = "#ffbb33"
#: Red for the ``critical`` leakage severity.
COLOR_CRITICAL: str = "#d62728"
#: Neutral blue for non-categorical elements (axes, default bars).
COLOR_ACCENT: str = "#1f77b4"


# ---------------------------------------------------------------------------
# Per-level color maps
# ---------------------------------------------------------------------------


FAITHFULNESS_COLOR_MAP: Dict[str, str] = {
    "high": COLOR_HIGH,
    "medium": COLOR_MEDIUM,
    "low": COLOR_LOW,
}

LEAKAGE_SEVERITY_COLOR_MAP: Dict[str, str] = {
    "ok": COLOR_OK,
    "warning": COLOR_WARNING,
    "critical": COLOR_CRITICAL,
}

PREDICTION_COLOR_MAP: Dict[str, str] = {
    "UP": "#2ca02c",
    "DOWN": "#d62728",
    "HOLD": "#7f7f7f",
}


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def build_prediction_distribution_chart(df: pd.DataFrame) -> go.Figure:
    """Return a Plotly bar chart of ``UP`` / ``DOWN`` / ``HOLD`` counts.

    The X-axis lists the three classes in a fixed order; the Y-axis
    lists the row count. Empty classes are rendered as zero-height
    bars so the chart is informative on sparse data.
    """
    counts: Dict[str, int] = {label: 0 for label in VALID_PREDICTIONS}
    if df is not None and not df.empty and "prediction" in df.columns:
        series = df["prediction"].astype(str)
        for label in VALID_PREDICTIONS:
            counts[label] = int((series == label).sum())

    fig = go.Figure(
        data=[
            go.Bar(
                x=list(VALID_PREDICTIONS),
                y=[counts[label] for label in VALID_PREDICTIONS],
                marker_color=[PREDICTION_COLOR_MAP[label] for label in VALID_PREDICTIONS],
                text=[counts[label] for label in VALID_PREDICTIONS],
                textposition="outside",
                hovertemplate="%{x}: %{y}<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        title="Prediction Distribution",
        xaxis_title="Prediction",
        yaxis_title="Count",
        showlegend=False,
        margin={"l": 40, "r": 20, "t": 40, "b": 40},
        height=320,
    )
    return fig


def build_confidence_drop_chart(df: pd.DataFrame) -> go.Figure:
    """Return a Plotly scatter chart of ``confidence_drop`` per ``sample_id``.

    Each marker is colored by the row's faithfulness level (green /
    amber / red). The legend is hidden — color is documented in the
    accompanying text rather than a key — to keep the chart clean.
    """
    if df is None or df.empty or "confidence_drop" not in df.columns:
        fig = go.Figure()
        fig.update_layout(
            title="Confidence Drop per Sample",
            xaxis_title="Sample index",
            yaxis_title="Confidence drop",
            showlegend=False,
            height=320,
        )
        return fig

    work = df.copy()
    if "sample_id" not in work.columns:
        work["sample_id"] = [f"sample-{i}" for i in range(len(work))]
    work["confidence_drop"] = pd.to_numeric(
        work["confidence_drop"], errors="coerce"
    ).fillna(0.0)
    work["_level"] = work["confidence_drop"].apply(classify_faithfulness_level)
    work["_color"] = work["_level"].map(FAITHFULNESS_COLOR_MAP)

    fig = go.Figure(
        data=[
            go.Scatter(
                x=work["sample_id"].astype(str),
                y=work["confidence_drop"],
                mode="markers",
                marker=dict(
                    color=work["_color"],
                    size=12,
                    line=dict(color="#333", width=1),
                ),
                text=work["_level"],
                hovertemplate="sample_id=%{x}<br>drop=%{y:.3f}<br>level=%{text}<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        title="Confidence Drop per Sample",
        xaxis_title="Sample",
        yaxis_title="Confidence drop",
        showlegend=False,
        height=320,
        margin={"l": 40, "r": 20, "t": 40, "b": 80},
    )
    fig.update_xaxes(tickangle=-45)
    return fig


def build_temporal_leakage_chart(df: pd.DataFrame) -> go.Figure:
    """Return a Plotly bar chart of leakage counts grouped by ``ticker``."""
    if df is None or df.empty or "ticker" not in df.columns:
        fig = go.Figure()
        fig.update_layout(
            title="Temporal Leakage by Ticker",
            xaxis_title="Ticker",
            yaxis_title="Leakage rows",
            showlegend=False,
            height=320,
        )
        return fig
    grouped = df.groupby("ticker", dropna=False).size().reset_index(name="count")
    grouped = grouped.sort_values("count", ascending=False)
    fig = go.Figure(
        data=[
            go.Bar(
                x=grouped["ticker"].astype(str),
                y=grouped["count"],
                marker_color=COLOR_WARNING,
                text=grouped["count"],
                textposition="outside",
                hovertemplate="%{x}: %{y}<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        title="Temporal Leakage by Ticker",
        xaxis_title="Ticker",
        yaxis_title="Leakage rows",
        showlegend=False,
        height=320,
        margin={"l": 40, "r": 20, "t": 40, "b": 40},
    )
    return fig


def build_accuracy_by_ticker_chart(accuracy_df: pd.DataFrame) -> go.Figure:
    """Return a Plotly bar chart of per-ticker accuracy.

    Ticker's whose accuracy is ``None`` (no labels) are rendered with a
    zero-height bar and a tooltip explaining why. The chart is sorted
    by ``count`` descending, matching the order produced by
    :func:`src.dashboard.metrics.accuracy_by_ticker`.
    """
    if accuracy_df is None or accuracy_df.empty:
        fig = go.Figure()
        fig.update_layout(
            title="Accuracy by Ticker",
            xaxis_title="Ticker",
            yaxis_title="Accuracy",
            showlegend=False,
            height=320,
        )
        return fig
    work = accuracy_df.copy()
    work["accuracy_display"] = work["accuracy"].fillna(0.0)
    work["accuracy_text"] = work["accuracy"].apply(
        lambda v: "n/a" if pd.isna(v) else f"{float(v):.0%}"
    )
    fig = go.Figure(
        data=[
            go.Bar(
                x=work.index.astype(str),
                y=work["accuracy_display"],
                marker_color=COLOR_ACCENT,
                text=work["accuracy_text"],
                textposition="outside",
                hovertemplate="%{x}: %{text}<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        title="Accuracy by Ticker",
        xaxis_title="Ticker",
        yaxis_title="Accuracy",
        yaxis=dict(range=[0, 1]),
        showlegend=False,
        height=320,
        margin={"l": 40, "r": 20, "t": 40, "b": 40},
    )
    return fig


__all__ = [
    "COLOR_HIGH",
    "COLOR_MEDIUM",
    "COLOR_LOW",
    "COLOR_OK",
    "COLOR_WARNING",
    "COLOR_CRITICAL",
    "COLOR_ACCENT",
    "FAITHFULNESS_COLOR_MAP",
    "LEAKAGE_SEVERITY_COLOR_MAP",
    "PREDICTION_COLOR_MAP",
    "build_prediction_distribution_chart",
    "build_confidence_drop_chart",
    "build_temporal_leakage_chart",
    "build_accuracy_by_ticker_chart",
]