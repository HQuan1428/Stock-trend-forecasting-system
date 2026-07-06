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


_FILTERS_STATE_KEY = "dashboard_filters"
_FILTERS_APPLIED_KEY = "dashboard_filters_applied"


def render_sidebar(data: DashboardData) -> Tuple[Dict[str, Any], bool]:
    """Render the sidebar filters as an on-demand form and return the
    currently *applied* filter state.

    The filters live inside a single ``st.form`` — changing a widget no
    longer reruns the app or refilters the tabs on every click. Nothing
    downstream recomputes until the user presses **Apply filters** (or
    **Reset**), which is what keeps the main area from dumping every
    table/chart on first load.

    Returns:
        A ``(filters, applied)`` tuple. ``filters`` has the same keys as
        before (``tickers``, ``predictions``, ``faithfulness_levels``,
        ``date_range``, ``cited_only``, ``leakage_only``); it reflects
        the *last applied* selection, not necessarily the widgets'
        current on-screen state. ``applied`` is ``False`` until the user
        has pressed Apply (or Reset) at least once in this session —
        callers should show a lightweight welcome state instead of the
        full tab layout while it is ``False``.
    """
    st.sidebar.header("🔍 Filters")

    # Tickers: union of available tickers across the four frames.
    tickers_pool = sorted(
        set(
            _unique_values(data.predictions, "ticker")
            + _unique_values(data.evidence, "ticker")
            + _unique_values(data.faithfulness, "ticker")
            + _unique_values(data.leakage, "ticker")
        )
    )
    # Predictions: union of available predictions across predictions + faithfulness.
    preds_pool = sorted(
        set(
            _unique_values(data.predictions, "prediction")
            + _unique_values(data.faithfulness, "prediction")
        )
        or list(VALID_PREDICTIONS)
    )

    # Forecast date range bounds.
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
    bounds_start = dates[0] if dates else today
    bounds_end = dates[-1] if dates else today

    default_filters: Dict[str, Any] = {
        "tickers": tickers_pool,
        "predictions": preds_pool,
        "faithfulness_levels": list(FAITHFULNESS_LEVELS),
        "date_range": (bounds_start, bounds_end),
        "cited_only": False,
        "leakage_only": False,
    }
    last_applied: Dict[str, Any] = st.session_state.get(_FILTERS_STATE_KEY, default_filters)

    # Seed widget defaults from the last-applied selection, guarding
    # against stale values that no longer exist in the current pool
    # (e.g. the output directory changed between runs).
    def _safe_default(values: Any, pool: List[str]) -> List[str]:
        if not isinstance(values, (list, tuple)):
            return pool
        kept = [v for v in values if v in pool]
        return kept or pool

    with st.sidebar.form("filters_form", border=False):
        selected_tickers = st.multiselect(
            "Ticker",
            options=tickers_pool,
            default=_safe_default(last_applied.get("tickers"), tickers_pool),
            help="Filter to one or more tickers.",
        )
        selected_predictions = st.multiselect(
            "Prediction",
            options=preds_pool,
            default=_safe_default(last_applied.get("predictions"), preds_pool),
        )
        selected_levels = st.multiselect(
            "Faithfulness level",
            options=list(FAITHFULNESS_LEVELS),
            default=_safe_default(
                last_applied.get("faithfulness_levels"), list(FAITHFULNESS_LEVELS)
            ),
        )
        date_range = st.date_input(
            "Forecast date range",
            value=last_applied.get("date_range") or (bounds_start, bounds_end),
            min_value=bounds_start if dates else None,
            max_value=bounds_end if dates else None,
        )
        cited_only = st.toggle(
            "Show only cited evidence",
            value=bool(last_applied.get("cited_only", False)),
            help="Restrict the Evidence tab to rows where is_cited == True.",
        )
        leakage_only = st.toggle(
            "Show only temporal leakage cases",
            value=bool(last_applied.get("leakage_only", False)),
            help="Restrict the Temporal Leakage tab to rows where news_time > forecast_time.",
        )

        col_apply, col_reset = st.columns(2)
        submitted = col_apply.form_submit_button(
            "✅ Apply filters", width="stretch", type="primary"
        )
        reset = col_reset.form_submit_button("↺ Reset", width="stretch")

    if reset:
        st.session_state[_FILTERS_STATE_KEY] = default_filters
        st.session_state[_FILTERS_APPLIED_KEY] = True
    elif submitted:
        if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
            start, end = date_range
        else:
            start = end = None
        st.session_state[_FILTERS_STATE_KEY] = {
            "tickers": selected_tickers,
            "predictions": selected_predictions,
            "faithfulness_levels": selected_levels,
            "date_range": (start, end),
            "cited_only": cited_only,
            "leakage_only": leakage_only,
        }
        st.session_state[_FILTERS_APPLIED_KEY] = True

    applied = bool(st.session_state.get(_FILTERS_APPLIED_KEY, False))
    filters = st.session_state.get(_FILTERS_STATE_KEY, default_filters)
    if applied:
        st.sidebar.caption("Filters applied. Adjust and press Apply to refresh.")
    return filters, applied


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
    st.subheader("📊 Overview")

    with st.container(border=True):
        cols = st.columns(4)
        cols[0].metric(
            "🗂️ Total forecasts",
            int(len(filtered_predictions)) if filtered_predictions is not None else 0,
        )
        acc = accuracy(filtered_predictions)
        cols[1].metric(
            "🎯 Accuracy",
            f"{acc:.0%}" if acc is not None else "n/a",
        )
        cols[2].metric(
            "💧 Avg confidence",
            f"{average_confidence(filtered_predictions):.0%}",
        )
        cols[3].metric(
            "📉 Avg confidence drop",
            f"{average_confidence_drop(filtered_faithfulness):.0%}",
        )

        cols = st.columns(3)
        cols[0].metric(
            "⏱️ Temporal leakage rows",
            int(temporal_leakage_count(leakage_df=filtered_leakage)),
        )
        cols[1].metric(
            "✅ Avg temporal validity",
            f"{average_temporal_validity(filtered_faithfulness):.0%}",
        )
        counts = prediction_distribution(filtered_predictions)
        cols[2].metric(
            "😐 HOLD share",
            f"{counts['HOLD'] / max(1, sum(counts.values())):.0%}",
        )

    st.plotly_chart(
        build_prediction_distribution_chart(filtered_predictions),
        width="stretch",
        key="chart-prediction-distribution",
    )

    if filtered_faithfulness is not None and not filtered_faithfulness.empty:
        acc_df = accuracy_by_ticker(filtered_faithfulness)
        st.subheader("🏷️ Accuracy by ticker")
        st.plotly_chart(
            build_accuracy_by_ticker_chart(acc_df),
            width="stretch",
            key="chart-accuracy-by-ticker",
        )
        with st.expander("📄 View accuracy-by-ticker table", expanded=False):
            st.dataframe(acc_df, width="stretch")


