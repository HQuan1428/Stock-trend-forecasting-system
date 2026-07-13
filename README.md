# Faithful Evidence-Centric Financial News Forecasting

An academic prototype for forecasting stock movement from financial news while
evaluating whether the cited evidence is relevant, temporally valid, and
faithful to each prediction.

## Project status

Chuỗi stage tương tác được: 8 stage CLI độc lập + thin runner end-to-end, 8 envelope JSON trung gian + 6 output CSV, và các metric nâng cao (B1–B4). Toàn bộ logic là deterministic, rule-based, không dùng LLM/ML/GPU.

**Baseline (A1–A7):**

- `temporal-retriever` — lọc tin theo thời gian, đảm bảo không dùng tin tương lai.
- `evidence-extractor` — trích xuất evidence bằng keyword matching (V1/V2/V3 dictionary).
- `evidence-selector` — phân loại pro / counter / neutral evidence theo prediction.
- `forecast-model-basic` — rule-based voting: UP/DOWN/HOLD với confidence và rationale.
- `faithfulness-evaluator` — 3 metric: temporal_validity, evidence_support, confidence_drop.
- `interactive-stage-cli` — mỗi stage một CLI (`python -m src.<stage>`), accumulating JSON envelope, schema validation ở ranh giới stage, thin runner (`src/runner.py`).

**Nâng cao (B1–B4):**

- `phase-b2-counterevidence-coverage` — tính counterevidence_coverage và counterevidence_detected.
- `phase-b1-sufficiency-counterfactual` — sufficiency score (chỉ dùng cited evidence) và counterfactual delta (thay cited bằng neutral placeholder).
- `phase-b3-market-consistency-regime` — so sánh prediction với next_day_return, phân tích regime bull/bear/sideways.
- `phase-b4-agentic-sdlc-maturity` — trace log (run_log.json), 3 agent role, quality gate, reflection.

## Setup

```bash
pip install -r requirements.txt
```

## Run

### End-to-end (thin runner)

```bash
python -m src.runner --input data/sample_dataset.csv --output-dir outputs
# dừng sớm sau một stage:
python -m src.runner --input data/sample_dataset.csv --output-dir outputs --stop-after forecast_model
```

Runner chạy chuỗi stage in-process (cùng hàm `process()` mà CLI rời dùng),
ghi envelope trung gian `01_samples.json` … `08_market.json` rồi 6 CSV kết
quả vào `--output-dir`. Không LLM, FinBERT, transformer, GPU, hay external
API. Deterministic: chạy 2 lần → output byte-identical.

### Per-stage CLI (tương tác từng bước)

Output của stage này là input của stage sau — có thể `cat`/chỉnh file JSON
giữa các bước:

```bash
python -m src.ingest --input data/sample_dataset.csv -o outputs/01_samples.json
python -m src.retriever --input outputs/01_samples.json -o outputs/02_retrieved.json
python -m src.evidence_extractor --input outputs/02_retrieved.json -o outputs/03_evidence.json
python -m src.forecast_model --input outputs/03_evidence.json -o outputs/04_forecast.json
python -m src.evidence_selector --input outputs/04_forecast.json -o outputs/05_selected.json
python -m src.faithfulness_evaluator --input outputs/05_selected.json -o outputs/06_faithfulness.json
python -m src.sufficiency_evaluator --input outputs/06_faithfulness.json -o outputs/07_sufficiency.json
python -m src.market_analyzer --input outputs/07_sufficiency.json -o outputs/08_market.json
python -m src.export_csv --input outputs/08_market.json --output-dir outputs
```

Mỗi stage validate schema input ở ranh giới (thiếu key/sai type → message
nêu rõ `sample_id` + key lỗi, exit code 2). Envelope là accumulating: stage
chỉ bổ sung field (`forecast`, `selection`, `faithfulness`, ...), không xóa
field của stage trước.

### Output files

