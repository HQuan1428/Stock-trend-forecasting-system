# Faithful Evidence-Centric Financial News Forecasting

An academic prototype for forecasting stock movement from financial news while
evaluating whether the cited evidence is relevant, temporally valid, and
faithful to each prediction.

## Project status

The repository is currently at the initial scaffold stage. Application logic
is added through OpenSpec-driven changes:

- `temporal-retriever` — news-time filter (first stage).
- `evidence-extractor` — keyword-based evidence extractor (second stage).

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

## Evidence Extractor

The Evidence Extractor is the second stage. It receives one news item (already
validated by the Temporal Retriever) and returns a structured list of
evidence phrases with polarity, expected direction, character offsets, and a
deterministic `primary_evidence_id`.

It is **rule-based, deterministic, and testable** — no LLM, no FinBERT, no
transformer. See
[`openspec/changes/evidence-extractor/specs/evidence-extractor/spec.md`](openspec/changes/evidence-extractor/specs/evidence-extractor/spec.md)
for the full normative spec.

### Single item

```python
from src.evidence_extractor import extract_evidence

result = extract_evidence({
    "news_id": "N001",
    "ticker": "GOOGL",
    "forecast_time": "2025-03-12 09:00",
    "news_time": "2025-03-11 15:30",
    "news_text": "Google raises guidance despite lawsuit risk",
})

# Two evidence items: one positive ("raises guidance"), one negative
# ("lawsuit"). summary.has_mixed_evidence is True. primary_evidence_id
# points to the negative "lawsuit" because the Primary Evidence Rule
# prefers negative > positive > neutral.
assert result["summary"]["has_mixed_evidence"] is True
assert result["primary_evidence_id"] == "N001_E002"
```

### Batch

```python
from src.evidence_extractor import extract_evidence_batch

results = extract_evidence_batch([item1, item2, item3])
# One result per input, in input order. No time-based filtering.
```

### Contract notes for downstream modules

- The Evidence Extractor does **not** filter by time. The Temporal Retriever
  owns temporal validity; the Extractor MUST be kept out of any future
  code path that re-introduces time-based filtering.
- `evidence_text` is **lowercased** per the spec. Character offsets
  (`start_char`, `end_char`) refer to the **original** `news_text`.
- `matched_keyword` may be `null` for the neutral fallback. `support_score`
  is `1.0` for keyword matches and `0.5` for neutral.
- `evidence_id` format is `<news_id>_E<index>` zero-padded to 3 digits
  (e.g. `N001_E001`).
- `extraction_method` is always the literal `"rule_based_keyword"`.

### Keyword dictionary — single source of truth

The polarity and direction tables live in `src/evidence_extractor.py` as
module-level constants:

- `POSITIVE_KEYWORDS`, `NEGATIVE_KEYWORDS`, `KEYWORDS`, `KEYWORD_TO_POLARITY`
- `POLARITY_TO_DIRECTION`, `SUPPORT_SCORES`

Future modules (Evidence Selector, Counterevidence Coverage, Forecast Model)
MUST import from this module rather than redefining polarity rules.

### Sample I/O

Five golden fixtures live under `samples/evidence_extractor/` (one
`_input.json` and one `_expected.json` per scenario). A regression test in
`tests/test_evidence_extractor.py` asserts byte-equality on every pair.

## Evidence Selector

The Evidence Selector takes a Forecast Model prediction plus the Evidence
Extractor's candidate list and classifies each candidate as `pro`,
`counter`, or `neutral` evidence using a deterministic rule-based mapping.
The selector is intentionally non-ML: no LLM, no FinBERT, no training, no
network access.

### Why it exists

A one-sided explanation — only evidence that supports the prediction —
hides conflicts. The selector exists to make counterevidence a first-class
output so the Faithfulness Evaluator and Dashboard can surface a balanced
view.

### Classification

