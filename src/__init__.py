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
]