| File | Purpose |
|------|---------|
| `outputs/01_samples.json` … `08_market.json` | Envelope trung gian sau từng stage — inspect được toàn bộ state. |
| `outputs/prediction_results.csv` | One row per `(ticker, forecast_time)` group with `prediction`, `confidence`, `score`, `label`, `is_correct`, `rationale`, `cited_evidence_count`, `valid_news_count`, `invalid_future_news_count`. |
| `outputs/evidence_results.csv` | One row per extracted evidence item with `evidence_role` (`pro` / `counter` / `neutral`) and `is_cited` flag. |
| `outputs/faithfulness_results.csv` | One row per group with `original_confidence`, `confidence_without_cited_evidence`, `confidence_drop`, `temporal_validity`, `evidence_support`, `faithfulness_label` (`HIGH` / `MEDIUM` / `LOW`), `counterevidence_coverage`, `counterevidence_detected`. |
| `outputs/temporal_leakage_results.csv` | One row per news item with `news_time > forecast_time`; `leakage_type = future_news`. |
| `outputs/sufficiency_results.csv` | One row per group với `sufficiency_score` (chỉ dùng cited evidence), `prediction_on_only_cited`, `counterfactual_confidence`, `counterfactual_delta`. |
| `outputs/market_consistency_results.csv` | One row per group với `market_consistent`, `market_consistency_score`, `regime` (`bull` / `bear` / `sideways`), `next_day_return`, `price_5d_return`. |

## Dashboard

Dashboard Streamlit + Plotly, **read-only** trên envelope cuối
(`outputs/08_market.json`) — không gọi pipeline, không ghi file.

```bash
streamlit run src/dashboard/app.py
```

6 tab:

1. **🎬 Live Demo** — kịch bản demo 5 phút (ChuDe1.md §11.1): chọn ticker →
   chọn forecast date → tin hợp lệ (kèm cảnh báo tin tương lai bị loại) →
   prediction + phân rã vote UP/DOWN/HOLD → cited evidence + rationale →
   toggle "Remove cited evidence" so sánh confidence trước/sau (số liệu
   ablation đã tính sẵn ở faithfulness stage) → banner kết luận faithful.
2. **📊 Overview** — prediction distribution, accuracy, avg confidence/drop,
   accuracy theo ticker.
3. **📄 Evidence** — bảng evidence toàn dataset, filter ticker/role/cited.
4. **🔍 Faithfulness** — confidence drop chart (màu HIGH/MEDIUM/LOW) +
   radar 5 trục (temporal validity, evidence support, normalized drop,
   sufficiency B1, coverage B2).
5. **⏰ Temporal Leakage** — banner mức độ + bảng tin vi phạm sort theo
   leakage_minutes.
6. **🧪 B-metrics** — B1 sufficiency/counterfactual, B2 coverage,
   B3 market consistency/regime, B4 agent trace log.

### Export figure PNG cho báo cáo

Mỗi biểu đồ Plotly có nút camera (📷 *Download plot as png*) ở góc trên
phải — dùng nó để xuất 4 hình cho `outputs/figures/`:
`prediction_distribution.png` (tab Overview), `confidence_drop.png` và
`faithfulness_radar.png` (tab Faithfulness), `temporal_leakage_warning.png`
(chụp banner + bảng tab Temporal Leakage).

## Tests

```bash
pytest tests/
```

## Temporal Retriever

The Temporal Retriever is the first stage of the pipeline. It guarantees that
no news published **after** a forecast moment can ever reach a downstream
module.

```python
from src import TemporalRetriever

result = TemporalRetriever().retrieve(
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
from src import EvidenceExtractor

result = EvidenceExtractor().extract({
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
results = EvidenceExtractor().extract_batch([item1, item2, item3])
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
from src import EvidenceSelector

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

result = EvidenceSelector().select(request)
# result["pro_evidence"], result["counterevidence"], result["neutral_evidence"]
# result["invalid_future_evidence"], result["summary"], result["selection_method"]
```

### Batch

