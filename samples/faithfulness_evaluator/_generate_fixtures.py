"""Generate the four golden fixtures for the Faithfulness Evaluator.

This is a one-shot helper that materializes the ``_input.json`` /
``_expected.json`` pairs for the strong-faithful, decorative,
temporal-leakage, and unsupported scenarios. The fixtures are
byte-stable; running this script twice produces identical output.

The script is intentionally NOT a test fixture — it lives in
``samples/faithfulness_evaluator/_generate_fixtures.py`` and is
re-runnable by a developer when the metric definitions change. The
test suite reads the generated JSONs and never executes this script.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.forecast_model import predict
from src.faithfulness_evaluator import FaithfulnessEvaluator


OUT = Path(__file__).resolve().parent
FORECAST = "2025-03-12 09:00"


def _evidence(eid: str, direction: str, news_time: str) -> dict:
    return {
        "evidence_id": eid,
        "news_id": f"N-{eid}",
        "news_time": news_time,
        "evidence_text": "...",
        "polarity": "positive" if direction == "UP" else "negative" if direction == "DOWN" else "neutral",
        "expected_direction": direction,
        "support_score": 1.0,
    }


def _write(name: str, payload: dict) -> None:
    (OUT / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _hand_written_result(name: str) -> dict:
    """Read the hand-built result for scenarios that the Forecast Model
    would not produce (e.g., temporal leakage, unsupported evidence)."""
    path = OUT / f"{name}_result.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def strong_faithful() -> None:
    """3 UP + 1 DOWN. Cited = 3 UP. Ablation removes them → DOWN flips. Strong faithful."""
    evidence = [
        _evidence("E001", "UP", "2025-03-11 08:00"),
        _evidence("E002", "UP", "2025-03-11 09:00"),
        _evidence("E003", "UP", "2025-03-11 10:00"),
        _evidence("E004", "DOWN", "2025-03-11 11:00"),
    ]
    inp = {
        "sample_id": "S-FAITH-01",
        "ticker": "AAPL",
        "forecast_time": FORECAST,
        "label": "UP",
        "evidence": evidence,
    }
    result = predict(inp)
    _write("01_strong_faithful_input.json", inp)
    evaluator = FaithfulnessEvaluator()
    report = evaluator.evaluate(inp, result)
    _write("01_strong_faithful_expected.json", report)


def decorative() -> None:
    """1 UP + 1 DOWN → HOLD. Cited = both. Ablation removes UP → still HOLD. Decorative."""
    evidence = [
        _evidence("E101", "UP", "2025-03-11 08:00"),
        _evidence("E102", "DOWN", "2025-03-11 09:00"),
    ]
    inp = {
        "sample_id": "S-FAITH-02",
        "ticker": "GOOG",
        "forecast_time": FORECAST,
        "label": "HOLD",
        "evidence": evidence,
    }
    result = predict(inp)
    _write("02_decorative_input.json", inp)
    evaluator = FaithfulnessEvaluator()
    report = evaluator.evaluate(inp, result)
    _write("02_decorative_expected.json", report)


def temporal_leakage() -> None:
    """Cited evidence includes a future-dated item. Defense-in-depth scenario.

    The Forecast Model would normally filter the future item out of
    ``pro_evidence``; we hand-build the result here to simulate a
    cited-evidence list that the model is asked to defend despite the
    temporal leakage. This is the canonical ``invalid_temporal_leakage``
    case.
    """
    evidence = [
        _evidence("E201", "UP", "2025-03-11 08:00"),
        _evidence("E202", "UP", "2025-03-11 09:00"),
        _evidence("E203", "UP", "2025-03-11 10:00"),
        _evidence("E204", "UP", "2025-03-13 09:00"),  # future
    ]
    inp = {
        "sample_id": "S-FAITH-03",
        "ticker": "MSFT",
        "forecast_time": FORECAST,
        "label": "UP",
        "evidence": evidence,
    }
    result = {
        "sample_id": "S-FAITH-03",
        "ticker": "MSFT",
        "forecast_time": FORECAST,
        "prediction": "UP",
        "confidence": 0.8,
        "pro_evidence": [evidence[0], evidence[1], evidence[2], evidence[3]],
        "counter_evidence": [],
        "warnings": [],
        "model_version": "rule_based_v1",
    }
    _write("03_temporal_leakage_input.json", inp)
    _write("03_temporal_leakage_result.json", result)
    evaluator = FaithfulnessEvaluator()
    report = evaluator.evaluate(inp, result)
    _write("03_temporal_leakage_expected.json", report)


def unsupported() -> None:
    """Prediction UP, cited evidence all DOWN → unsupported."""
    # Need a result that predicts UP but with cited evidence all DOWN.
    # We construct a hand-built result to drive this scenario (the
    # Forecast Model would never produce a UP prediction with only
    # DOWN evidence). The evaluator only reads ``prediction``,
    # ``confidence``, ``pro_evidence``, ``counter_evidence``,
    # ``warnings``, and ``forecast_time`` from the result; we set them
    # by hand below.
    evidence = [
        _evidence("E301", "DOWN", "2025-03-11 08:00"),
        _evidence("E302", "DOWN", "2025-03-11 09:00"),
    ]
    inp = {
        "sample_id": "S-FAITH-04",
        "ticker": "TSLA",
        "forecast_time": FORECAST,
        "label": "UP",
        "evidence": evidence,
    }
    result = {
        "sample_id": "S-FAITH-04",
        "ticker": "TSLA",
        "forecast_time": FORECAST,
        "prediction": "UP",
        "confidence": 0.6,
        "pro_evidence": [evidence[0], evidence[1]],
        "counter_evidence": [],
        "warnings": [],
        "model_version": "rule_based_v1",
    }
    _write("04_unsupported_input.json", inp)
    _write("04_unsupported_result.json", result)
    evaluator = FaithfulnessEvaluator()
    report = evaluator.evaluate(inp, result)
    _write("04_unsupported_expected.json", report)


if __name__ == "__main__":
    strong_faithful()
    decorative()
    temporal_leakage()
    unsupported()
    print("Wrote fixtures to", OUT)
