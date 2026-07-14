"""Unit tests for ``src/finbert_sentiment.py``.

Only the load-failure path is exercised here (mocked, no network/model
needed). Real-model classification behavior is covered by
``TestRealFinbertIntegration`` in ``tests/test_evidence_extractor.py``.
"""

from __future__ import annotations

import pytest

from src.finbert_sentiment import FinbertLoadError, FinbertSentimentScorer


def test_ensure_loaded_wraps_tokenizer_failure_in_finbert_load_error(monkeypatch) -> None:
    transformers = pytest.importorskip("transformers")

    def _raise(*args, **kwargs):
        raise OSError("simulated: no network and no local cache")

    monkeypatch.setattr(transformers.AutoTokenizer, "from_pretrained", _raise)

    scorer = FinbertSentimentScorer()
    with pytest.raises(FinbertLoadError) as excinfo:
        scorer.score(["Apple beats expectations."])

    assert "ProsusAI/finbert" in str(excinfo.value)
    assert "simulated: no network and no local cache" in str(excinfo.value)


def test_ensure_loaded_wraps_model_failure_in_finbert_load_error(monkeypatch) -> None:
    transformers = pytest.importorskip("transformers")

    def _raise(*args, **kwargs):
        raise OSError("simulated: corrupt checkpoint")

    monkeypatch.setattr(
        transformers.AutoModelForSequenceClassification, "from_pretrained", _raise
    )

    scorer = FinbertSentimentScorer()
    with pytest.raises(FinbertLoadError):
        scorer.score(["Apple beats expectations."])

    # A failed load must not leave the scorer half-initialized: a retry
    # (e.g. after fixing the network) should attempt loading again, not
    # silently short-circuit on a stale non-None tokenizer/model.
    assert scorer._model is None
    assert scorer._tokenizer is None


def test_finbert_load_error_does_not_require_torch_or_transformers() -> None:
    # Constructing/raising FinbertLoadError must not itself require the
    # heavy ML dependencies — it's a plain RuntimeError subclass.
    err = FinbertLoadError("boom")
    assert isinstance(err, RuntimeError)
    assert str(err) == "boom"
