"""Unit tests for src.market_analyzer (B3)."""

from __future__ import annotations

import pytest

from src.market_analyzer import (
    REGIME_THRESHOLD,
    RETURN_THRESHOLD,
    MarketAnalyzer,
    _classify_regime,
    _is_market_consistent,
)


# ---------------------------------------------------------------------------
# _classify_regime
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ret,expected", [
    (0.03,  "bull"),
    (0.021, "bull"),
    (REGIME_THRESHOLD + 0.001, "bull"),
    (-0.03, "bear"),
    (-0.021, "bear"),
    (-REGIME_THRESHOLD - 0.001, "bear"),
    (0.0,   "sideways"),
    (0.01,  "sideways"),
    (-0.01, "sideways"),
    (REGIME_THRESHOLD,  "sideways"),   # boundary: not strictly >
    (-REGIME_THRESHOLD, "sideways"),   # boundary: not strictly <
])
def test_classify_regime(ret: float, expected: str) -> None:
    assert _classify_regime(ret) == expected


# ---------------------------------------------------------------------------
# _is_market_consistent
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("prediction,ret,expected", [
    # UP
    ("UP", 0.02,  True),
    ("UP", RETURN_THRESHOLD + 0.001, True),
    ("UP", -0.015, False),
    ("UP", 0.001, False),             # within neutral band → not UP
    ("UP", RETURN_THRESHOLD, False),  # boundary: not strictly >
    # DOWN
    ("DOWN", -0.015, True),
    ("DOWN", -RETURN_THRESHOLD - 0.001, True),
    ("DOWN", 0.02, False),
    ("DOWN", 0.0, False),
    ("DOWN", -RETURN_THRESHOLD, False),  # boundary: not strictly <
    # HOLD
    ("HOLD", 0.001, True),
    ("HOLD", 0.0, True),
    ("HOLD", RETURN_THRESHOLD, True),   # boundary: abs == threshold → True
    ("HOLD", 0.03, False),              # strong positive → not HOLD
    ("HOLD", -0.03, False),             # strong negative → not HOLD
    ("HOLD", RETURN_THRESHOLD + 0.001, False),
])
def test_is_market_consistent(prediction: str, ret: float, expected: bool) -> None:
    assert _is_market_consistent(prediction, ret) is expected


# ---------------------------------------------------------------------------
# MarketAnalyzer.analyze
# ---------------------------------------------------------------------------


def test_analyze_returns_all_fields() -> None:
    result = MarketAnalyzer().analyze("UP", 0.02, 0.03)
    assert set(result.keys()) == {
        "market_consistent",
        "market_consistency_score",
        "regime",
        "next_day_return",
        "price_5d_return",
    }


def test_analyze_consistency_score_binary() -> None:
    for pred, ret, p5d in [("UP", 0.02, 0.0), ("DOWN", -0.02, 0.0), ("HOLD", 0.001, 0.0)]:
        r = MarketAnalyzer().analyze(pred, ret, p5d)
        assert r["market_consistency_score"] in (0.0, 1.0)


def test_analyze_regime_valid_values() -> None:
    for p5d in [0.03, -0.03, 0.0]:
        r = MarketAnalyzer().analyze("HOLD", 0.0, p5d)
        assert r["regime"] in ("bull", "bear", "sideways")


def test_analyze_echoes_inputs() -> None:
    r = MarketAnalyzer().analyze("UP", 0.0123, -0.0456)
    assert r["next_day_return"] == pytest.approx(0.0123)
    assert r["price_5d_return"] == pytest.approx(-0.0456)


def test_analyze_consistent_up() -> None:
    r = MarketAnalyzer().analyze("UP", 0.02, 0.03)
    assert r["market_consistent"] is True
    assert r["market_consistency_score"] == 1.0
    assert r["regime"] == "bull"


def test_analyze_inconsistent_up_negative_return() -> None:
    r = MarketAnalyzer().analyze("UP", -0.015, -0.025)
    assert r["market_consistent"] is False
    assert r["market_consistency_score"] == 0.0
    assert r["regime"] == "bear"


def test_analyze_hold_in_neutral_band() -> None:
    r = MarketAnalyzer().analyze("HOLD", 0.001, 0.01)
    assert r["market_consistent"] is True
    assert r["regime"] == "sideways"


def test_analyze_hold_inconsistent_strong_move() -> None:
    r = MarketAnalyzer().analyze("HOLD", 0.03, 0.0)
    assert r["market_consistent"] is False
