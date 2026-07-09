"""Streamlit entry point for the Visualization Dashboard.

Run from the repository root::

    streamlit run src/dashboard/app.py

The app loads the four upstream CSVs via
:func:`src.dashboard.data_loader.load_dashboard_data`, renders the
sidebar, and routes the filtered DataFrames to the five tab renderers
in :mod:`src.dashboard.components`.

The app **never mutates** files under ``outputs/`` and **never calls**
the Forecast Model, Faithfulness Evaluator, or any LLM / network
service. It is read-only with respect to upstream artifacts.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

# Ensure the project root is on sys.path so ``from src...`` resolves when
# Streamlit runs this file directly (Streamlit does not auto-add it the
# way pytest + conftest.py does). PROJECT_ROOT is the repo root, i.e. the
# parent of the ``src/`` package.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st

from src.dashboard.components import (
    render_agentic_sdlc_tab,
    render_case_detail_tab,
    render_confidence_drop_tab,
    render_evidence_tab,
    render_market_tab,
    render_overview_tab,
    render_sufficiency_tab,
    render_temporal_leakage_tab,
    render_sidebar,
)
from src.dashboard.data_loader import load_dashboard_data
from src.dashboard.metrics import apply_filters
from src.dashboard.validators import DashboardDataError, assert_dashboard_data


#: Default location of the upstream CSV outputs.
DEFAULT_OUTPUT_DIR: str = "outputs"

#: Tab labels, with icons, in display order. Kept as one tuple so the
#: label <-> renderer pairing in ``main()`` cannot drift apart silently.
_TAB_LABELS = (
    "📊 Overview",
    "🧾 Evidence",
    "📉 Confidence Drop",
    "⏱️ Temporal Leakage",
    "🔎 Case Detail",
    "🧪 Sufficiency",
    "📈 Market Consistency",
    "🤖 Agentic SDLC",
)

#: Custom CSS layer. Pure Streamlit feature (``st.markdown`` +
#: ``unsafe_allow_html``) — no new dependency. Base corner-radius and
#: color theme come from ``.streamlit/config.toml``; this stylesheet
#: only adds what the native theme config cannot express (card
#: elevation, hover states, the hero panel, badge pills).
_CUSTOM_CSS = """
<style>
/* Metric cards: soft elevation + hover lift */
[data-testid="stMetric"] {
    background: white;
    padding: 0.9rem 1.1rem;
    border-radius: 1rem;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.08), 0 1px 2px rgba(15, 23, 42, 0.04);
    border: 1px solid rgba(15, 23, 42, 0.06);
    transition: box-shadow 0.15s ease, transform 0.15s ease;
}
[data-testid="stMetric"]:hover {
    box-shadow: 0 6px 16px rgba(15, 23, 42, 0.10);
    transform: translateY(-2px);
}
[data-testid="stMetricLabel"] { font-weight: 600; opacity: 0.75; }

/* Buttons: friendly hover lift, bolder label */
.stButton > button,
.stDownloadButton > button,
[data-testid="stFormSubmitButton"] button {
    font-weight: 600;
    transition: box-shadow 0.15s ease, transform 0.1s ease;
}
.stButton > button:hover,
.stDownloadButton > button:hover,
[data-testid="stFormSubmitButton"] button:hover {
    box-shadow: 0 4px 12px rgba(31, 119, 180, 0.28);
    transform: translateY(-1px);
}

/* Bordered containers (card groupings) get a matching soft shadow */
[data-testid="stVerticalBlockBorderWrapper"] {
    box-shadow: 0 1px 4px rgba(15, 23, 42, 0.06);
}

/* Tabs: more breathing room, bold active label */
button[data-baseweb="tab"] { font-weight: 600; }

