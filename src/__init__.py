"""Faithful evidence-centric financial news forecasting prototype."""

from src.retriever import RetrievalResult, TemporalValidationError, retrieve_valid_news

__all__ = ["retrieve_valid_news", "RetrievalResult", "TemporalValidationError"]
