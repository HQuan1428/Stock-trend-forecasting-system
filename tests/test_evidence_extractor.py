"""Unit tests for ``src/stages/evidence_extractor.py`` (V3 — FinBERT).

The FinBERT-aware evidence extractor relies on a locally-cached
``ProsusAI/finbert`` model. To keep this suite fully offline we mock
``FinbertSentimentScorer`` instead of calling the network model.
``test_real_finbert_integration`` skips itself when the cache is missing.
"""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import patch

import pytest

from src.stages.evidence_extractor import (
    POLARITY_TO_DIRECTION,
    SUPPORT_SCORES,
    EvidenceExtractor,
    process,
)


_NEWS_AAPL_UP = {
    "news_id": "N001",
    "ticker": "AAPL",
    "forecast_time": "2025-03-12 09:00",
    "news_time": "2025-03-11 08:00",
    "news_text": "Apple announces record profit and strong sales.",
}
_NEWS_GOOGL_DOWN = {
    "news_id": "N002",
    "ticker": "GOOGL",
    "forecast_time": "2025-03-12 09:00",
    "news_time": "2025-03-11 09:00",
    "news_text": "Google faces antitrust lawsuit and heavy fine.",
}
_NEWS_EMPTY = {
    "news_id": "N003",
    "ticker": "MSFT",
    "forecast_time": "2025-03-12 09:00",
    "news_time": "2025-03-11 10:00",
    "news_text": "",
}


def _mock_scorer_scores(texts: List[str]) -> List[Dict[str, float]]:
    """Map canned news text to deterministic FinBERT-like probs."""
    out = []
    for t in texts:
        low = t.lower()
        if "record profit" in low or "strong sales" in low or "beats" in low:
            out.append({"positive": 0.95, "negative": 0.02, "neutral": 0.03})
        elif "antitrust" in low or "lawsuit" in low or "fine" in low:
            out.append({"positive": 0.10, "negative": 0.80, "neutral": 0.10})
        elif not t.strip():
            out.append({"positive": 0.0, "negative": 0.0, "neutral": 1.0})
        else:
            out.append({"positive": 0.40, "negative": 0.20, "neutral": 0.40})
    return out


@pytest.fixture(autouse=True)
def _mock_finbert(monkeypatch):
    """Avoid loading real FinBERT during the test suite."""
    monkeypatch.setattr(
        "src.stages.evidence_extractor.EvidenceExtractor._get_scorer",
        lambda self: type(
            "FakeScorer", (), {"score": staticmethod(_mock_scorer_scores)}
        )(),
    )
    # Reset the cache between tests so each gets a fresh fixture.
    EvidenceExtractor._scorer = None
    yield
    EvidenceExtractor._scorer = None


# ---------------------------------------------------------------------------
# Constants — single source of truth contract
# ---------------------------------------------------------------------------


def test_polarity_to_direction_is_canonical() -> None:
    assert POLARITY_TO_DIRECTION == {"positive": "UP", "negative": "DOWN", "neutral": "HOLD"}


def test_support_scores_have_three_keys() -> None:
    assert set(SUPPORT_SCORES.keys()) == {"positive", "negative", "neutral"}


def test_extraction_method_is_finbert_v1() -> None:
    assert EvidenceExtractor.EXTRACTION_METHOD == "finbert_sentiment_v1"


# ---------------------------------------------------------------------------
# _argmax_polarity — tie-break order
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "probs,expected",
    [
        ({"positive": 0.9, "negative": 0.05, "neutral": 0.05}, "positive"),
        ({"positive": 0.05, "negative": 0.9, "neutral": 0.05}, "negative"),
        ({"positive": 0.05, "negative": 0.05, "neutral": 0.9}, "neutral"),
        ({"positive": 0.5, "negative": 0.5, "neutral": 0.0}, "positive"),
        ({"positive": 0.0, "negative": 0.5, "neutral": 0.5}, "negative"),
    ],
)
def test_argmax_polarity_respects_tiebreak(probs: Dict[str, float], expected: str) -> None:
    assert EvidenceExtractor._argmax_polarity(probs) == expected


# ---------------------------------------------------------------------------
# _score_text — empty text fallback
# ---------------------------------------------------------------------------


def test_score_text_empty_returns_neutral_uniform() -> None:
    ex = EvidenceExtractor()
    out = ex._score_text("")
    assert out == {"positive": 0.0, "negative": 0.0, "neutral": 1.0}


def test_score_text_none_returns_neutral_uniform() -> None:
    ex = EvidenceExtractor()
    assert ex._score_text(None) == {"positive": 0.0, "negative": 0.0, "neutral": 1.0}