```python
results = EvidenceSelector().select_batch([request_a, request_b, request_c])
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

## Forecast Model

The Forecast Model is the fourth stage. It receives a single forecast
request (one per `sample_id`) and a list of **selected, valid evidence**
already filtered by the Temporal Retriever and classified by the Evidence
Selector, and emits a deterministic `UP` / `DOWN` / `HOLD` prediction
with a stable confidence, evidence counts, pro and counter evidence
lists, a template-based rationale, and a structured warnings list.

Version 1 is **rule-based, deterministic, and traceable**. It does NOT
use any LLM, FinBERT, transformer model, logistic regression,
deep-learning model, external API, or price features. Rationale is
selected from a small fixed set of string templates.

### Algorithm

```
positive_count = |{ e : e.expected_direction == "UP" }|
negative_count = |{ e : e.expected_direction == "DOWN" }|
neutral_count  = |{ e : e.expected_direction == "HOLD" }|
score          = positive_count - negative_count

if score  > 0: prediction = "UP"
elif score < 0: prediction = "DOWN"
else:           prediction = "HOLD"

confidence         = 0.5 + min(abs(score) * 0.1, 0.45)   clamped to [0.5, 0.95]
evidence_strength  = abs(score) / (positive_count + negative_count)  (0 when denom is 0)
conflict_ratio     = min(positive_count, negative_count) / max(positive_count + negative_count, 1)
```

Neutral evidence (`expected_direction = "HOLD"`) does not move the score
but is preserved in `neutral_evidence` for traceability.

**`class_confidences`** — a deterministic UP/DOWN/HOLD vote breakdown
(sums to 1.0, `class_confidences[prediction] == confidence`), computed
purely from `positive_count`/`negative_count`/`neutral_count`: the
winning class keeps `confidence`; the remainder (`1.0 - confidence`)
splits between the two other classes proportionally to their own
counts (even split when both are zero). This is a rule-based
descriptive breakdown, **not a calibrated probability** — it exists so
the dashboard's Live Demo tab can show "how the vote actually split"
instead of only the winning class's confidence. Persisted as
`class_confidence_up` / `class_confidence_down` / `class_confidence_hold`
in `prediction_results.csv`.

### Input schema

| Field           | Type   | Required | Description |
|-----------------|--------|----------|-------------|
| `sample_id`     | string | yes      | Stable identifier; echoed in output. |
| `ticker`        | string | yes      | Stock ticker; echoed in output. Not used as a filter. |
| `forecast_time` | string | yes      | Naive ISO timestamp (interpreted as UTC). Compared to each `evidence[].news_time`. |
| `evidence`      | list   | yes      | List of selected evidence items. May be empty. |
| `label`         | string | no       | Ground-truth label (`UP` / `DOWN` / `HOLD`) for evaluation. **MUST NOT** be read by `predict`. |

Each evidence item requires `evidence_id`, `news_id`, `news_time`,
`evidence_text`, `polarity`, and `expected_direction`. `support_score` is
optional (defaulted to `0.0` in the output).

### Output schema

The result is a `ForecastResult` dict with `sample_id`, `ticker`,
`forecast_time`, `prediction`, `confidence`, `score`, the four
counts (`positive_count`, `negative_count`, `neutral_count`,
`total_evidence`, `directional_evidence_count`), the two derived metrics
(`evidence_strength`, `conflict_ratio`), the five evidence lists
(`pro_evidence`, `counter_evidence`, `up_evidence`, `down_evidence`,
`neutral_evidence`), `rationale`, `warnings`, and `model_version` (the
literal string `"rule_based_v1"`).

All five evidence lists are always lists (never `null`), sorted by
`evidence_id` ascending. `warnings` is always present and may be empty.

### Rationale templates

| Branch | Template |
|--------|----------|
| `prediction = UP`   | `"Prediction UP because positive evidence count ({positive_count}) is greater than negative evidence count ({negative_count})."` |
| `prediction = DOWN` | `"Prediction DOWN because negative evidence count ({negative_count}) is greater than positive evidence count ({positive_count})."` |
| `prediction = HOLD`, `directional_evidence_count > 0` | `"Prediction HOLD because positive and negative evidence are balanced."` |
| `prediction = HOLD`, `directional_evidence_count == 0` | `"Prediction HOLD because positive and negative evidence are balanced or no valid directional evidence is available."` |

The same templates are exposed as the `RATIONALE_TEMPLATES` constant in
`src.forecast_model` so downstream modules import them rather than
redefining the literal strings.

### Single prediction

```python
from src import ForecastModel

