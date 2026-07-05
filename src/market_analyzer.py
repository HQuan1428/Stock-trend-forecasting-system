"""Market Consistency + Regime Analysis (B3).

Given a forecast prediction and simulated market return data, this module
answers two questions:

1. **Market Consistency**: Does the prediction (UP/DOWN/HOLD) agree with the
   actual next-day return (``next_day_return``)?
   Thresholds: UP ↔ return > 0.005; DOWN ↔ return < -0.005; HOLD ↔ within ±0.005.

2. **Regime Classification**: What was the market regime at forecast time?
   Derived from ``price_5d_return``:
   - ``"bull"``     if price_5d_return > 0.02
   - ``"bear"``     if price_5d_return < -0.02
   - ``"sideways"`` otherwise

Both functions are pure, deterministic, and free of IO, ML, or external APIs.
"""

from __future__ import annotations

#: Threshold for classifying next_day_return as directional (vs. neutral).
RETURN_THRESHOLD: float = 0.005

#: Threshold for classifying the 5-day trend as bull/bear (vs. sideways).
REGIME_THRESHOLD: float = 0.02


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _classify_regime(price_5d_return: float) -> str:
    """Return ``"bull"``, ``"bear"``, or ``"sideways"`` based on price_5d_return."""
    if price_5d_return > REGIME_THRESHOLD:
        return "bull"
    if price_5d_return < -REGIME_THRESHOLD:
        return "bear"
    return "sideways"


def _is_market_consistent(prediction: str, next_day_return: float) -> bool:
    """Return ``True`` when ``prediction`` direction matches ``next_day_return`` sign.

    Mapping:
    - ``UP``   matches when ``next_day_return > RETURN_THRESHOLD``
    - ``DOWN`` matches when ``next_day_return < -RETURN_THRESHOLD``
    - ``HOLD`` matches when ``abs(next_day_return) <= RETURN_THRESHOLD``
    """
    if prediction == "UP":
        return next_day_return > RETURN_THRESHOLD
    if prediction == "DOWN":
        return next_day_return < -RETURN_THRESHOLD
    # HOLD
    return abs(next_day_return) <= RETURN_THRESHOLD


# ---------------------------------------------------------------------------
# Public evaluator
# ---------------------------------------------------------------------------


class MarketAnalyzer:
    """Compute market consistency and regime for a single forecast group."""

    def analyze(
        self,
        prediction: str,
        next_day_return: float,
        price_5d_return: float,
    ) -> dict:
        """Return market consistency and regime metrics.

        Args:
            prediction: The model's prediction — one of ``UP``, ``DOWN``, ``HOLD``.
            next_day_return: Actual next-day return (signed float, e.g. 0.02 = +2%).
            price_5d_return: 5-day trailing return used for regime classification.

        Returns:
            Dict with five fields:
            - ``market_consistent`` (bool)
            - ``market_consistency_score`` (float: 1.0 or 0.0)
            - ``regime`` (str: "bull" / "bear" / "sideways")
            - ``next_day_return`` (float, echoed)
            - ``price_5d_return`` (float, echoed)
        """
        consistent = _is_market_consistent(prediction, next_day_return)
        return {
            "market_consistent": consistent,
            "market_consistency_score": 1.0 if consistent else 0.0,
            "regime": _classify_regime(price_5d_return),
            "next_day_return": next_day_return,
            "price_5d_return": price_5d_return,
        }
