"""Reusable Streamlit UI blocks for the dashboard.

Thin render layer only — every number shown here is computed by
``metrics``/``data_loader``. The ``_BANNER_FN`` indirection maps the
banner kinds produced by ``metrics`` onto Streamlit calls.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from src.dashboard import metrics

_BANNER_FN = {
    "success": st.success,
    "warning": st.warning,
    "error": st.error,
}


def banner(kind: str, message: str) -> None:
    _BANNER_FN.get(kind, st.warning)(message)


def metric_row(items: Dict[str, str]) -> None:
    """One st.metric per (label, value) pair, on a single row."""
    cols = st.columns(len(items))
    for col, (label, value) in zip(cols, items.items()):
        col.metric(label, value)


def leakage_warning(invalid_future_news: List[Dict[str, Any]], forecast_time: str) -> None:
    """§4.2: warn when a sample carries future-dated news."""
    from src.export_csv import compute_leakage_minutes

    if not invalid_future_news:
        return
    lines = [
        f"- `{n['news_id']}` @ {n['news_time']} "
        f"(+{compute_leakage_minutes(str(n['news_time']), forecast_time)} phút "
        f"sau thời điểm dự báo)"
        for n in invalid_future_news
    ]
    st.error(
        f"**{len(invalid_future_news)} tin tương lai đã bị loại** "
        "(news_time > forecast_time):\n" + "\n".join(lines)
    )


def evidence_list(title: str, items: List[Dict[str, Any]]) -> None:
    """Cited evidence with publication time (§4.2)."""
    st.markdown(f"**{title}**")
    if not items:
        st.caption("(không có)")
        return
    for ev in items:
        direction = ev.get("expected_direction", "?")
        st.markdown(
            f"- “{ev.get('evidence_text', '')}” — hướng **{direction}**, "
            f"xuất bản {ev.get('news_time', '?')}"
        )


def verdict_banner(verdict: str) -> None:
    kind, message = metrics.verdict_banner(verdict)
    banner(kind, message)


def confidence_comparison(report: Dict[str, Any]) -> None:
    """Live Demo: before/after ablation, from precomputed faithfulness."""
    before = float(report["original_confidence"])
    after = float(report["confidence_after_removal"])
    drop = float(report["confidence_drop"])
    cols = st.columns(3)
    cols[0].metric("Confidence gốc", f"{before:.2f}")
    cols[1].metric(
        "Sau khi bỏ cited evidence", f"{after:.2f}", delta=f"{-drop:+.2f}"
    )
    cols[2].metric(
        "Prediction sau ablation", str(report["prediction_after_removal"])
    )


def filterable_evidence_table(evidence: pd.DataFrame) -> None:
    """A7: the dataset-wide evidence table with ticker/role/cited filters."""
    cols = st.columns(3)
    tickers = sorted(evidence["ticker"].unique().tolist())
    roles = ["pro", "counter", "neutral"]
    pick_tickers = cols[0].multiselect("Ticker", tickers, default=[])
    pick_roles = cols[1].multiselect("Role", roles, default=[])
    cited_only = cols[2].checkbox("Chỉ evidence được cite")

    view = evidence
    if pick_tickers:
        view = view[view["ticker"].isin(pick_tickers)]
    if pick_roles:
        view = view[view["evidence_role"].isin(pick_roles)]
    if cited_only:
        view = view[view["is_cited"]]
    st.dataframe(view, width="stretch", hide_index=True)
    st.caption(f"{len(view)} evidence")


__all__ = [
    "banner",
    "confidence_comparison",
    "evidence_list",
    "filterable_evidence_table",
    "leakage_warning",
    "metric_row",
    "verdict_banner",
]