| prediction | evidence.expected_direction | selector_label |
| ---------- | --------------------------- | -------------- |
| UP         | UP                          | pro            |
| UP         | DOWN                        | counter        |
| UP         | HOLD                        | neutral        |
| DOWN       | DOWN                        | pro            |
| DOWN       | UP                          | counter        |
| DOWN       | HOLD                        | neutral        |
| HOLD       | HOLD                        | pro            |
| HOLD       | UP or DOWN                  | counter        |

### Single prediction

```python
from src import select_evidence

request = {
    "ticker": "AAPL",
    "forecast_time": "2025-03-12 09:00",
    "prediction": "UP",
    "confidence": 0.82,
    "evidence_candidates": [
        {
            "news_id": "N001",
            "ticker": "AAPL",
            "news_time": "2025-03-11 08:30",
            "evidence_text": "Apple launches new product",
            "polarity": "positive",
            "expected_direction": "UP",
            "extractor_score": 0.9,
        },
        {
            "news_id": "N002",
            "ticker": "AAPL",
            "news_time": "2025-03-11 10:00",
            "evidence_text": "iPhone sales in China decline",
            "polarity": "negative",
            "expected_direction": "DOWN",
            "extractor_score": 0.85,
        },
    ],
}

result = select_evidence(request)
# result["pro_evidence"], result["counterevidence"], result["neutral_evidence"]
# result["invalid_future_evidence"], result["summary"], result["selection_method"]
```

### Batch

```python
from src import select_evidence_batch

results = select_evidence_batch([request_a, request_b, request_c])
# One result per input, in input order.
```

### Contract notes for downstream modules

- **Inputs**: `prediction` must be `UP` / `DOWN` / `HOLD`; `evidence_candidates`
  must be a list. Anything else raises `EvidenceSelectorError`.
- **Outputs**: `pro_evidence`, `counterevidence`, `neutral_evidence`,
  `invalid_future_evidence` are always lists (never `None`), sorted by
  `selector_score` descending, truncated to `top_k` per group.
- **Counts**: `summary.pro_count` / `counter_count` / `neutral_count` use the
  *pre-truncation* totals so the Faithfulness Evaluator's coverage metric
  is not biased by display limits.
- **Future evidence**: a candidate with `news_time > forecast_time` is
  surfaced in `invalid_future_evidence` and excluded from pro/counter/
  neutral. Naive timestamps are interpreted as UTC.
- **Label leakage**: the selector never reads a ground-truth label. Even
  if a candidate carries an extra `ground_truth_label` or `actual` field,
  classification is based on `expected_direction` only, and those fields
  are stripped from the output.
- **`compute_coverage`**: optional helper for the Faithfulness Evaluator;
  derive Counterevidence Coverage from a caller's `expected_labels` dict,
  never from the input candidates.

### Configuration

| kwarg           | default | notes                          |
| --------------- | ------- | ------------------------------ |
| `top_k_pro`     | 3       | per-group cap on pro evidence  |
| `top_k_counter` | 3       | per-group cap on counter       |
| `top_k_neutral` | 3       | per-group cap on neutral       |

### Sample I/O

Three golden fixtures live under `samples/evidence_selector/` (one
`_input.json` and one `_expected.json` per scenario). A regression test in
`tests/test_evidence_selector.py` asserts byte-equality on every pair. The
UP fixture exercises every output list — pro, counter, neutral, and
`invalid_future_evidence` — in a single run.

### Limitations

- Rule-based classification can misfire on nuanced, mixed-sentiment, or
  sarcastic news where `expected_direction` does not capture the full
  intent.
- Ranking uses `extractor_score` only in V1. The `selector_score` field is
  kept as a single point of future extension for
  `extractor_score * keyword_strength * recency_weight`.
- `top_k` truncation silently drops items beyond the cap. Downstream
  consumers that need to know the pre-truncation count must read
  `summary.pro_count` / `counter_count` / `neutral_count`.
- The selector does not validate the `confidence` field. It is preserved
  verbatim in the output for the Faithfulness Evaluator to use.

## Disclaimer

This project is for research and learning. It is not a trading system and does
not provide investment advice.