request = {
    "sample_id": "S0001",
    "ticker": "AAPL",
    "forecast_time": "2025-03-12 09:00",
    "label": "UP",
    "evidence": [
        {
            "evidence_id": "N001_E001",
            "news_id": "N001",
            "news_time": "2025-03-11 08:30",
            "evidence_text": "strong sales",
            "polarity": "positive",
            "expected_direction": "UP",
            "support_score": 1.0,
        },
        # ... more evidence items
    ],
}

result = ForecastModel().predict(request)
# result["prediction"], result["confidence"], result["score"],
# result["pro_evidence"], result["counter_evidence"],
# result["rationale"], result["warnings"], result["model_version"]
```

### Faithfulness support

```python
# Re-run the forecast after removing cited evidence. Used by the
# Faithfulness Evaluator to compute confidence_drop.
reduced = ForecastModel().predict_without_evidence(request, ["N001_E001", "N002_E001"])

confidence_drop = original["confidence"] - reduced["confidence"]
```

### Batch and CSV

```python
model = ForecastModel()
results = model.predict_batch([r1, r2, r3])
# One result per input, in input order.
# By default a CSV is written to outputs/prediction_results.csv and
# a JSON sibling to outputs/prediction_results.json. Pass
# output_csv_path=None / output_json_path=None to disable either.

metrics = model.compute_accuracy_and_confusion(results)
# metrics["accuracy"], metrics["confusion_matrix"], metrics["per_class"], metrics["n_samples"]
```

The CSV header is fixed and matches `CSV_COLUMNS` in `src.forecast_model`:
`sample_id`, `ticker`, `forecast_time`, `prediction`, `confidence`,
`score`, `positive_count`, `negative_count`, `neutral_count`,
`total_evidence`, `directional_evidence_count`, `evidence_strength`,
`conflict_ratio`, `label`, `model_version`.

### Contract notes for downstream modules

- **No raw news**: the model MUST NOT read `news_text`, `title`, or any
  other raw-news field. It consumes evidence already validated by the
  upstream pipeline.
- **No `label` during prediction**: `predict` echoes `label` to the
  result for the evaluation helper; it never reads it for scoring.
- **Defense in depth**: every evidence item's `news_time` is compared to
  `forecast_time`. Future items are excluded and reported as
  `TEMPORAL_LEAKAGE_BLOCKED` warnings. This is intentionally redundant
  with the Temporal Retriever.
- **Defensive defaults**: bad evidence items (`INVALID_EVIDENCE`,
  `DUPLICATE_EVIDENCE_ID`, `MALFORMED_NEWS_TIME`) are skipped with
  warnings; `predict_batch` catches `ForecastModelError` per record and
  substitutes a default `HOLD` result with an `INPUT_ERROR` warning.
  Use `strict=True` to raise on invalid `expected_direction`.
- **Determinism**: identical inputs produce byte-equal outputs
  (`json.dumps(result, sort_keys=True)` is stable). The order of items
  within each evidence list is `evidence_id` ascending.

### Limitations

- **Integer-only score**: there is no `support_score` weighting, no
  keyword weighting, and no recency weighting. Five weak positive items
  look the same as one strong positive. The `evidence_strength` and
  `conflict_ratio` fields expose the same information at a glance.
- **Confidence saturation**: confidence saturates at `abs(score) = 5`
  (`0.95`). Beyond that, additional evidence does not change
  confidence.
- **Templated rationale**: the rationale is intentionally templated (no
  nuance, no LLM). A non-technical reader may interpret "positive
  evidence count (1) is greater than negative evidence count (0)" as
  stronger than a single match warrants.
- **V1 is not a trading system**: the model is intentionally weak. Its
  purpose is to be faithful to its cited evidence (every prediction
  derivable from the evidence it cites, every cited evidence removable
  via `predict_without_evidence`), not to be accurate.
- **V2 extension point**: keyword strength and recency weighting are
  documented as future work and would change the algorithm but not the
  public API contract (`model_version` becomes the filter key).

## Faithfulness Evaluator

The Faithfulness Evaluator is the fifth stage. Given a `ForecastResult`
from the Forecast Model and the input envelope that produced it, it
answers the central research question: **"When the model cites evidence
for its prediction, does that evidence actually influence the
prediction?"**

Version 1 is **deterministic, rule-based, and side-effect-free in
single-evaluation mode**. It does NOT use any LLM, FinBERT, transformer
model, logistic regression, deep-learning model, or external API. It
does NOT re-extract or re-classify evidence. It re-invokes
`src.forecast_model.predict_without_evidence` for the ablation pass and
otherwise operates on the result it is given.

### Three required metrics

| Metric               | Formula                                                                                                                                       |
|----------------------|-----------------------------------------------------------------------------------------------------------------------------------------------|
| `temporal_validity`  | `1.0` if every cited evidence item has `news_time <= forecast_time`; `0.0` if any item has `news_time > forecast_time`; `1.0` for empty list. |
| `evidence_support`   | Mean of per-item support scores (`1.0` exact match, `0.5` HOLD vs. UP/DOWN, `0.0` opposite). `1.0` for empty list.                          |
| `confidence_drop`    | `original_confidence - confidence_after_removal`. Signed; may be negative. A `confidence_increased_after_removal` warning is added when negative. |

### Optional composite score (V1 heuristic)

```
normalized_drop = min(max(confidence_drop, 0.0) / 0.30, 1.0)
faithfulness_score = 0.35 * temporal_validity
                   + 0.30 * evidence_support
                   + 0.35 * normalized_drop
