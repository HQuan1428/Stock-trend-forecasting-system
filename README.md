# Faithful Evidence-Centric Financial News Forecasting

An academic prototype for forecasting stock movement from financial news while
evaluating whether the cited evidence is relevant, temporally valid, and
faithful to each prediction.

## Project status

The repository is currently at the initial scaffold stage. Application logic
is added through OpenSpec-driven changes. The first change,
`temporal-retriever`, ships the news-time filter that all later stages rely on.

## Setup

```bash
pip install -r requirements.txt
```

## Tests

```bash
pytest tests/
```

## Temporal Retriever

The Temporal Retriever is the first stage of the pipeline. It guarantees that
no news published **after** a forecast moment can ever reach a downstream
module.

```python
from src.retriever import retrieve_valid_news

result = retrieve_valid_news(
    forecast_time="2025-03-12 09:00",  # naive → interpreted as UTC
    ticker="AAPL",
    news=[
        {"news_id": "n1", "news_time": "2025-03-11 08:00", "text": "Past headline"},
        {"news_id": "n2", "news_time": "2025-03-12 15:30", "text": "Future headline"},
    ],
)
assert result.valid_count == 1
assert result.invalid_future_count == 1
assert result.temporal_validity == 0.5
assert result.ticker == "AAPL"
```

**Contract for downstream consumers:** consume `valid_news` only. The
`invalid_future_news` group exists for traceability and dashboard warnings —
it MUST never be fed into the evidence extractor or forecast model.

## Disclaimer

This project is for research and learning. It is not a trading system and does
not provide investment advice.
