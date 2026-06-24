"""Faithful evidence-centric financial news forecasting prototype."""

from src.evidence_extractor import (
    EXTRACTION_METHOD,
    KEYWORDS,
    KEYWORD_TO_POLARITY,
    NEGATIVE_KEYWORDS,
    POLARITY_TO_DIRECTION,
    POSITIVE_KEYWORDS,
    SUPPORT_SCORES,
    build_evidence_objects,
    build_summary,
    extract_evidence,
    extract_evidence_batch,
    result_to_dict,
    select_primary_evidence_id,
)
from src.evidence_selector import (
    CLASSIFICATION_TABLE,
    DEFAULT_TOP_K,
    EVIDENCE_SELECTOR_FIELDS,
    EvidenceSelectorError,
    OUTPUT_GROUPS,
    REASON_TABLE,
    REQUIRED_INPUT_FIELDS,
    SELECTION_METHOD,
    VALID_DIRECTIONS,
    VALID_PREDICTIONS,
    compute_coverage,
    select_evidence,
    select_evidence_batch,
)
from src.retriever import RetrievalResult, TemporalValidationError, retrieve_valid_news

__all__ = [
    # retriever
    "retrieve_valid_news",
    "RetrievalResult",
    "TemporalValidationError",
    # evidence_extractor
    "extract_evidence",
    "extract_evidence_batch",
    "build_evidence_objects",
    "build_summary",
    "select_primary_evidence_id",
    "result_to_dict",
    "POSITIVE_KEYWORDS",
    "NEGATIVE_KEYWORDS",
    "KEYWORDS",
    "KEYWORD_TO_POLARITY",
    "POLARITY_TO_DIRECTION",
    "SUPPORT_SCORES",
    "EXTRACTION_METHOD",
    # evidence_selector
    "select_evidence",
    "select_evidence_batch",
    "compute_coverage",
    "EvidenceSelectorError",
    "CLASSIFICATION_TABLE",
    "REASON_TABLE",
    "REQUIRED_INPUT_FIELDS",
    "OUTPUT_GROUPS",
    "DEFAULT_TOP_K",
    "VALID_PREDICTIONS",
    "VALID_DIRECTIONS",
    "SELECTION_METHOD",
    "EVIDENCE_SELECTOR_FIELDS",
]