```

`faithfulness_score` is in `[0.0, 1.0]`. Negative `confidence_drop` is
clamped to `0.0` for the composite; the signed drop is preserved in the
report. **The composite is documented as a V1 dashboard heuristic, not
a scientifically validated metric.** `confidence_drop` is the primary
signal.

### Verdict cascade

```
temporal_validity < 1.0          → invalid_temporal_leakage
evidence_support  < 0.5           → unsupported_evidence
cited_evidence is empty           → decorative_explanation_risk
prediction_after_removal != prediction → strong_faithful_candidate
confidence_drop >= 0.20           → strong_faithful_candidate
confidence_drop >= 0.10           → moderate_faithful_candidate
confidence_drop >= 0.05           → weak_faithful_candidate
otherwise                         → decorative_explanation_risk
```

The six labels are exposed as the `VERDICTS` constant
(`frozenset`).

### Ablation strategies

| Strategy                    | Description                                                                                                |
|-----------------------------|------------------------------------------------------------------------------------------------------------|
| `remove_cited_pro_evidence` | Default. Removes every evidence item whose `evidence_id` is in `pro_evidence` (the supporting evidence).    |
| `remove_all_cited_evidence` | Removes every evidence item whose `evidence_id` is in `pro_evidence` OR `counter_evidence`.                |

When the Forecast Model only accepts news-level input, the
`evidence_id` set is collapsed to a `news_id` set and the expansion is
recorded in `ablation_warnings` as
`"COLLAPSED_BY_NEWS_ID: <news_id> (expanded from <evidence_id_list>)"`.

### Single evaluation

```python
from src import FaithfulnessEvaluator, ForecastModel

request = {
    "sample_id": "S0001",
    "ticker": "AAPL",
    "forecast_time": "2025-03-12 09:00",
    "label": "UP",
    "evidence": [
        {
            "evidence_id": "N001_E001",
            "news_id": "N001",
            "news_time": "2025-03-11 08:30",
            "evidence_text": "strong sales",
            "polarity": "positive",
            "expected_direction": "UP",
            "support_score": 1.0,
        },
        # ... more evidence items
    ],
}
result = ForecastModel().predict(request)
report = FaithfulnessEvaluator().evaluate(request, result)
# report["temporal_validity"], report["evidence_support"],
# report["confidence_drop"], report["faithfulness_score"],
# report["verdict"], report["per_evidence_results"],
# report["temporal_warnings"], report["support_warnings"],
# report["ablation_warnings"]
```

### Batch evaluation and CSV/JSON export

```python
from src import FaithfulnessEvaluator, ForecastModel

