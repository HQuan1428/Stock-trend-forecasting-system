"""Unit tests for src.stages.sufficiency_evaluator (B1)."""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from src.stages.sufficiency_evaluator import SufficiencyEvaluator

_only_cited_evidence = SufficiencyEvaluator._only_cited_evidence
_perturb_to_neutral = SufficiencyEvaluator._perturb_to_neutral
_compute_sufficiency_score = SufficiencyEvaluator._compute_sufficiency_score


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_FORECAST_TIME = "2025-03-12T09:00:00"


def _make_evidence(news_id: str, direction: str, idx: int = 0) -> Dict[str, Any]:
    pos_p, neg_p, neu_p = (
        (0.85, 0.10, 0.05) if direction == "UP"
        else (0.10, 0.85, 0.05) if direction == "DOWN"
        else (0.15, 0.15, 0.70)
    )
    polarity = "positive" if direction == "UP" else "negative" if direction == "DOWN" else "neutral"
    return {
        "evidence_id": f"{news_id}_ev{idx}",
        "news_id": news_id,
        "news_time": "2025-03-11T08:00:00",
        "evidence_text": f"Evidence for {news_id}",
        "polarity": polarity,
        "expected_direction": direction,
        "support_score": pos_p if direction == "UP" else neg_p if direction == "DOWN" else neu_p,
        "sentiment_probs": {"positive": pos_p, "negative": neg_p, "neutral": neu_p},
    }


def _make_request(evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "sample_id": "TEST_sample",
        "ticker": "TEST",
        "forecast_time": _FORECAST_TIME,
        "evidence": evidence,
    }


def _make_result(prediction: str, confidence: float) -> Dict[str, Any]:
    return {"prediction": prediction, "confidence": confidence}


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------


def test_only_cited_evidence_filters_correctly() -> None:
    evs = [_make_evidence("N1", "UP"), _make_evidence("N2", "DOWN"), _make_evidence("N3", "HOLD")]
    cited = {"N1", "N3"}
    result = _only_cited_evidence(evs, cited)
    assert [e["news_id"] for e in result] == ["N1", "N3"]


def test_only_cited_evidence_empty_cited_ids() -> None:
    evs = [_make_evidence("N1", "UP"), _make_evidence("N2", "DOWN")]
    result = _only_cited_evidence(evs, set())
    assert result == []


def test_perturb_to_neutral_replaces_cited() -> None:
    evs = [_make_evidence("N1", "UP"), _make_evidence("N2", "DOWN")]
    perturbed = _perturb_to_neutral(evs, {"N1"})
    assert len(perturbed) == 2
    # N1 replaced
    n1 = next(e for e in perturbed if e["news_id"] == "N1")
    assert n1["expected_direction"] == "HOLD"
    assert n1["support_score"] == 0.5
    assert n1["evidence_text"] == ""
    assert n1["polarity"] == "neutral"
    # N2 unchanged
    n2 = next(e for e in perturbed if e["news_id"] == "N2")
    assert n2["expected_direction"] == "DOWN"


def test_perturb_to_neutral_empty_cited_ids_returns_unchanged() -> None:
    evs = [_make_evidence("N1", "UP")]
    perturbed = _perturb_to_neutral(evs, set())
    assert perturbed[0]["expected_direction"] == "UP"


def test_compute_sufficiency_score_clamped_to_one() -> None:
    assert _compute_sufficiency_score(0.9, 0.7) == pytest.approx(1.0)


def test_compute_sufficiency_score_normal() -> None:
    score = _compute_sufficiency_score(0.6, 0.8)
    assert score == pytest.approx(0.6 / 0.8)
    assert 0.0 <= score <= 1.0


def test_compute_sufficiency_score_zero_original_confidence() -> None:
    assert _compute_sufficiency_score(0.5, 0.0) == 0.0


# ---------------------------------------------------------------------------
# SufficiencyEvaluator integration tests
# ---------------------------------------------------------------------------


def test_sufficiency_score_in_range() -> None:
    evs = [_make_evidence("N1", "UP"), _make_evidence("N2", "UP")]
    req = _make_request(evs)
    from src.stages.forecast_model import ForecastModel
    result = ForecastModel().predict(req)
    cited = {"N1"}
    evaluator = SufficiencyEvaluator()
    out = evaluator.evaluate(req, result, cited)
    assert 0.0 <= out["sufficiency_score"] <= 1.0


def test_prediction_on_only_cited_is_valid_label() -> None:
    evs = [_make_evidence("N1", "UP"), _make_evidence("N2", "DOWN")]
    req = _make_request(evs)
    from src.stages.forecast_model import ForecastModel
    result = ForecastModel().predict(req)
    cited = {"N1"}
    evaluator = SufficiencyEvaluator()
    out = evaluator.evaluate(req, result, cited)
    assert out["prediction_on_only_cited"] in ("UP", "DOWN", "HOLD")


def test_counterfactual_delta_is_signed_float() -> None:
    evs = [_make_evidence("N1", "UP"), _make_evidence("N2", "UP")]
    req = _make_request(evs)
    from src.stages.forecast_model import ForecastModel
    result = ForecastModel().predict(req)
    cited = {"N1", "N2"}
    evaluator = SufficiencyEvaluator()
    out = evaluator.evaluate(req, result, cited)
    assert isinstance(out["counterfactual_delta"], float)
    # Replacing all cited evidence with neutral should reduce confidence → delta >= 0
    assert out["counterfactual_delta"] >= 0.0


def test_empty_cited_ids_gives_sufficiency_zero_and_no_counterfactual_change() -> None:
    evs = [_make_evidence("N1", "UP")]
    req = _make_request(evs)
    from src.stages.forecast_model import ForecastModel
    result = ForecastModel().predict(req)
    original_confidence = float(result["confidence"])
    evaluator = SufficiencyEvaluator()
    out = evaluator.evaluate(req, result, set())
    # V3: sufficiency with no cited evidence runs ``predict`` against an
    # empty ``evidence`` list. The exact softmax value depends on the
    # Attention checkpoint (we commit random-init weights for now);
    # the qualitative contract is just ``sufficiency_score == 0.0``
    # (no citation means no faithfulness signal) and ``counterfactual_delta == 0``
    # (nothing to perturb).
    assert out["sufficiency_score"] == 0.0
    assert out["counterfactual_delta"] == pytest.approx(0.0)
    assert 0.0 < out["sufficiency_confidence"] <= 1.0


def test_all_evidence_cited_sufficiency_score_approx_one() -> None:
    evs = [_make_evidence("N1", "UP"), _make_evidence("N2", "UP")]
    req = _make_request(evs)
    from src.stages.forecast_model import ForecastModel
    result = ForecastModel().predict(req)
    cited = {"N1", "N2"}
    evaluator = SufficiencyEvaluator()
    out = evaluator.evaluate(req, result, cited)
    # All evidence is cited → sufficiency_confidence == original_confidence → score == 1.0
    assert out["sufficiency_score"] == pytest.approx(1.0)
