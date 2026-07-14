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
    "TemporalRetriever": "src.stages.retriever",
    "TimeUtils": "src.stages.retriever",
    "RetrievalResult": "src.stages.retriever",
    "TemporalValidationError": "src.stages.retriever",
    # evidence_extractor
    "EvidenceExtractor": "src.stages.evidence_extractor",
    # evidence_selector
    "EvidenceSelector": "src.stages.evidence_selector",
    "EvidenceSelectorError": "src.stages.evidence_selector",
    # forecast_model
    "ForecastModel": "src.stages.forecast_model",
    "ForecastModelError": "src.stages.forecast_model",
    # faithfulness_evaluator / faithfulness_metrics
    "FaithfulnessEvaluator": "src.stages.faithfulness_evaluator",
    "FaithfulnessEvaluatorError": "src.stages.faithfulness_evaluator",
    "FaithfulnessMetrics": "src.stages.faithfulness_metrics",
    "VERDICTS": "src.stages.faithfulness_metrics",
    # sufficiency (B1) / market (B3)
    "SufficiencyEvaluator": "src.stages.sufficiency_evaluator",
    "MarketAnalyzer": "src.stages.market_analyzer",
    # shared data contracts + validators
    "NewsRecord": "src.core.schema",
    "EvidenceItem": "src.core.schema",
    "ForecastResult": "src.core.schema",
    "FaithfulnessResult": "src.core.schema",
    "PipelineResult": "src.core.schema",
    "REQUIRED_SAMPLE_KEYS": "src.core.schema",
    "validate_sample": "src.core.schema",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    if name in _EXPORTS:
        return getattr(importlib.import_module(_EXPORTS[name]), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
