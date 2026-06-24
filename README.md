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
module. When `ticker` is provided, it is a real filter: only news items whose
own `ticker` field matches (case-sensitive string equality) reach the time
filter. Items with a mismatched or missing `ticker` are excluded and reported
in the structured `errors` list.

```python
from src.retriever import retrieve_valid_news

result = retrieve_valid_news(
    forecast_time="2025-03-12 09:00",  # naive → interpreted as UTC
    ticker="AAPL",                      # acts as a case-sensitive filter
    news=[
        {
            "news_id": "n1",
            "news_time": "2025-03-11 08:00",
            "ticker": "AAPL",
            "text": "Past AAPL headline",
        },
        {
            "news_id": "n2",
            "news_time": "2025-03-12 15:30",
            "ticker": "AAPL",
            "text": "Future AAPL headline",
        },
        {
            "news_id": "n3",
            "news_time": "2025-03-11 08:00",
            "ticker": "GOOGL",  # different ticker -> excluded
            "text": "Past GOOGL headline",
        },
        {
            "news_id": "n4",
            "news_time": "2025-03-11 08:00",
            # no ticker -> excluded
            "text": "Past untickered headline",
        },
    ],
)
assert result.ticker == "AAPL"
assert result.valid_count == 1                  # n1: past + ticker match
assert result.invalid_future_count == 1         # n2: future + ticker match
assert len(result.errors) == 2                  # n3 (ticker_mismatch), n4 (missing_ticker)
assert result.temporal_validity == 0.25         # 1/4

# Passing ticker=None (or omitting it) skips the ticker filter entirely,
# preserving the original behavior where every news item reaches the time
# filter regardless of its ticker field.
```

**Contract for downstream consumers:** consume `valid_news` only. The
`invalid_future_news` group exists for traceability and dashboard warnings —
it MUST never be fed into the evidence extractor or forecast model.
Ticker-mismatched and ticker-missing items are reported in `errors` with
`reason` ∈ `{"ticker_mismatch", "missing_ticker"}`; the partition invariant
`len(valid_news) + len(invalid_future_news) + len(errors) == total_count`
always holds.

## Disclaimer

This project is for research and learning. It is not a trading system and does
not provide investment advice.
