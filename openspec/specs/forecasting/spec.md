# Forecast Model — Spec (Version 3 / attention_evidence_v1)

This spec defines the behavior of the **Forecast Model** module in the
Faithful Evidence-Centric Financial News Forecasting pipeline, after the
V3 replacement of the rule-based baseline with an ML stack:

- `src/stages/evidence_extractor.py` — **FinBERT** (ProsusAI/finbert,
  frozen) classifier trên mỗi `evidence_text` → sinh
  `sentiment_probs = {"positive": p, "negative": p, "neutral": p}`.
- `src/stages/forecast_model.py` — **Attention Evidence Aggregator**
  (PyTorch `nn.Module`, trainable, checkpoint
  `models/evidence_aggregator_v1.pt`). V2 frozen logreg đã xoá hoàn toàn.

V3 không còn deterministic byte-for-byte (PyTorch + FinBERT inference có
sai số float platform-dependent), nhưng **seed reproducible**: cùng
input + cùng checkpoint → output giống hệt trong tolerance `1e-6` float
(nhờ `model.eval() + torch.no_grad() + torch.manual_seed(SEED=42)`).

---

## Input Schema

The module SHALL accept a single forecast request with the following fields:

| Field           | Type   | Required | Description |
|-----------------|--------|----------|-------------|
| `sample_id`     | string | yes      | Stable identifier. Echoed. |
| `ticker`        | string | yes      | Stock ticker. Echoed. Not used as a filter. |
| `forecast_time` | string | yes      | ISO 8601 / "YYYY-MM-DD HH:MM" string. Naive = UTC. Compared against each `evidence[].news_time`. |
| `evidence`      | list   | yes      | List of evidence items (FinBERT-extracted). May be empty. Each item carries `evidence_id`, `news_id`, `news_time`, `evidence_text`, `polarity`, `expected_direction`, `support_score`, `sentiment_probs`. |
| `label`         | string | no       | Ground-truth label (`UP` / `DOWN` / `HOLD`). Echoed; NEVER read by `predict()`. |

---

## Output Schema

The module SHALL return a `ForecastResult` dict with the following fields:

| Field                          | Type    | Description |
|--------------------------------|---------|-------------|
| `sample_id`                    | string  | Same as input. |
| `ticker`                       | string  | Same as input. |
| `forecast_time`                | string  | Same as input. |
| `prediction`                   | string  | One of `"UP"`, `"DOWN"`, `"HOLD"`. |
| `confidence`                   | number  | `class_confidences[prediction]`. |
| `class_confidences`            | object  | `{"UP": float, "DOWN": float, "HOLD": float}`. Sum within float tolerance of `1.0`. |
| `score`                        | integer | Reserved placeholder (`0`); retained for schema compat. |
| `positive_count`               | integer | Count of items with `expected_direction = "UP"`. |
| `negative_count`               | integer | Count of items with `expected_direction = "DOWN"`. |
| `neutral_count`                | integer | Count of items with `expected_direction = "HOLD"`. |
| `total_evidence`               | integer | Count of items considered for scoring. |
| `directional_evidence_count`   | integer | `positive_count + negative_count`. |
| `pro_evidence`                 | list    | Items supporting the prediction. Never `null`. |
| `counter_evidence`             | list    | Items conflicting with the prediction. Never `null`. |
| `up_evidence`                  | list    | All items with `expected_direction = "UP"`. Never `null`. |
| `down_evidence`                | list    | All items with `expected_direction = "DOWN"`. Never `null`. |
| `neutral_evidence`             | list    | All items with `expected_direction = "HOLD"`. Never `null`. |
| `rationale`                    | string  | `"Attention model: top evidence {eids}, attention weight={w:.4f}"`. Deterministic, template-based. |
| `warnings`                     | list    | Structured warning entries. Always present. |
| `model_version`                | string  | MUST be the literal `"attention_evidence_v1"`. |

`evidence_strength` và `conflict_ratio` đã xoá ở V3.

---

## V3 Algorithm

### Feature extraction per evidence item (7-dim)

