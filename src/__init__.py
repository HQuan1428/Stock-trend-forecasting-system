"""Faithful evidence-centric financial news forecasting prototype.

Class re-exports are lazy (PEP 562) so ``python -m src.<stage>`` does not
double-import the stage module through the package ``__init__`` (which
would emit a ``RuntimeWarning`` from runpy). ``from src import
ForecastModel`` etc. keep working unchanged.
"""

from __future__ import annotations

import importlib
from typing import Any

_EXPORTS = {
    # retriever
    "TemporalRetriever": "src.retriever",
    "TimeUtils": "src.retriever",
    "RetrievalResult": "src.retriever",
    "TemporalValidationError": "src.retriever",
    # evidence_extractor
    "EvidenceExtractor": "src.evidence_extractor",
    # evidence_selector
    "EvidenceSelector": "src.evidence_selector",
    "EvidenceSelectorError": "src.evidence_selector",
    # forecast_model
    "ForecastModel": "src.forecast_model",
    "ForecastModelError": "src.forecast_model",
    # faithfulness_evaluator / faithfulness_metrics
    "FaithfulnessEvaluator": "src.faithfulness_evaluator",
    "FaithfulnessEvaluatorError": "src.faithfulness_evaluator",
    "FaithfulnessMetrics": "src.faithfulness_metrics",
    "VERDICTS": "src.faithfulness_metrics",
    # sufficiency (B1) / market (B3)
    "SufficiencyEvaluator": "src.sufficiency_evaluator",
    "MarketAnalyzer": "src.market_analyzer",
    # shared data contracts + validators
    "NewsRecord": "src.schema",
    "EvidenceItem": "src.schema",
    "ForecastResult": "src.schema",
    "FaithfulnessResult": "src.schema",
    "PipelineResult": "src.schema",
    "REQUIRED_SAMPLE_KEYS": "src.schema",
    "validate_sample": "src.schema",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    if name in _EXPORTS:
        return getattr(importlib.import_module(_EXPORTS[name]), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
