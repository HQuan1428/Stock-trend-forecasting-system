"""Generate golden fixtures for the Forecast Model by running predict().

Run from the project root:
    .venv/bin/python samples/forecast_model/_generate.py
"""

from __future__ import annotations

import json
from pathlib import Path

from src.forecast_model import predict


SAMPLES_DIR = Path(__file__).resolve().parent


def _write(name: str, payload: dict, result: dict) -> None:
    (SAMPLES_DIR / f"{name}_input.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    )
    (SAMPLES_DIR / f"{name}_expected.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )


def _evidence(eid, news_id, news_time, text, polarity, direction, score=1.0):
    return {
        "evidence_id": eid,
        "news_id": news_id,
        "news_time": news_time,
        "evidence_text": text,
        "polarity": polarity,
        "expected_direction": direction,
        "support_score": score,
    }


def fixture_01_up() -> None:
    payload = {
        "sample_id": "S0001",
        "ticker": "AAPL",
        "forecast_time": "2025-03-12 09:00",
        "label": "UP",
        "evidence": [
            _evidence("N001_E001", "N001", "2025-03-11 08:30", "strong sales", "positive", "UP"),
            _evidence("N002_E001", "N002", "2025-03-11 10:00", "raised guidance", "positive", "UP"),
            _evidence("N003_E001", "N003", "2025-03-11 11:00", "new product launch", "positive", "UP"),
            _evidence("N004_E001", "N004", "2025-03-11 12:00", "lawsuit risk", "negative", "DOWN"),
        ],
    }
    _write("01_up", payload, predict(payload))


def fixture_02_down() -> None:
    payload = {
        "sample_id": "S0002",
        "ticker": "MSFT",
        "forecast_time": "2025-04-01 09:00",
        "label": "DOWN",
        "evidence": [
            _evidence("N010_E001", "N010", "2025-03-30 08:30", "weak sales", "negative", "DOWN"),
            _evidence("N011_E001", "N011", "2025-03-30 09:30", "regulatory probe", "negative", "DOWN"),
            _evidence("N012_E001", "N012", "2025-03-30 10:30", "guidance cut", "negative", "DOWN"),
            _evidence("N013_E001", "N013", "2025-03-30 11:30", "new contract", "positive", "UP"),
        ],
    }
    _write("02_down", payload, predict(payload))


def fixture_03_balanced_hold() -> None:
    payload = {
        "sample_id": "S0003",
        "ticker": "GOOGL",
        "forecast_time": "2025-04-15 09:00",
        "label": "HOLD",
        "evidence": [
            _evidence("N020_E001", "N020", "2025-04-14 08:00", "strong revenue", "positive", "UP"),
            _evidence("N021_E001", "N021", "2025-04-14 09:00", "raised dividend", "positive", "UP"),
            _evidence("N022_E001", "N022", "2025-04-14 10:00", "weak margins", "negative", "DOWN"),
            _evidence("N023_E001", "N023", "2025-04-14 11:00", "cost pressure", "negative", "DOWN"),
        ],
    }
    _write("03_balanced_hold", payload, predict(payload))


def fixture_04_empty_hold() -> None:
    payload = {
        "sample_id": "S0004",
        "ticker": "AMZN",
        "forecast_time": "2025-05-01 09:00",
        "label": "HOLD",
        "evidence": [],
    }
    _write("04_empty_hold", payload, predict(payload))


def fixture_05_future_evidence() -> None:
    payload = {
        "sample_id": "S0005",
        "ticker": "TSLA",
        "forecast_time": "2025-03-12 09:00",
        "label": "UP",
        "evidence": [
            _evidence("N030_E001", "N030", "2025-03-11 08:30", "strong sales", "positive", "UP"),
            _evidence("N031_E001", "N031", "2025-03-11 09:30", "raised guidance", "positive", "UP"),
            # Future item (after forecast_time)
            _evidence("N032_E001", "N032", "2025-03-12 15:30", "future announcement", "positive", "UP"),
        ],
    }
    _write("05_future_evidence", payload, predict(payload))


def main() -> None:
    fixture_01_up()
    fixture_02_down()
    fixture_03_balanced_hold()
    fixture_04_empty_hold()
    fixture_05_future_evidence()
    print("Generated 5 forecast_model golden fixtures.")


if __name__ == "__main__":
    main()