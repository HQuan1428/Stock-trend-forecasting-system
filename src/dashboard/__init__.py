"""Visualization Dashboard.

The final read-only visualization layer of the Faithful Evidence-Centric
Financial News Forecasting pipeline. Consumes four upstream CSV outputs
(``prediction_results.csv``, ``evidence_results.csv`` (synthesized when
missing), ``faithfulness_results.csv``, ``temporal_leakage_results.csv``
(synthesized when missing)) and renders a 5-tab Streamlit dashboard with
sidebar filters.

This module is **read-only with respect to upstream artifacts**: it MUST
NOT mutate any file under ``outputs/``. It MUST NOT re-run the
upstream pipeline. It MUST NOT invoke any LLM, FinBERT, transformer,
logistic-regression, deep-learning model, or external API. The
dashboard is **deterministic** given the same input files and the same
filter state.

The package is split into a thin app layer and pure-function modules
that can be unit-tested without a Streamlit server:

- :mod:`src.dashboard.validators` — column assertions + ``DashboardDataError``.
- :mod:`src.dashboard.metrics` — pure metric functions and filter helpers.
- :mod:`src.dashboard.data_loader` — CSV loaders + proposal-vs-source adapter.
- :mod:`src.dashboard.charts` — Plotly chart builders (no Streamlit import).
- :mod:`src.dashboard.components` — Streamlit UI primitives.
- :mod:`src.dashboard.app` — the ``streamlit run`` entry point.
"""

from src.dashboard.validators import (
    DashboardDataError,
    assert_columns,
    assert_dashboard_data,
)
from src.dashboard.data_loader import (
    DashboardData,
    EVIDENCE_COLUMNS,
    FAITHFULNESS_COLUMNS,
    LEAKAGE_COLUMNS,
    PREDICTION_COLUMNS,
    load_dashboard_data,
)
from src.dashboard.metrics import (
    FAITHFULNESS_HIGH_THRESHOLD,
    FAITHFULNESS_LEVELS,
    FAITHFULNESS_MEDIUM_THRESHOLD,
    LEAKAGE_CRITICAL_THRESHOLD,
    LEAKAGE_SEVERITIES,
    LEAKAGE_WARNING_THRESHOLD,
    VALID_PREDICTIONS,
    accuracy,
    accuracy_by_ticker,
    apply_filters,
    average_confidence,
    average_confidence_drop,
    average_temporal_validity,
    classify_faithfulness_level,
    leakage_severity,
    prediction_distribution,
    temporal_leakage_count,
)
from src.dashboard.charts import (
    COLOR_ACCENT,
    COLOR_CRITICAL,
    COLOR_HIGH,
    COLOR_LOW,
    COLOR_MEDIUM,
    COLOR_OK,
    COLOR_WARNING,
    build_accuracy_by_ticker_chart,
    build_confidence_drop_chart,
    build_prediction_distribution_chart,
    build_temporal_leakage_chart,
)

__all__ = [
    # validators
    "DashboardDataError",
    "assert_columns",
    "assert_dashboard_data",
    # data_loader
    "DashboardData",
    "load_dashboard_data",
    "PREDICTION_COLUMNS",
    "EVIDENCE_COLUMNS",
    "FAITHFULNESS_COLUMNS",
    "LEAKAGE_COLUMNS",
    # metrics — constants
    "FAITHFULNESS_HIGH_THRESHOLD",
    "FAITHFULNESS_MEDIUM_THRESHOLD",
    "LEAKAGE_WARNING_THRESHOLD",
    "LEAKAGE_CRITICAL_THRESHOLD",
    "FAITHFULNESS_LEVELS",
    "LEAKAGE_SEVERITIES",
    "VALID_PREDICTIONS",
    # metrics — functions
    "prediction_distribution",
    "accuracy",
    "average_confidence",
    "average_confidence_drop",
    "temporal_leakage_count",
    "average_temporal_validity",
    "classify_faithfulness_level",
    "leakage_severity",
    "accuracy_by_ticker",
    "apply_filters",
    # charts
    "build_prediction_distribution_chart",
    "build_confidence_drop_chart",
    "build_temporal_leakage_chart",
    "build_accuracy_by_ticker_chart",
    "COLOR_HIGH",
    "COLOR_MEDIUM",
    "COLOR_LOW",
    "COLOR_OK",
    "COLOR_WARNING",
    "COLOR_CRITICAL",
]
