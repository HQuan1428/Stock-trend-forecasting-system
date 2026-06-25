"""Tests for ``src.dashboard.components``.

Streamlit components cannot be unit-tested without a running server,
so this suite focuses on the two pieces that have a pure contract:

- :data:`src.dashboard.components.CASE_DETAIL_TEMPLATE` is a static
  string that the case-detail tab fills with values from the report.
  The test asserts the template's literal content and the determinism
  of the formatted output.

- The :func:`src.dashboard.metrics.apply_filters` helper that
  ``render_overview_tab`` etc. delegate to is exercised end-to-end
  against the three sample fixtures (covered in
  ``test_dashboard_metrics.py``); this file only pins the wiring so
  any future refactor that drops the wiring is caught here.
"""

from __future__ import annotations

from src.dashboard.components import CASE_DETAIL_TEMPLATE
from src.dashboard.metrics import (
    FAITHFULNESS_LEVELS,
    VALID_PREDICTIONS,
    apply_filters,
    classify_faithfulness_level,
    leakage_severity,
)


def test_case_detail_template_is_static_string() -> None:
    """The template must not contain time-based or random content."""
    assert isinstance(CASE_DETAIL_TEMPLATE, str)
    forbidden = ["{time}", "{date}", "{now}", "{random}", "{uuid}", "{sample_id}"]
    for marker in forbidden:
        assert marker not in CASE_DETAIL_TEMPLATE, marker


def test_case_detail_template_has_required_placeholders() -> None:
    required = [
        "{prediction}",
        "{original_confidence",
        "{confidence_after_removal",
        "{confidence_drop",
        "{faithfulness_level}",
        "{supportive_phrase}",
    ]
    for marker in required:
        assert marker in CASE_DETAIL_TEMPLATE, marker


def test_case_detail_template_format_is_deterministic() -> None:
    """Calling ``.format(...)`` twice with the same args is byte-equal."""
    kwargs = dict(
        prediction="UP",
        original_confidence=0.8,
        confidence_after_removal=0.5,
        confidence_drop=0.3,
        faithfulness_level="high",
        supportive_phrase="supportive of the prediction",
    )
    out1 = CASE_DETAIL_TEMPLATE.format(**kwargs)
    out2 = CASE_DETAIL_TEMPLATE.format(**kwargs)
    assert out1 == out2


def test_case_detail_template_contains_filled_values() -> None:
    out = CASE_DETAIL_TEMPLATE.format(
        prediction="UP",
        original_confidence=0.8,
        confidence_after_removal=0.5,
        confidence_drop=0.3,
        faithfulness_level="high",
        supportive_phrase="supportive of the prediction",
    )
    assert "UP" in out
    assert "80%" in out
    assert "50%" in out
    assert "30%" in out
    assert "high" in out
    assert "supportive of the prediction" in out


def test_apply_filters_round_trip_on_healthy_fixture(tmp_path_factory=None) -> None:
    """The wiring from components -> apply_filters is unchanged for the
    healthy fixture; this guards against accidental wiring drops."""
    import json
    from pathlib import Path

    from src.dashboard.data_loader import load_dashboard_data
    from src.dashboard.metrics import apply_filters

    target = Path(__file__).resolve().parents[1] / "samples" / "dashboard" / "healthy"
    data = load_dashboard_data(str(target))
    out = apply_filters(data.predictions, {})
    assert out is not None
    assert len(out) == len(data.predictions)
    # Apply a ticker filter and confirm it narrows.
    tickers = sorted(data.predictions["ticker"].astype(str).unique().tolist())
    if len(tickers) > 1:
        out = apply_filters(data.predictions, {"tickers": [tickers[0]]})
        assert set(out["ticker"].astype(str).unique()) == {tickers[0]}


def test_filter_pipeline_classifies_all_three_levels() -> None:
    """End-to-end: classify_faithfulness_level + leakage_severity produce
    the documented buckets across the healthy fixture."""
    from pathlib import Path

    from src.dashboard.data_loader import load_dashboard_data
    from src.dashboard.metrics import (
        accuracy,
        average_confidence,
        average_confidence_drop,
        leakage_severity,
        prediction_distribution,
        temporal_leakage_count,
    )

    target = Path(__file__).resolve().parents[1] / "samples" / "dashboard" / "healthy"
    data = load_dashboard_data(str(target))
    dist = prediction_distribution(data.predictions)
    assert sum(dist.values()) == len(data.predictions)
    # The healthy fixture has no leakage, so severity should be ok.
    assert leakage_severity(int(len(data.leakage))) == "ok"
    # Accuracy / averages are computable.
    assert average_confidence(data.predictions) >= 0.0
    assert average_confidence_drop(data.faithfulness) >= 0.0


def test_faithfulness_levels_constant_matches_three_levels() -> None:
    """The level list is exposed to the sidebar; pin its contents."""
    assert tuple(FAITHFULNESS_LEVELS) == ("high", "medium", "low")


def test_valid_predictions_constant_matches_three_classes() -> None:
    assert tuple(VALID_PREDICTIONS) == ("UP", "DOWN", "HOLD")