# ---------------------------------------------------------------------------
# Evidence tab
# ---------------------------------------------------------------------------


def render_evidence_tab(
    filtered_evidence: pd.DataFrame,
    filtered_predictions: Optional[pd.DataFrame] = None,
) -> None:
    """Render the Evidence tab content.

    ``filtered_predictions`` is used to look up the per-group
    ``prediction`` value so the evidence table can show which prediction
    each evidence item is tied to. The join is by ``sample_id``.
    """
    st.subheader("🧾 Evidence")
    if filtered_evidence is None or filtered_evidence.empty:
        st.info("No evidence rows match the current filters.")
        return

    view = filtered_evidence.copy()
    if (
        filtered_predictions is not None
        and not filtered_predictions.empty
        and "sample_id" in filtered_predictions.columns
        and "prediction" in filtered_predictions.columns
        and "sample_id" in view.columns
    ):
        view = view.merge(
            filtered_predictions[["sample_id", "prediction"]].drop_duplicates(
                subset=["sample_id"]
            ),
            on="sample_id",
            how="left",
        )
    if "prediction" not in view.columns:
        view["prediction"] = ""
    view["is_cited_display"] = view["is_cited"].apply(
        lambda v: "✓ cited" if bool(v) else "—"
    )
    view["temporal_display"] = view["is_temporally_valid"].apply(
        lambda v: "✓ valid" if bool(v) else "⚠ temporal leakage"
    )

    search = st.text_input(
        "🔎 Search evidence text",
        value="",
        placeholder="e.g. lawsuit, guidance, recall...",
        help="Client-side filter on the evidence_text column.",
    )
    display_columns = [
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
    table = view[display_columns]
    if search.strip():
        table = table[
            table["evidence_text"].astype(str).str.contains(search, case=False, na=False)
        ]

    with st.expander(f"📄 View evidence table ({len(table)} rows)", expanded=False):
        st.dataframe(table, width="stretch")
        st.download_button(
            "⬇️ Download as CSV",
            data=table.to_csv(index=False).encode("utf-8"),
            file_name="evidence_filtered.csv",
            mime="text/csv",
        )


# ---------------------------------------------------------------------------
# Confidence Drop tab
# ---------------------------------------------------------------------------


def render_confidence_drop_tab(filtered_faithfulness: pd.DataFrame) -> None:
    """Render the Confidence Drop tab content."""
    st.subheader("📉 Confidence Drop Analysis")
    if filtered_faithfulness is None or filtered_faithfulness.empty:
        st.info("No faithfulness rows match the current filters.")
        return

    st.plotly_chart(
        build_confidence_drop_chart(filtered_faithfulness),
        width="stretch",
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

    with st.container(border=True):
        cols = st.columns(3)
        cols[0].metric("🟢 High faithfulness", bucket_counts.get("high", 0))
        cols[1].metric("🟡 Medium faithfulness", bucket_counts.get("medium", 0))
        cols[2].metric("🔴 Low faithfulness", bucket_counts.get("low", 0))

    table = filtered_faithfulness[
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
    ]
    with st.expander(f"📄 View faithfulness table ({len(table)} rows)", expanded=False):
        st.dataframe(table, width="stretch")
        st.download_button(
            "⬇️ Download as CSV",
            data=table.to_csv(index=False).encode("utf-8"),
            file_name="faithfulness_filtered.csv",
            mime="text/csv",
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
    st.subheader("⏱️ Temporal Leakage")
    count = int(temporal_leakage_count(leakage_df=filtered_leakage))
    severity = leakage_severity(count)
    color, message = _LEAKAGE_SEVERITY_BANNERS[severity]
    st.markdown(
        f"<div style='padding:0.9em 1.2em;border-radius:1rem;background:{color}1a;"
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

    with st.expander(f"📄 View leakage table ({len(view)} rows)", expanded=True):
        st.dataframe(view, width="stretch")
        st.download_button(
            "⬇️ Download as CSV",
            data=view.to_csv(index=False).encode("utf-8"),
            file_name="temporal_leakage_filtered.csv",
            mime="text/csv",
        )


# ---------------------------------------------------------------------------
# Case Detail tab
# ---------------------------------------------------------------------------


def render_case_detail_tab(
    data: DashboardData,
    filters: Mapping[str, Any],
) -> None:
    """Render the Case Detail tab content."""
    st.subheader("🔎 Case Detail")
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

    selected = st.selectbox(
        "Sample ID",
        options=sample_ids,
        key="case-detail-sample",
        help="Start typing to search.",
    )

    rows = pool[pool["sample_id"].astype(str) == str(selected)]
    if rows.empty:
        st.warning(f"Sample {selected!r} not found.")
        return
    row = rows.iloc[0]

    with st.container(border=True):
        cols = st.columns(4)
        cols[0].metric("🏷️ Ticker", str(row.get("ticker", "")))
        cols[1].metric("🗓️ Forecast time", str(row.get("forecast_time", "")))
        cols[2].metric("🏁 Label", str(row.get("label", "—")))
        cols[3].metric("🔮 Prediction", str(row.get("prediction", "—")))

        cols = st.columns(3)
        cols[0].metric(
            "💧 Original confidence",
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
                "💧 Confidence after removal",
                f"{float(faith_row.get('confidence_without_cited_evidence', 0.0)):.0%}",
            )
            drop = float(faith_row.get("confidence_drop", 0.0))
            level = classify_faithfulness_level(drop)
            cols[2].metric("📉 Confidence drop", f"{drop:.0%}", delta=level)
        else:
            cols[1].metric("💧 Confidence after removal", "n/a")

    # Cited evidence sub-table.
    if data.evidence is not None and not data.evidence.empty:
        cited = data.evidence[
            (data.evidence["sample_id"].astype(str) == str(selected))
            & (data.evidence["is_cited"].astype(bool))
        ]
        with st.expander(f"🧾 Cited evidence ({len(cited)} rows)", expanded=True):
            if cited.empty:
                st.info("No cited evidence for this sample.")
            else:
                st.dataframe(cited, width="stretch")
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
        st.markdown("**🧠 Interpretation**")
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


def render_agentic_sdlc_tab(agent_trace: list) -> None:
    """Render the Agentic SDLC tab.

    Displays quality gate pass rate, human acceptance rate, per-role counts,
    a trace log table, and a static reflection section.
    Gracefully handles an empty trace without raising.
    """
    from src.agent_trace import summarize_trace

    if not agent_trace:
        st.info(
            "No agent trace log found. "
            "Expected at outputs/run_log.json — seed it by running the pipeline once."
        )
        return

    summary = summarize_trace(agent_trace)
    total = summary["total"]
    pass_rate = summary["pass_rate"]
    acceptance_rate = summary["human_accepted"] / total if total > 0 else 0.0

    cols = st.columns(3)
    cols[0].metric("Total Agent Runs", total)
    cols[1].metric("Quality Gate Pass Rate", f"{pass_rate:.0%}")
    cols[2].metric("Human Acceptance Rate", f"{acceptance_rate:.0%}")

    st.subheader("Runs by Agent Role")
    roles_df = pd.DataFrame(
        [{"agent_role": role, "count": cnt} for role, cnt in summary["roles"].items()]
    )
    st.dataframe(roles_df, use_container_width=True)

    st.subheader("Full Trace Log")
    display_cols = ["run_id", "agent_role", "task", "human_review", "quality_gate"]
    trace_df = pd.DataFrame(agent_trace)
    show_cols = [c for c in display_cols if c in trace_df.columns]
    st.dataframe(trace_df[show_cols], use_container_width=True)

    with st.expander("Reflection: Human-AI Collaboration Model", expanded=False):
        st.markdown(
            """
**3 Agent Roles trong dự án:**

1. **Research Agent** — Phân tích gap, viết OpenSpec (proposal + design + spec) trước mỗi change.
2. **Coding Agent** — Implement module theo spec đã được human approve; không code trước khi có spec.
3. **Testing/Review Agent** — Viết test từ spec scenarios, verify output, báo cáo edge cases.

**Human Control Points:**
- User review proposal.md + design.md → approve trước khi `/opsx:apply`
- `pytest` gate: toàn bộ test suite phải green sau mỗi change (483 → 497 → 535 tests)
- Pipeline gate: `python -m src.pipeline` không lỗi, output CSV đúng schema
- User inspect output CSV để confirm giá trị hợp lệ

**Bài học:**
Spec trước, code sau — decisions về threshold (±0.005, ±0.02) nằm trong design.md,
không bị baked vào code mà không có lý do. Human-in-the-loop tại spec level hiệu quả
hơn review code sau khi đã viết xong.
"""
        )


def render_market_tab(market_df: Optional[pd.DataFrame]) -> None:
    """Render the Market Consistency tab.

    Shows overall consistency rate and per-regime breakdown as metric cards,
    then a full table of per-sample results.
    Gracefully handles ``None`` or empty input without raising.
    """
    if market_df is None or (hasattr(market_df, "empty") and market_df.empty):
        st.info(
            "Market consistency results not available. "
            "Run the pipeline first to generate market_consistency_results.csv. "
            "(Note: market data is synthetic / simulated.)"
        )
        return

    overall_rate = 0.0
    n_samples = len(market_df)
    if "market_consistent" in market_df.columns:
        overall_rate = float(
            pd.to_numeric(market_df["market_consistent"], errors="coerce")
            .fillna(0.0)
            .mean()
        )

    cols = st.columns(2)
    cols[0].metric("Market Consistency Rate", f"{overall_rate:.0%}")
    cols[1].metric("Samples", n_samples)

    if "regime" in market_df.columns and "market_consistency_score" in market_df.columns:
        st.subheader("Accuracy by Regime")
        regime_stats = (
            market_df.groupby("regime")["market_consistency_score"]
            .agg(["mean", "count"])
            .rename(columns={"mean": "consistency_rate", "count": "n"})
            .reset_index()
        )
        regime_stats["consistency_rate"] = regime_stats["consistency_rate"].map(
            lambda x: f"{x:.0%}"
        )
        st.dataframe(regime_stats, use_container_width=True)

    display_cols = [
        c for c in (
            "sample_id", "ticker", "forecast_time", "prediction",
            "next_day_return", "market_consistent", "regime",
            "market_consistency_score",
        )
        if c in market_df.columns
    ]
    st.subheader("Per-Sample Results (synthetic market data)")
    st.dataframe(market_df[display_cols], use_container_width=True)


def render_sufficiency_tab(sufficiency_df: Optional[pd.DataFrame]) -> None:
    """Render the Sufficiency & Counterfactual tab.

    Shows avg sufficiency_score and avg counterfactual_delta as metric
    cards, then a full table of per-sample results.
    Gracefully handles ``None`` or empty input without raising.
    """
    if sufficiency_df is None or (hasattr(sufficiency_df, "empty") and sufficiency_df.empty):
        st.info("Sufficiency results not available. Run the pipeline first to generate sufficiency_results.csv.")
        return

    avg_suff = 0.0
    avg_cf = 0.0
    if "sufficiency_score" in sufficiency_df.columns:
        avg_suff = float(
            pd.to_numeric(sufficiency_df["sufficiency_score"], errors="coerce")
            .fillna(0.0)
            .mean()
        )
    if "counterfactual_delta" in sufficiency_df.columns:
        avg_cf = float(
            pd.to_numeric(sufficiency_df["counterfactual_delta"], errors="coerce")
            .fillna(0.0)
            .mean()
        )

    cols = st.columns(2)
    cols[0].metric("Avg Sufficiency Score", f"{avg_suff:.0%}")
    cols[1].metric("Avg Counterfactual Delta", f"{avg_cf:.2f}")

    display_cols = [
        c for c in (
            "sample_id", "ticker", "prediction", "original_confidence",
            "sufficiency_confidence", "sufficiency_score",
            "prediction_on_only_cited", "counterfactual_confidence",
            "counterfactual_delta",
        )
        if c in sufficiency_df.columns
    ]
    st.dataframe(sufficiency_df[display_cols], use_container_width=True)


__all__ = [
    "CASE_DETAIL_TEMPLATE",
    "render_sidebar",
    "render_overview_tab",
    "render_evidence_tab",
    "render_confidence_drop_tab",
    "render_temporal_leakage_tab",
    "render_case_detail_tab",
    "render_sufficiency_tab",
    "render_market_tab",
    "render_agentic_sdlc_tab",
]