"""End-to-end smoke tests for the Streamlit dashboard, via Streamlit's
native ``AppTest`` framework (``streamlit.testing.v1``).

This runs the real ``src/dashboard/app.py`` script headlessly (no
browser, no server socket) and inspects the resulting element tree —
this is a first-party Streamlit testing API, not a new dependency.

These tests exercise exactly the "data only appears on request" flow:
the app must start in a welcome state with no tabs, and only render the
eight tabs after the sidebar form's Apply button is clicked.
"""

from __future__ import annotations

import pathlib

import pytest

pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP_PATH = str(
    pathlib.Path(__file__).resolve().parents[1] / "src" / "dashboard" / "app.py"
)


def _fresh_app() -> AppTest:
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=60)
    return at


def _apply_button(at: AppTest):
    return next(b for b in at.button if "Apply" in (b.label or ""))


def test_initial_load_shows_welcome_state_with_no_tabs() -> None:
    """Before any filter is applied, the dashboard must not dump every
    tab/table at once — only a lightweight welcome panel."""
    at = _fresh_app()
    assert not at.exception
    assert len(at.tabs) == 0
    assert len(at.metric) == 3  # welcome panel's 3 summary metrics


def test_apply_filters_reveals_all_eight_tabs() -> None:
    at = _fresh_app()
    _apply_button(at).click().run(timeout=60)
    assert not at.exception
    assert len(at.tabs) == 8


def test_narrowing_ticker_filter_and_reapplying_does_not_raise() -> None:
    at = _fresh_app()
    _apply_button(at).click().run(timeout=60)
    ticker_filter = at.multiselect[0]
    if len(ticker_filter.value) > 1:
        ticker_filter.set_value([ticker_filter.value[0]])
    _apply_button(at).click().run(timeout=60)
    assert not at.exception
    assert len(at.tabs) == 8


def test_evidence_search_box_does_not_raise() -> None:
    at = _fresh_app()
    _apply_button(at).click().run(timeout=60)
    search_boxes = [t for t in at.text_input if "Search" in (t.label or "")]
    assert search_boxes, "expected an evidence search text_input"
    search_boxes[0].set_value("guidance").run(timeout=60)
    assert not at.exception


def test_case_detail_sample_selection_does_not_raise() -> None:
    at = _fresh_app()
    _apply_button(at).click().run(timeout=60)
    sample_select = next(s for s in at.selectbox if s.label == "Sample ID")
    if len(sample_select.options) > 1:
        sample_select.set_value(sample_select.options[1]).run(timeout=60)
    assert not at.exception


def test_reset_button_returns_to_full_unfiltered_view() -> None:
    at = _fresh_app()
    _apply_button(at).click().run(timeout=60)
    reset_btn = next(b for b in at.button if "Reset" in (b.label or ""))
    reset_btn.click().run(timeout=60)
    assert not at.exception
    assert len(at.tabs) == 8