/* Hero / welcome panel shown before the first filter is applied */
.hero-card {
    background: linear-gradient(135deg, #eaf3fb 0%, #f7f9fc 100%);
    border-radius: 1.25rem;
    padding: 2rem 2.2rem;
    border: 1px solid rgba(31, 119, 180, 0.14);
    margin-bottom: 1rem;
}
.hero-card h3 { margin-top: 0; }

/* Small pill badges used in the header and status banners */
.badge {
    display: inline-block;
    padding: 0.22rem 0.75rem;
    border-radius: 999px;
    background: rgba(31, 119, 180, 0.10);
    color: #1f77b4;
    font-size: 0.82rem;
    font-weight: 600;
    margin: 0 0.35rem 0.35rem 0;
}
</style>
"""


def _inject_theme() -> None:
    st.markdown(_CUSTOM_CSS, unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def _load_cached(output_dir: str):
    """Cache the load keyed on the output directory string."""
    return load_dashboard_data(output_dir)


def _banner_for_missing(data) -> None:
    if data.missing_files:
        st.warning(
            "The following expected files were not found and have been "
            "synthesized or marked empty: " + ", ".join(data.missing_files)
        )
    if data.empty_files:
        st.info(
            "The following files are present but empty: "
            + ", ".join(data.empty_files)
        )


def _render_header(data) -> None:
    st.title("📈 Faithful Evidence-Centric Forecasting")
    st.caption(
        "Academic visualization, not a trading tool. "
        "Read-only with respect to upstream artifacts."
    )
    n_predictions = 0 if data.predictions is None else len(data.predictions)
    n_tickers = (
        data.predictions["ticker"].nunique()
        if data.predictions is not None and "ticker" in data.predictions.columns
        else 0
    )
    st.markdown(
        f"<span class='badge'>🗂️ {n_predictions} forecasts</span>"
        f"<span class='badge'>🏷️ {n_tickers} tickers</span>"
        f"<span class='badge'>🔒 read-only</span>",
        unsafe_allow_html=True,
    )


def _render_welcome_panel(data) -> None:
    """Shown before the user has applied any filters — an inviting,
    data-light landing state rather than dumping every tab at once.
    """
    st.markdown(
        "<div class='hero-card'>"
        "<h3>👋 Chọn bộ lọc rồi bấm <b>Áp dụng bộ lọc</b> để bắt đầu</h3>"
        "<p>Dùng thanh bên trái để chọn ticker, khoảng ngày dự báo, "
        "faithfulness level, v.v. Dữ liệu chi tiết (bảng, biểu đồ, case "
        "detail) chỉ hiển thị sau khi bạn áp dụng bộ lọc — giúp dashboard "
        "gọn và nhanh hơn khi dữ liệu lớn.</p>"
        "</div>",
        unsafe_allow_html=True,
    )
    cols = st.columns(3)
    cols[0].metric(
        "Total forecasts", 0 if data.predictions is None else len(data.predictions)
    )
    cols[1].metric(
        "Evidence rows", 0 if data.evidence is None else len(data.evidence)
    )
    cols[2].metric(
        "Temporal leakage rows", 0 if data.leakage is None else len(data.leakage)
    )


def main(output_dir: Optional[str] = None) -> None:
    """Streamlit entry point."""
    st.set_page_config(
        page_title="Faithfulness Dashboard",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _inject_theme()

    target = output_dir or DEFAULT_OUTPUT_DIR
    if not Path(target).exists():
        st.error(f"Output directory {target!r} does not exist.")
        return

    data = _load_cached(target)
    _render_header(data)
    _banner_for_missing(data)
    try:
        assert_dashboard_data(data)
    except DashboardDataError as exc:
        st.error(f"Schema validation failed: {exc}")
        return

    filters, applied = render_sidebar(data)

    if not applied:
        _render_welcome_panel(data)
        return

    fp = apply_filters(data.predictions, filters, frame_kind="predictions")
    fe = apply_filters(data.evidence, filters, frame_kind="evidence")
    ff = apply_filters(data.faithfulness, filters, frame_kind="faithfulness")
    fl = apply_filters(data.leakage, filters, frame_kind="leakage")

    tabs = st.tabs(list(_TAB_LABELS))
    with tabs[0]:
        render_overview_tab(data, fp, fe, ff, fl)
    with tabs[1]:
        render_evidence_tab(fe, fp)
    with tabs[2]:
        render_confidence_drop_tab(ff)
    with tabs[3]:
        render_temporal_leakage_tab(fl)
    with tabs[4]:
        render_case_detail_tab(data, filters)
    with tabs[5]:
        render_sufficiency_tab(data.sufficiency)
    with tabs[6]:
        render_market_tab(data.market)
    with tabs[7]:
        render_agentic_sdlc_tab(data.agent_trace)


if __name__ == "__main__":
    main()