| Index | Feature            | Source                              |
|------:|--------------------|-------------------------------------|
|   0   | `pos_prob`         | `sentiment_probs["positive"]`       |
|   1   | `neg_prob`         | `sentiment_probs["negative"]`       |
|   2   | `neutral_prob`     | `sentiment_probs["neutral"]`        |
|   3   | `support_score`    | `support_score` (FinBERT max prob)  |
|   4   | `dir_up`           | `1.0` if `expected_direction == "UP"`, else `0.0` |
|   5   | `dir_down`         | same for `"DOWN"`                   |
|   6   | `dir_hold`         | same for `"HOLD"`                   |

### Price features (2-dim, sample-level)

`[price_5d_return, volume_change]` — both default to `0.0` if missing on the
sample. Sourced from `B3` columns in the input CSV (already canonicalized by
`ingest.py`).

### Forward pass

```python
class AttentionEvidenceAggregator(nn.Module):
    def __init__(self):
        super().__init__()
        self.proj = nn.Linear(7, 32)
        self.attn = nn.Linear(32, 1)
        self.head = nn.Sequential(
            nn.Linear(34, 16),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(16, 3),
        )

    def forward(self, evidence_features, price_features):
        if evidence_features.shape[0] == 0:
            group = torch.zeros(32)
        else:
            h = self.proj(evidence_features)
            scores = self.attn(h)
            weights = torch.softmax(scores, dim=0)
            group = (weights * h).sum(dim=0)
        combined = torch.cat([group, price_features])
        logits = self.head(combined)
        return F.softmax(logits, dim=-1)
```

### Deterministic prediction

```python
torch.manual_seed(SEED)  # SEED = 42
model.eval()
with torch.no_grad():
    class_probs = self.model(evidence_features, price_features)
prediction = argmax(class_probs) with tie-break UP > DOWN > HOLD
confidence = class_probs[prediction]
```

---

## Pro / Counter Evidence (unchanged from V1)

| `prediction` | `pro_evidence`           | `counter_evidence`       |
|--------------|--------------------------|--------------------------|
| `UP`         | items with `expected_direction = "UP"`   | items with `expected_direction = "DOWN"` |
| `DOWN`       | items with `expected_direction = "DOWN"` | items with `expected_direction = "UP"`   |
| `HOLD`       | `[]`                     | `[]`                     |

The three raw groups (`up_evidence`, `down_evidence`, `neutral_evidence`)
SHALL always be populated regardless of `prediction`. All four evidence
lists SHALL be sorted by `evidence_id` ascending.

---

## Rationale

Template:
```
"Attention model: top evidence {eids}, attention weight={w:.4f}"
```
where `{eids}` is the comma-joined `evidence_id` of the top-3 evidence
items by attention weight (deterministic, sorted descending then by
`evidence_id` ascending), and `{w:.4f}` is the top-1 weight formatted to 4
decimals.

If there are no evidence items, rationale is `"Attention model: no evidence items"`.

---

## Temporal Safety

Same as V1:
- `news_time > forecast_time` (strict) → exclude from scoring, emit
  `TEMPORAL_LEAKAGE_BLOCKED` warning.
- `news_time == forecast_time` → include normally.
- `news_time` missing/unparseable → treat as not-future, emit
  `MALFORMED_NEWS_TIME` warning.
- `forecast_time` missing/unparseable → raise `ForecastModelError`.

---

## Defensive Handling of Bad Evidence

Same as V1:
- Missing/invalid `expected_direction` → ignore, emit `INVALID_EVIDENCE`
  warning (`strict=False`). Under `strict=True`, raise.
- Duplicate `evidence_id` → first wins, subsequent dropped,
  `DUPLICATE_EVIDENCE_ID` warning.

---

## Faithfulness Support

Same as V1: `predict_without_evidence(input_data, removed_evidence_ids)`
runs the same algorithm with the cited evidence filtered out before
forward pass. The `evidence_features` tensor size shrinks accordingly.
Faithfulness/S ufficiency evaluators can compute `confidence_drop` etc.

---

## Determinism (V3 semantics)

The system SHALL be **seed-reproducible**, not byte-identical. Given:

- identical input envelope
- identical checkpoint `models/evidence_aggregator_v1.pt`
- identical runtime (`torch.manual_seed(SEED)`, `model.eval()`,
  `torch.no_grad()`)

