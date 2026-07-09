"""Faithful evidence-centric financial news forecasting prototype."""

from src.faithfulness_evaluator import (
    FaithfulnessEvaluator,
    FaithfulnessEvaluatorError,
)
from src.faithfulness_metrics import VERDICTS, FaithfulnessMetrics
from src.evidence_extractor import EvidenceExtractor
from src.evidence_selector import EvidenceSelector, EvidenceSelectorError
from src.forecast_model import ForecastModel, ForecastModelError
from src.retriever import RetrievalResult, TemporalRetriever, TemporalValidationError, TimeUtils
from src.market_analyzer import MarketAnalyzer
from src.sufficiency_evaluator import SufficiencyEvaluator
from src.pipeline import PipelineRunner
from src.schema import (
    EvidenceItem,
    FaithfulnessResult,
    ForecastResult,
    NewsRecord,
    PipelineResult,
)
from src.dashboard import (  # noqa: E402 — placed after retriever for grouping
    COLOR_ACCENT,
    COLOR_CRITICAL,
    COLOR_HIGH,
    COLOR_LOW,
    COLOR_MEDIUM,
    COLOR_OK,
    COLOR_WARNING,
    DashboardData,
    DashboardDataError,
    EVIDENCE_COLUMNS,
    FAITHFULNESS_COLUMNS,
    LEAKAGE_COLUMNS,
    PREDICTION_COLUMNS,
    accuracy,
    accuracy_by_ticker,
    apply_filters,
    assert_columns,
    assert_dashboard_data,
    average_confidence,
    average_confidence_drop,
    average_temporal_validity,
    build_accuracy_by_ticker_chart,
    build_confidence_drop_chart,
    build_prediction_distribution_chart,
    build_temporal_leakage_chart,
    classify_faithfulness_level,
    leakage_severity,
    load_dashboard_data,
    prediction_distribution,
    temporal_leakage_count,
)

__all__ = [
    # retriever
    "TemporalRetriever",
    "TimeUtils",
    "RetrievalResult",
    "TemporalValidationError",
    # evidence_extractor
    "EvidenceExtractor",
    # evidence_selector
    "EvidenceSelector",
    "EvidenceSelectorError",
    # forecast_model
    "ForecastModel",
    "ForecastModelError",
    # faithfulness_evaluator / faithfulness_metrics
    "FaithfulnessEvaluator",
    "FaithfulnessEvaluatorError",
    "FaithfulnessMetrics",
    "VERDICTS",
    # sufficiency (B1) / market (B3)
    "SufficiencyEvaluator",
    "MarketAnalyzer",
    # pipeline
    "PipelineRunner",
    # dashboard — validators
    "DashboardDataError",
    "assert_columns",
    "assert_dashboard_data",
    # dashboard — data loader
    "DashboardData",
    "load_dashboard_data",
    "PREDICTION_COLUMNS",
    "EVIDENCE_COLUMNS",
    "FAITHFULNESS_COLUMNS",
    "LEAKAGE_COLUMNS",
    # dashboard — metrics
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
    # dashboard — charts
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
    "COLOR_ACCENT",
    # shared data contracts
    "NewsRecord",
    "EvidenceItem",
    "ForecastResult",
    "FaithfulnessResult",
    "PipelineResult",
]
