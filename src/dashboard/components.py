"""Streamlit UI components for the dashboard.

This module is the **only** place in the dashboard package that imports
Streamlit. The helpers here are thin wrappers around the pure
:mod:`src.dashboard.metrics` and :mod:`src.dashboard.charts` modules.

The components are deliberately **side-effect-free with respect to disk**:
they never write to ``outputs/``. They render to the Streamlit session
state and never mutate global state.

Testing strategy: the helpers are not unit-tested directly because
running Streamlit requires a server. Instead, the :mod:`src.dashboard.metrics`
and :mod:`src.dashboard.charts` functions they delegate to are tested
in isolation. The acceptance-scenario tests assert that those
delegations produce the expected values for the sample fixtures.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Tuple

import pandas as pd

import streamlit as st

from src.dashboard.charts import (
    COLOR_HIGH,
    COLOR_LOW,
    COLOR_MEDIUM,
    COLOR_OK,
    COLOR_WARNING,
    COLOR_CRITICAL,
    build_accuracy_by_ticker_chart,
    build_confidence_drop_chart,
    build_prediction_distribution_chart,
    build_temporal_leakage_chart,
)
from src.dashboard.data_loader import DashboardData
from src.dashboard.metrics import (
    FAITHFULNESS_LEVELS,
    VALID_PREDICTIONS,
    accuracy,
    accuracy_by_ticker,
    average_confidence,
    average_confidence_drop,
    average_temporal_validity,
    classify_faithfulness_level,
    leakage_severity,
    prediction_distribution,
    temporal_leakage_count,
)


#: Template string for the case-detail interpretation. Static — no
#: time-based or random content; verified by a regression test.
CASE_DETAIL_TEMPLATE: str = (
    "The model predicted **{prediction}** with confidence "
    "**{original_confidence:.0%}**. After removing the cited evidence, "
    "confidence changed to **{confidence_after_removal:.0%}** "
    "(drop = **{confidence_drop:.0%}**). This corresponds to "
    "**{faithfulness_level}** faithfulness — the cited evidence appears "
    "to be {supportive_phrase}."
)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------


def _unique_values(df: Optional[pd.DataFrame], column: str) -> List[str]:
    if df is None or df.empty or column not in df.columns:
        return []
    return sorted(set(df[column].dropna().astype(str).tolist()))


def render_sidebar(data: DashboardData) -> Dict[str, Any]:
    """Render the six sidebar filters and return the active state.

    Returns a dict with keys ``tickers``, ``predictions``,
    ``faithfulness_levels``, ``date_range``, ``cited_only``,
    ``leakage_only``. Each key holds the user-selected value; the
    Streamlit app applies them via
    :func:`src.dashboard.metrics.apply_filters`.
    """
    st.sidebar.header("Filters")

    # Tickers: union of available tickers across the four frames.
    tickers_pool = sorted(
        set(
            _unique_values(data.predictions, "ticker")
            + _unique_values(data.evidence, "ticker")
            + _unique_values(data.faithfulness, "ticker")
            + _unique_values(data.leakage, "ticker")
        )
    )
    selected_tickers = st.sidebar.multiselect(
        "Ticker",
        options=tickers_pool,
        default=tickers_pool,
        help="Filter to one or more tickers. 'All' is the default.",
    )

    # Predictions: union of available predictions across predictions + faithfulness.
    preds_pool = sorted(
        set(
            _unique_values(data.predictions, "prediction")
            + _unique_values(data.faithfulness, "prediction")
        )
        or list(VALID_PREDICTIONS)
    )
    selected_predictions = st.sidebar.multiselect(
        "Prediction",
        options=preds_pool,
        default=preds_pool,
    )

    # Faithfulness levels.
    selected_levels = st.sidebar.multiselect(
        "Faithfulness level",
        options=list(FAITHFULNESS_LEVELS),
        default=list(FAITHFULNESS_LEVELS),
    )

    # Forecast date range.
    # Streamlit's date_input accepts date / datetime / ISO string / "today",
    # but NOT pandas.Timestamp, numpy.datetime64, or None when the widget is
    # in range mode. Build a safe tuple of two datetime.date values; if no
    # forecast times are available, fall back to ("today", "today") so the
    # widget always receives two valid values.
    import datetime as _dt

    dates: List[_dt.date] = []
    if data.predictions is not None and "forecast_time" in data.predictions.columns:
        parsed = pd.to_datetime(data.predictions["forecast_time"], errors="coerce")
        dates = sorted({d.date() for d in parsed.dropna()})

    today = _dt.date.today()
    if dates:
        start_default: Any = dates[0]
        end_default: Any = dates[-1]
    else:
        start_default = today
        end_default = today
    date_range = st.sidebar.date_input(
        "Forecast date range",
        value=(start_default, end_default),
    )

    cited_only = st.sidebar.checkbox(
        "Show only cited evidence",
        value=False,
        help="Restrict the Evidence tab to rows where is_cited == True.",
    )
    leakage_only = st.sidebar.checkbox(
        "Show only temporal leakage cases",
        value=False,
        help="Restrict the Temporal Leakage tab to rows where news_time > forecast_time.",
    )

    # Normalize date_range to a tuple of length 2.
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        start, end = date_range
    else:
        start = end = None

    return {
        "tickers": selected_tickers,
        "predictions": selected_predictions,
        "faithfulness_levels": selected_levels,
        "date_range": (start, end),
        "cited_only": cited_only,
        "leakage_only": leakage_only,
    }


# ---------------------------------------------------------------------------
# Overview tab
# ---------------------------------------------------------------------------


def render_overview_tab(
    data: DashboardData,
    filtered_predictions: pd.DataFrame,
    filtered_evidence: pd.DataFrame,
    filtered_faithfulness: pd.DataFrame,
    filtered_leakage: pd.DataFrame,
) -> None:
    """Render the Overview tab content."""
    st.subheader("Overview")
    cols = st.columns(4)
    cols[0].metric(
        "Total forecasts",
        int(len(filtered_predictions)) if filtered_predictions is not None else 0,
    )
    acc = accuracy(filtered_predictions)
    cols[1].metric(
        "Accuracy",
        f"{acc:.0%}" if acc is not None else "n/a",
    )
    cols[2].metric(
        "Avg confidence",
        f"{average_confidence(filtered_predictions):.0%}",
    )
    cols[3].metric(
        "Avg confidence drop",
        f"{average_confidence_drop(filtered_faithfulness):.0%}",
    )

    cols = st.columns(3)
    cols[0].metric(
        "Temporal leakage rows",
        int(temporal_leakage_count(leakage_df=filtered_leakage)),
    )
    cols[1].metric(
        "Avg temporal validity",
        f"{average_temporal_validity(filtered_faithfulness):.0%}",
    )
    counts = prediction_distribution(filtered_predictions)
    cols[2].metric(
        "HOLD share",
        f"{counts['HOLD'] / max(1, sum(counts.values())):.0%}",
    )

    st.plotly_chart(
        build_prediction_distribution_chart(filtered_predictions),
        use_container_width=True,
        key="chart-prediction-distribution",
    )

    if filtered_faithfulness is not None and not filtered_faithfulness.empty:
        acc_df = accuracy_by_ticker(filtered_faithfulness)
        st.subheader("Accuracy by ticker")
        st.dataframe(acc_df, use_container_width=True)
        st.plotly_chart(
            build_accuracy_by_ticker_chart(acc_df),
            use_container_width=True,
            key="chart-accuracy-by-ticker",
        )


# ---------------------------------------------------------------------------
# Evidence tab
# ---------------------------------------------------------------------------


def render_evidence_tab(filtered_evidence: pd.DataFrame) -> None:
    """Render the Evidence tab content."""
    st.subheader("Evidence")
    if filtered_evidence is None or filtered_evidence.empty:
        st.info("No evidence rows match the current filters.")
        return

    view = filtered_evidence.copy()
    view["is_cited_display"] = view["is_cited"].apply(
        lambda v: "✓ cited" if bool(v) else "—"
    )
    view["temporal_display"] = view["is_temporally_valid"].apply(
        lambda v: "✓ valid" if bool(v) else "⚠ temporal leakage"
    )
    st.dataframe(
        view[
            [
                "sample_id",
                "ticker",
                "forecast_time",
                "news_time",
                "prediction",
                "evidence_text",
                "polarity",
                "expected_direction",
                "evidence_role",
                "support_score",
                "is_cited_display",
                "temporal_display",
            ]
        ],
        use_container_width=True,
    )


# ---------------------------------------------------------------------------
# Confidence Drop tab
# ---------------------------------------------------------------------------


def render_confidence_drop_tab(filtered_faithfulness: pd.DataFrame) -> None:
    """Render the Confidence Drop tab content."""
    st.subheader("Confidence Drop Analysis")
    if filtered_faithfulness is None or filtered_faithfulness.empty:
        st.info("No faithfulness rows match the current filters.")
        return

    st.plotly_chart(
        build_confidence_drop_chart(filtered_faithfulness),
        use_container_width=True,
        key="chart-confidence-drop",
    )

    # Bucket counts.
    if "faithfulness_label" in filtered_faithfulness.columns:
        bucket_counts = filtered_faithfulness["faithfulness_label"].value_counts().to_dict()
    else:
        bucket_counts = {}
        for _, row in filtered_faithfulness.iterrows():
            level = classify_faithfulness_level(row.get("confidence_drop", 0.0))
            bucket_counts[level] = bucket_counts.get(level, 0) + 1

    cols = st.columns(3)
    cols[0].metric("High faithfulness", bucket_counts.get("high", 0))
    cols[1].metric("Medium faithfulness", bucket_counts.get("medium", 0))
    cols[2].metric("Low faithfulness", bucket_counts.get("low", 0))

    st.dataframe(
        filtered_faithfulness[
            [
                c
                for c in (
                    "sample_id",
                    "ticker",
                    "prediction",
                    "original_confidence",
                    "confidence_without_cited_evidence",
                    "confidence_drop",
                    "faithfulness_label",
                )
                if c in filtered_faithfulness.columns
            ]
        ],
        use_container_width=True,
    )


# ---------------------------------------------------------------------------
# Temporal Leakage tab
# ---------------------------------------------------------------------------


_LEAKAGE_SEVERITY_BANNERS = {
    "ok": (COLOR_OK, "✅ OK — no temporal leakage detected"),
    "warning": (COLOR_WARNING, "⚠ Warning — 1–3 temporal leakage rows"),
    "critical": (COLOR_CRITICAL, "🚨 Critical — more than 3 temporal leakage rows"),
}


def render_temporal_leakage_tab(filtered_leakage: pd.DataFrame) -> None:
    """Render the Temporal Leakage tab content."""
    st.subheader("Temporal Leakage")
    count = int(temporal_leakage_count(leakage_df=filtered_leakage))
    severity = leakage_severity(count)
    color, message = _LEAKAGE_SEVERITY_BANNERS[severity]
    st.markdown(
        f"<div style='padding:0.6em 1em;border-radius:6px;background:{color}22;"
        f"border-left:6px solid {color};font-weight:600'>{message}</div>",
        unsafe_allow_html=True,
    )
    if severity == "ok":
        st.info(
            "All cited evidence has news_time <= forecast_time. "
            "The Temporal Retriever has rejected any future news."
        )
        return

    view = filtered_leakage.copy()
    if severity == "critical" and "leakage_minutes" in view.columns:
        view = view.sort_values("leakage_minutes", ascending=False)
    elif "sample_id" in view.columns:
        view = view.sort_values("sample_id", ascending=True)
    st.dataframe(view, use_container_width=True)


# ---------------------------------------------------------------------------
# Case Detail tab
# ---------------------------------------------------------------------------


def render_case_detail_tab(
    data: DashboardData,
    filters: Mapping[str, Any],
) -> None:
    """Render the Case Detail tab content."""
    st.subheader("Case Detail")
    if data.predictions is None or data.predictions.empty:
        st.info("No predictions available to inspect.")
        return

    pool = data.predictions
    if "sample_id" in pool.columns:
        sample_ids = pool["sample_id"].dropna().astype(str).tolist()
    else:
        sample_ids = []
    if not sample_ids:
        st.info("No sample_id values found.")
        return

    selected = st.selectbox("Sample ID", options=sample_ids, key="case-detail-sample")

    rows = pool[pool["sample_id"].astype(str) == str(selected)]
    if rows.empty:
        st.warning(f"Sample {selected!r} not found.")
        return
    row = rows.iloc[0]

    cols = st.columns(4)
    cols[0].metric("Ticker", str(row.get("ticker", "")))
    cols[1].metric("Forecast time", str(row.get("forecast_time", "")))
    cols[2].metric("Label", str(row.get("label", "—")))
    cols[3].metric("Prediction", str(row.get("prediction", "—")))

    cols = st.columns(2)
    cols[0].metric(
        "Original confidence",
        f"{float(row.get('confidence', 0.0)):.0%}",
    )

    faith_row: Optional[pd.Series] = None
    if data.faithfulness is not None and not data.faithfulness.empty:
        f_match = data.faithfulness[
            data.faithfulness["sample_id"].astype(str) == str(selected)
        ]
        if not f_match.empty:
            faith_row = f_match.iloc[0]
    if faith_row is not None:
        cols[1].metric(
            "Confidence after removal",
            f"{float(faith_row.get('confidence_without_cited_evidence', 0.0)):.0%}",
        )
        drop = float(faith_row.get("confidence_drop", 0.0))
        level = classify_faithfulness_level(drop)
        st.metric("Confidence drop", f"{drop:.0%}", delta=level)
    else:
        cols[1].metric("Confidence after removal", "n/a")

    # Cited evidence sub-table.
    st.markdown("**Cited evidence**")
    if data.evidence is not None and not data.evidence.empty:
        cited = data.evidence[
            (data.evidence["sample_id"].astype(str) == str(selected))
            & (data.evidence["is_cited"].astype(bool))
        ]
        if cited.empty:
            st.info("No cited evidence for this sample.")
        else:
            st.dataframe(cited, use_container_width=True)
    else:
        st.info("No evidence rows in the dashboard.")

    # Interpretation.
    if faith_row is not None:
        drop = float(faith_row.get("confidence_drop", 0.0))
        level = classify_faithfulness_level(drop)
        if drop >= 0.20:
            supportive = "supportive of the prediction"
        elif drop >= 0.05:
            supportive = "partially supportive of the prediction"
        else:
            supportive = "decorative — removing it barely changes the result"
        st.markdown(
            CASE_DETAIL_TEMPLATE.format(
                prediction=str(row.get("prediction", "—")),
                original_confidence=float(row.get("confidence", 0.0)),
                confidence_after_removal=float(
                    faith_row.get("confidence_without_cited_evidence", 0.0)
                ),
                confidence_drop=drop,
                faithfulness_level=level,
                supportive_phrase=supportive,
            )
        )


__all__ = [
    "CASE_DETAIL_TEMPLATE",
    "render_sidebar",
    "render_overview_tab",
    "render_evidence_tab",
    "render_confidence_drop_tab",
    "render_temporal_leakage_tab",
    "render_case_detail_tab",
]