the system SHALL produce a result whose scalar fields agree within float
tolerance `1e-6` across two runs on the same machine. Cross-machine
byte-equality is NOT guaranteed.

`torch.use_deterministic_algorithms(True)` is NOT required (softmax is
already deterministic under `eval()`).

---

## Model Version

Every result SHALL include `model_version = "attention_evidence_v1"`.

---

## ADDED Requirements

### Requirement: FinBERT polarity replaces keyword matching

The `src/stages/evidence_extractor.py` module MUST classify each evidence
text using FinBERT (`ProsusAI/finbert`) instead of the V1 keyword list.
The output evidence item MUST include `sentiment_probs` mapping
`{"positive", "negative", "neutral"}` to non-negative floats summing to
`1.0 ± 1e-6`.

### Scenario: FinBERT-extracted evidence carries sentiment_probs

- **WHEN** `extract()` is called on a non-empty `news_text`
- **THEN** each output evidence item SHALL have a `sentiment_probs` field
      with three float values summing to `1.0 ± 1e-6`
- **AND** `polarity` SHALL equal `"positive"` /
      `"negative"` / `"neutral"` based on the argmax of `sentiment_probs`
- **AND** `expected_direction` SHALL map to `"UP"` / `"DOWN"` / `"HOLD"`
      via the canonical `POLARITY_TO_DIRECTION` table

### Requirement: Forecast Model uses frozen Attention Evidence Aggregator

The `src/stages/forecast_model.py` module MUST be implemented as a PyTorch
`AttentionEvidenceAggregator` (see *V3 Algorithm*). Runtime prediction
MUST:
- Load `models/evidence_aggregator_v1.pt` at construction time. File
  missing → raise `ForecastModelError`.
- Set `torch.manual_seed(42)`, `model.eval()`, `torch.no_grad()` inside
  `_predict_core`.
- Emit a `ForecastResult` dict matching the V3 output schema.

### Scenario: Empty evidence still produces a valid prediction

- **WHEN** `evidence` list is `[]` (or filtered to empty after temporal/dedup)
- **THEN** the forward pass uses a zero group vector (`torch.zeros(32)`),
      combined with price features
- **AND** output `prediction` is one of `"UP"` / `"DOWN"` / `"HOLD"`
- **AND** `sum(class_confidences.values()) == 1.0 ± 1e-6`

### Scenario: Determinism via seed

- **WHEN** `predict()` is called twice with identical input on the same
      checkpoint
- **THEN** the two result dicts SHALL have all scalar fields equal within
      `1e-6` float tolerance

### Requirement: Public API of ForecastModel is unchanged

The methods `predict()`, `predict_without_evidence()`, `predict_batch()`,
`compute_accuracy_and_confusion()`, `build_forecast_request()`, and
`process()` MUST keep their signatures and return types compatible with the
V1 baseline (any consumer reading these is unaffected by the V3 rewrite,
apart from `model_version = "attention_evidence_v1"` and the
removed `evidence_strength` / `conflict_ratio` fields).

### Requirement: No LLM, no external API at runtime

The pipeline MUST NOT call any LLM, external sentiment API, or external
service at runtime. FinBERT weights are loaded from the local
`models/finbert/` cache only; if the local cache is missing, FinBERT SHALL
raise `FinbertLoadError` and the pipeline MUST surface the failure with a
typed error rather than silently regressing to keyword matching.

### Requirement: Pipeline envelopes preserve `forecast` schema

`sample["forecast"]` after the `forecast_model` stage SHALL have all the
fields listed in the V3 *Output Schema* and SHALL NOT gain or lose keys
across the V3 transition (consumers downstream read these fields by name).

### Scenario: Runner produces 8 envelopes end-to-end with V3

- **WHEN** `python -m src.runner --input data/real_dataset.csv --output-dir X`
      runs to completion
- **THEN** `X/04_forecast.json` SHALL contain a `forecast` dict for every
      sample, each with `model_version = "attention_evidence_v1"`
- **AND** `X/05_selected.json` through `X/08_market.json` SHALL all
      load successfully and pass downstream validation