records = [request1, request2, request3]
results = ForecastModel().predict_batch(records, output_csv_path=None)
reports = FaithfulnessEvaluator().evaluate_batch(
    list(zip(records, results)),
    output_csv_path="outputs/faithfulness_results.csv",
    output_json_path="outputs/faithfulness_results.json",
)
```

The CSV header is the `CSV_COLUMNS` constant from `src.faithfulness_evaluator`:

```
ticker, forecast_time, prediction, original_confidence,
prediction_after_removal, confidence_after_removal, confidence_drop,
temporal_validity, evidence_support, faithfulness_score,
verdict, warnings
```

The `warnings` column is the JSON encoding of the concatenated
`temporal_warnings + support_warnings + ablation_warnings` lists.

### Limitations

- **Composite is a heuristic**: the V1 `faithfulness_score` is a
  weighted blend of three sub-metrics; the `confidence_drop` is the
  primary signal and the composite is for at-a-glance dashboard
  display.
- **Verdict cascade is fixed**: thresholds (`0.05`, `0.10`, `0.20`) are
  pinned in the spec and not configurable in V1. A future change can
  expose them as parameters without breaking the existing verdicts.
- **Single-ticker, single-ablation**: each `evaluate(...)` call is
  independent and uses a single ablation strategy. Leave-one-out
  per-evidence ablation is documented as a V2 extension point.
- **Re-invokes the Forecast Model**: the evaluator doubles the runtime
  per evaluation (one call to `predict`, one to
  `predict_without_evidence`). For a 100-row batch this is acceptable.
- **V1 is not a calibration**: the evaluator is a deterministic function
  of the result and the model; it is not a probabilistic faithfulness
  estimator.

## Agentic SDLC

Dự án áp dụng mô hình **Agentic AI trong SDLC**: AI agent hỗ trợ từng bước của vòng đời phát triển phần mềm, nhưng con người luôn kiểm soát và review trước khi accept.

### Ba agent role

| Role | Nhiệm vụ | Bước SDLC |
|------|----------|-----------|
| **Research Agent** | Phân tích bài toán, xác định metric gap, viết `proposal.md` cho từng change (B1–B4) | Requirement, Design |
| **Coding Agent** | Implement module theo spec (`sufficiency_evaluator.py`, `market_analyzer.py`, `agent_trace.py`, stage CLI/runner) | Implementation |
| **Testing/Review Agent** | Sinh test case, chạy pytest, verify output CSV, review code | Testing, Evaluation |

### Quality gates

Mỗi change trong `openspec/changes/` phải qua các gate trước khi được merge:

1. **Spec review** — proposal.md và design.md phải được con người đọc và approve.
2. **pytest pass** — toàn bộ `pytest tests/` phải green.
3. **Runner smoke test** — `python -m src.runner --input data/sample_dataset.csv --output-dir outputs` không lỗi.
4. **Output review** — output CSV được kiểm tra cột, kiểu dữ liệu, và giá trị mẫu.

### Minh chứng

- `src/agent_trace.py` — API trace log (write/load/summarize) cho 3 role.
- `openspec/changes/phase-b4-agentic-sdlc-maturity/reflection.md` — phân tích lessons learned từ Agentic SDLC.
- `openspec/changes/` — mỗi thư mục có `proposal.md`, `design.md`, `tasks.md` là bằng chứng spec-driven workflow.

Con người không để AI tự quyết định kiến trúc hay merge code — mỗi bước đều có checkpoint review rõ ràng.

## Disclaimer

This project is for research and learning. It is not a trading system and does
not provide investment advice.
