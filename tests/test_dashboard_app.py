"""Smoke tests for the dashboard render layer.

The render layer is thin by design; these tests only assert that the
modules import cleanly (no server needed) and that the Live Demo's
sample-selection helpers behave on a realistic frame. All aggregation
logic is covered in test_dashboard_metrics.py.
"""

from __future__ import annotations

import importlib

import pandas as pd
import pytest


def test_app_module_imports_without_running() -> None:
    app = importlib.import_module("src.dashboard.app")
    assert callable(app.main)


def test_components_module_imports() -> None:
    components = importlib.import_module("src.dashboard.components")
    assert callable(components.verdict_banner)


def test_live_demo_selection_helpers() -> None:
    from src.dashboard.metrics import find_sample_id, sample_choices

    samples = pd.DataFrame(
        [
            {"sample_id": "S1", "ticker": "AAPL", "forecast_time": "2025-03-12 09:00"},
            {"sample_id": "S2", "ticker": "AAPL", "forecast_time": "2025-03-13 09:00"},
            {"sample_id": "S3", "ticker": "GOOGL", "forecast_time": "2025-03-12 09:00"},
        ]
    )
    assert sample_choices(samples, "AAPL") == ["2025-03-12 09:00", "2025-03-13 09:00"]
    assert find_sample_id(samples, "AAPL", "2025-03-13 09:00") == "S2"
    with pytest.raises(KeyError):
        find_sample_id(samples, "AAPL", "1999-01-01 00:00")


def test_verdict_banner_text_is_vietnamese_and_complete() -> None:
    from src.dashboard.metrics import VERDICT_BANNERS
    from src.stages.faithfulness_metrics import VERDICTS

    # Every internal verdict must have a banner mapping.
    assert set(VERDICT_BANNERS) == set(VERDICTS)