# ---------------------------------------------------------------------------
# build_evidence_objects
# ---------------------------------------------------------------------------


def test_build_evidence_objects_emits_one_item_with_sentiment_probs() -> None:
    ex = EvidenceExtractor()
    items = ex.build_evidence_objects(
        "N007",
        "positive",
        {"positive": 0.82, "negative": 0.10, "neutral": 0.08},
        "Apple beats expectations.",
    )
    assert len(items) == 1
    item = items[0]
    assert item["evidence_id"] == "N007_E001"
    assert item["polarity"] == "positive"
    assert item["expected_direction"] == "UP"
    assert item["support_score"] == pytest.approx(0.82)
    assert item["sentiment_probs"] == pytest.approx(
        {"positive": 0.82, "negative": 0.10, "neutral": 0.08}
    )


def test_build_evidence_objects_negative_polarity_maps_to_down() -> None:
    ex = EvidenceExtractor()
    items = ex.build_evidence_objects(
        "N008", "negative",
        {"positive": 0.10, "negative": 0.80, "neutral": 0.10},
        "Google faces antitrust lawsuit.",
    )
    assert items[0]["expected_direction"] == "DOWN"
    assert items[0]["support_score"] == pytest.approx(0.80)


# ---------------------------------------------------------------------------
# extract() end-to-end (mocked FinBERT)
# ---------------------------------------------------------------------------


def test_extract_positive_news_returns_up_evidence() -> None:
    ex = EvidenceExtractor()
    out = ex.extract(_NEWS_AAPL_UP)
    assert out["extraction_method"] == "finbert_sentiment_v1"
    assert len(out["evidence"]) == 1
    e = out["evidence"][0]
    assert e["polarity"] == "positive"
    assert e["expected_direction"] == "UP"
    assert sum(e["sentiment_probs"].values()) == pytest.approx(1.0)
    assert out["primary_evidence_id"] == "N001_E001"


def test_extract_negative_news_returns_down_evidence() -> None:
    ex = EvidenceExtractor()
    out = ex.extract(_NEWS_GOOGL_DOWN)
    assert len(out["evidence"]) == 1
    e = out["evidence"][0]
    assert e["polarity"] == "negative"
    assert e["expected_direction"] == "DOWN"


def test_extract_empty_news_returns_neutral_evidence() -> None:
    ex = EvidenceExtractor()
    out = ex.extract(_NEWS_EMPTY)
    e = out["evidence"][0]
    assert e["polarity"] == "neutral"
    assert e["expected_direction"] == "HOLD"
    assert e["sentiment_probs"] == {"positive": 0.0, "negative": 0.0, "neutral": 1.0}


def test_extract_summary_counts_match_evidence() -> None:
    ex = EvidenceExtractor()
    out = ex.extract(_NEWS_AAPL_UP)
    s = out["summary"]
    assert s["positive_count"] == 1
    assert s["negative_count"] == 0
    assert s["neutral_count"] == 0
    assert s["total_evidence_count"] == 1
    assert s["has_mixed_evidence"] is False


# ---------------------------------------------------------------------------
# process() envelope adapter — runs against ingest + retriever chains
# ---------------------------------------------------------------------------


def _envelope_with_news(news: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "stage": "retriever",
        "samples": [
            {
                "sample_id": "T1",
                "ticker": news[0]["ticker"],
                "forecast_time": news[0]["forecast_time"],
                "label": "UP",
                "news": news,
                "valid_news": news,
                "invalid_future_news": [],
            }
        ],
    }


def test_process_appends_news_time_and_emits_sentiment_probs() -> None:
    env = _envelope_with_news([_NEWS_AAPL_UP])
    out = process(env)
    e = out["samples"][0]["evidence"][0]
    assert e["news_time"] == "2025-03-11 08:00"
    assert "sentiment_probs" in e
    assert sum(e["sentiment_probs"].values()) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Real FinBERT integration — skipped when no local model cache
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    "not __import__('os').path.isdir(__import__('os').path.expanduser('~/.cache/huggingface/hub/models--ProsusAI--finbert'))",
    reason="ProsusAI/finbert weights not in local Hugging Face cache",
)
def test_real_finbert_integration() -> None:
    """End-to-end test that actually runs FinBERT on a positive headline.

    Skip automatically when the local cache is missing (offline CI).
    """
    EvidenceExtractor._scorer = None  # ensure a fresh load
    ex = EvidenceExtractor()
    out = ex.extract(_NEWS_AAPL_UP)
    e = out["evidence"][0]
    assert e["polarity"] == "positive"
    assert e["expected_direction"] == "UP"
    assert e["sentiment_probs"]["positive"] > 0.5
