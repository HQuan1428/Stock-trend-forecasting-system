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
    render_case_detail_tab,
    render_confidence_drop_tab,
    render_evidence_tab,
    render_overview_tab,
    render_temporal_leakage_tab,
    render_sidebar,
)
from src.dashboard.data_loader import load_dashboard_data
from src.dashboard.metrics import apply_filters
from src.dashboard.validators import DashboardDataError, assert_dashboard_data


#: Default location of the upstream CSV outputs.
DEFAULT_OUTPUT_DIR: str = "outputs"


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


def main(output_dir: Optional[str] = None) -> None:
    """Streamlit entry point."""
    st.set_page_config(
        page_title="Faithfulness Dashboard",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.title("Faithful Evidence-Centric Forecasting — Dashboard")
    st.caption(
        "Academic visualization, not a trading tool. "
        "Read-only with respect to upstream artifacts."
    )

    target = output_dir or DEFAULT_OUTPUT_DIR
    if not Path(target).exists():
        st.error(f"Output directory {target!r} does not exist.")
        return

    data = _load_cached(target)
    _banner_for_missing(data)
    try:
        assert_dashboard_data(data)
    except DashboardDataError as exc:
        st.error(f"Schema validation failed: {exc}")
        return

    filters = render_sidebar(data)
    fp = apply_filters(data.predictions, filters, frame_kind="predictions")
    fe = apply_filters(data.evidence, filters, frame_kind="evidence")
    ff = apply_filters(data.faithfulness, filters, frame_kind="faithfulness")
    fl = apply_filters(data.leakage, filters, frame_kind="leakage")

    tabs = st.tabs(
        ["Overview", "Evidence", "Confidence Drop", "Temporal Leakage", "Case Detail"]
    )
    with tabs[0]:
        render_overview_tab(data, fp, fe, ff, fl)
    with tabs[1]:
        render_evidence_tab(fe)
    with tabs[2]:
        render_confidence_drop_tab(ff)
    with tabs[3]:
        render_temporal_leakage_tab(fl)
    with tabs[4]:
        render_case_detail_tab(data, filters)


if __name__ == "__main__":
    main()
