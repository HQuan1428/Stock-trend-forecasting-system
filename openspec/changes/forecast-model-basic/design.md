# Forecast Model — Design (Version 1)

## Context

The Faithful Evidence-Centric Financial News Forecasting pipeline currently has three upstream modules (Temporal Retriever, Evidence Extractor, Evidence Selector) that together produce a list of validated evidence for one forecast request. After they run, the system has no module that emits a stock-movement prediction. Without a Forecast Model:

- The pipeline cannot produce a baseline `UP / DOWN / HOLD` output, so the dashboard has nothing to display.
- The Faithfulness Evaluator cannot measure `confidence_drop` after removing cited evidence, because there is no prediction to re-run.
- The batch evaluation step has no labels-vs-predictions structure to compute accuracy or a confusion matrix.

Version 1 of the Forecast Model is intentionally simple. It receives only the **selected evidence** (and the `sample_id`, `ticker`, `forecast_time` envelope). It does **not** read raw `news_text`, it does **not** call any model, and it does **not** consult price data. The pipeline order becomes:

```
News + Price Data
  → Temporal Retriever       (owns temporal validity)
  → Evidence Extractor       (owns per-phrase evidence)
  → Evidence Selector        (owns pro/counter/neutral classification)
  → Forecast Model           (owns prediction + confidence + rationale)  ← this change
  → Faithfulness Evaluator   (consumes prediction; runs ForecastModel.predict_without_evidence)
  → Visualization Dashboard  (consumes prediction + evaluation metrics)
```

The reason for that order is deliberate: the Forecast Model never sees the raw news. Every prediction must be a deterministic function of the evidence it cites, and the Faithfulness Evaluator can drop one or more cited evidence IDs and re-run the model to get a counterfactual confidence.

## Goals / Non-Goals

**Goals**

- Provide a deterministic `predict(input_data) -> ForecastResult` function that emits a `UP / DOWN / HOLD` prediction, a stable confidence in `[0.5, 0.95]`, a numeric score, evidence counts, `evidence_strength`, `conflict_ratio`, `pro_evidence`, `counter_evidence`, a deterministic template-based `rationale`, and a `warnings` list.
- Expose `ForecastModel.predict_batch(records) -> list[ForecastResult]` that returns one result per input, in input order, and additionally persists the scalar fields of every result to `outputs/prediction_results.csv` for the dashboard.
- Expose `ForecastModel.predict_without_evidence(input_data, removed_evidence_ids) -> ForecastResult` so the Faithfulness Evaluator can compute `confidence_drop = original.confidence - new.confidence` after removing one or more cited evidence IDs.
- Compute `evidence_strength = abs(score) / directional_evidence_count` and `conflict_ratio = min(positive_count, negative_count) / max(positive_count + negative_count, 1)`. These are the V1 faithfulness-friendly summaries; the Evidence Selector covers the per-item classification.
- Defend in depth against temporal leakage: any evidence item with `news_time > forecast_time` is excluded from scoring and produces a `TEMPORAL_LEAKAGE_BLOCKED` warning. The Temporal Retriever normally prevents this; the Forecast Model must not silently trust upstream.
- Deduplicate evidence by `evidence_id` (first occurrence wins, subsequent ones go to `warnings` as `DUPLICATE_EVIDENCE_ID`); ignore evidence with missing or invalid `expected_direction` (warning code `INVALID_EVIDENCE`).
- Ship a `ForecastModel.compute_accuracy_and_confusion(results, label_key="label") -> dict` helper that returns `accuracy`, `confusion_matrix` (3×3 over `UP/DOWN/HOLD`), `per_class`, and `n_samples`. This is the V1 evaluation surface used by the dashboard and the offline experiment scripts.
- Be fully testable with unit tests that pin the nine acceptance scenarios from the spec.

**Non-Goals**

- LLM-based prediction, FinBERT, transformer models, gradient-boosted trees, logistic regression, or any other learned model.
- External APIs, market data sources, news crawlers, or any network I/O.
- Price features. The pipeline does not have a price module yet, and Version 1 must not invent one. Voting on selected evidence is enough.
- Counterfactual reasoning, post-hoc explanation generation, or natural-language rationale synthesis by an LLM. Rationale is template-based.
- Calibrated probabilistic confidence (no Platt scaling, no isotonic regression, no temperature). The V1 confidence is a stable deterministic function of `abs(score)`.
- Multi-horizon forecasts, multi-ticker joint prediction, or per-keyword weighting. Each `ForecastModel.predict(...)` call is independent and single-ticker.
- Trading advice, buy/sell recommendations, or portfolio action.

## Data Contract

### Input

`ForecastModel.predict` and `ForecastModel.predict_without_evidence` accept one envelope:

```json
{
  "sample_id": "S0001",
  "ticker": "AAPL",
  "forecast_time": "2025-03-12 09:00",
  "evidence": [
    {
      "evidence_id": "N001_E001",
      "news_id": "N001",
      "news_time": "2025-03-11 08:30",
      "evidence_text": "strong sales",
      "polarity": "positive",
      "expected_direction": "UP",
      "support_score": 1.0
    }
  ],
  "label": "UP"
}
```

| Field           | Type   | Required | Description |
|-----------------|--------|----------|-------------|
| `sample_id`     | string | yes      | Stable identifier for the sample; echoed in output. |
| `ticker`        | string | yes      | Stock ticker. Echoed in output. Not used as a filter. |
| `forecast_time` | string | yes      | Datetime string at which the forecast is made. Used to validate `news_time`. |
| `evidence`      | list   | yes      | Selected evidence items. May be empty. |
| `label`         | string | no       | Ground-truth label (`UP` / `DOWN` / `HOLD`) for evaluation. NEVER read during `ForecastModel.predict`; ONLY read by `ForecastModel.compute_accuracy_and_confusion`. |

Each evidence item MUST have:

| Field               | Type   | Required | Description |
|---------------------|--------|----------|-------------|
| `evidence_id`       | string | yes      | Stable ID; deduplication key. |
| `news_id`           | string | yes      | Stable ID of the source news. |
| `news_time`         | string | yes      | Datetime string of publication. Compared to `forecast_time`. |
| `evidence_text`     | string | yes      | The matched phrase (preserved verbatim). |
| `polarity`          | string | yes      | One of `"positive"`, `"negative"`, `"neutral"`. |
| `expected_direction`| string | yes      | One of `"UP"`, `"DOWN"`, `"HOLD"`. The only input to voting. |
| `support_score`     | number | optional | Forwarded to output; not used in V1 scoring. |

The model MUST NOT read `news_text`, `title`, or any other raw-news field. It MUST NOT read `label`.

### Output

`ForecastModel.predict` returns a `ForecastResult` dict (also the type used by `ForecastModel.predict_batch` and `ForecastModel.predict_without_evidence`):

```json
{
  "sample_id": "S0001",
  "ticker": "AAPL",
  "forecast_time": "2025-03-12 09:00",
  "prediction": "UP",
  "confidence": 0.7,
  "score": 2,
  "positive_count": 3,
  "negative_count": 1,
  "neutral_count": 0,
  "total_evidence": 4,
  "directional_evidence_count": 4,
  "evidence_strength": 0.5,
  "conflict_ratio": 0.25,
  "pro_evidence":       [ { "evidence_id": "...", "expected_direction": "UP",   "...": "..." } ],
  "counter_evidence":   [ { "evidence_id": "...", "expected_direction": "DOWN", "...": "..." } ],
  "up_evidence":        [ ... ],
  "down_evidence":      [ ... ],
  "neutral_evidence":   [ ... ],
  "rationale": "Prediction UP because positive evidence count (3) is greater than negative evidence count (1).",
  "warnings": [],
  "model_version": "rule_based_v1"
}
```

All four evidence lists (`pro_evidence`, `counter_evidence`, `up_evidence`, `down_evidence`, `neutral_evidence`) are always present, sorted deterministically, and never `null` — they are `[]` when empty. `warnings` is always present and may be empty. The `model_version` field is the literal string `"rule_based_v1"` and is the single source of truth for downstream consumers that want to filter by version.

## Voting Algorithm

The voting algorithm is intentionally trivial and human-auditable. The score is the integer difference between the counts of UP-expected and DOWN-expected evidence; neutral evidence contributes zero and is preserved in the output but does not move the score.

```
positive_count = |{ e : e.expected_direction == "UP" }|
negative_count = |{ e : e.expected_direction == "DOWN" }|
neutral_count  = |{ e : e.expected_direction == "HOLD" }|
score          = positive_count - negative_count

if score  > 0: prediction = "UP"
elif score < 0: prediction = "DOWN"
else:           prediction = "HOLD"
```

The score is an **integer** in V1. There is no support_score weighting, no keyword weighting, no recency weighting. The rationale is that the same algorithm must be reproducible byte-for-byte from a different runtime, and integer arithmetic is the easiest contract to audit.

`directional_evidence_count = positive_count + negative_count`. The `HOLD` items are NOT counted as directional: they cannot move the score, so they are not part of the directional vote.

## Confidence Algorithm

Confidence is a deterministic function of `abs(score)`, clamped to `[0.5, 0.95]`:

```
if directional_evidence_count == 0:
    confidence = 0.5
else:
    confidence = 0.5 + min(abs(score) * 0.1, 0.45)
    confidence = max(0.5, min(0.95, confidence))
```

The minimum is `0.5` so we never claim to be more uncertain than a coin flip. The maximum is `0.95` so we never claim to be certain. The form `0.5 + min(abs(score) * 0.1, 0.45)` is monotonic in `abs(score)` and saturates at `abs(score) = 5` (`0.5 + 5*0.1 = 1.0` clipped to `0.95`). It deliberately does NOT use `total_evidence` in the denominator, because that would overstate confidence when there is only one piece of evidence: `abs(1)/1 = 1.0` becomes `1.0` confidence, which is too strong for a single-evidence prediction. Using only the absolute score keeps the curve interpretable and stable across different evidence counts.

**Worked examples** (matches the acceptance scenarios in the spec):

| positive | negative | neutral | score | abs(score) | confidence |
|---------:|---------:|--------:|------:|-----------:|-----------:|
| 3        | 1        | 0       | 2     | 2          | 0.70       |
| 1        | 3        | 0       | -2    | 2          | 0.70       |
| 2        | 2        | 0       | 0     | 0          | 0.50       |
| 0        | 0        | 4       | 0     | 0          | 0.50       |
| 0        | 0        | 0       | 0     | 0          | 0.50       |

The 0.5 floor is also used for `score == 0` even when there are zero directional items: the rationale template explicitly tells the user "balanced or no valid directional evidence", so a non-trivial confidence would contradict the rationale.

## Evidence Strength and Conflict Ratio

`evidence_strength` and `conflict_ratio` are V1 summaries that the Faithfulness Evaluator and dashboard can show without re-implementing the algorithm. They are both derived from the same counts as `score`.

```
evidence_strength = abs(score) / directional_evidence_count   (0 when denominator is 0)
conflict_ratio    = min(positive_count, negative_count)
                    / max(positive_count + negative_count, 1)
```

`evidence_strength = 1.0` means every directional evidence item points the same way (no conflict); `0.0` means the directional items are perfectly balanced. `conflict_ratio` answers the same question from the other side: `0.0` means one-sided support, `0.5` means perfectly balanced directional evidence (e.g., 1 UP and 1 DOWN).

## Pro / Counter Evidence

The output always preserves directional evidence in two roles, plus three raw groups for the dashboard:

| prediction | `pro_evidence`       | `counter_evidence`   | `up_evidence` | `down_evidence` | `neutral_evidence` |
|------------|----------------------|----------------------|---------------|-----------------|---------------------|
| UP         | UP items             | DOWN items           | UP items      | DOWN items      | HOLD items          |
| DOWN       | DOWN items           | UP items             | UP items      | DOWN items      | HOLD items          |
| HOLD       | `[]`                 | `[]`                 | UP items      | DOWN items      | HOLD items          |

For `HOLD`, `pro_evidence` and `counter_evidence` are `[]` because there is no winning direction. The three raw groups (`up_evidence`, `down_evidence`, `neutral_evidence`) are still emitted, sorted by `evidence_id` ascending, so the dashboard can show "what evidence the model considered" without re-computing the partition. The `pro_evidence` and `counter_evidence` lists are always sorted by `evidence_id` ascending too — the same convention as the Evidence Selector, so cross-module comparisons are stable.

## Rationale Templates

The rationale is built deterministically from a small set of string templates, NOT generated by an LLM. Three templates cover the three predictions:

| prediction | template |
|------------|----------|
| UP         | `"Prediction UP because positive evidence count ({positive_count}) is greater than negative evidence count ({negative_count})."` |
| DOWN       | `"Prediction DOWN because negative evidence count ({negative_count}) is greater than positive evidence count ({positive_count})."` |
| HOLD (balanced) | `"Prediction HOLD because positive and negative evidence are balanced."` |
| HOLD (no directional) | `"Prediction HOLD because positive and negative evidence are balanced or no valid directional evidence is available."` |

The HOLD template chooses the second variant when `directional_evidence_count == 0` (no UP and no DOWN items at all), and the first variant when there is directional evidence but it is balanced (`score == 0`). The "no valid directional evidence" wording is required by the spec for the empty-input and neutral-only scenarios; the alternative wording for the balanced case is the natural mirror.

Rationale is built by a private helper `_build_rationale(prediction, positive_count, negative_count, directional_evidence_count) -> str`. The implementation MUST be a single `f`-string / format call per branch — no concatenation of fragments, no LLM call.

## Temporal Safety

Even though the Temporal Retriever is the owner of temporal validity, the Forecast Model MUST defensively validate every `news_time` against `forecast_time`. The behavior is:

1. If `news_time` is missing, `null`, or unparseable → treat as not-future (defensive default; do not block the rest of the batch on a parse error) and emit a `MALFORMED_NEWS_TIME` warning. The item is still considered for scoring unless `expected_direction` is also missing.
2. If `news_time` parses to a datetime STRICTLY greater than `forecast_time` → exclude the item from scoring, do not place it in any evidence list, and append a `TEMPORAL_LEAKAGE_BLOCKED` warning that records the offending `evidence_id` and the parsed timestamps.
3. If `news_time` is equal to `forecast_time` → keep the item. Strict inequality is the rule.

The forecast_time is parsed using the existing `src.retriever.TimeUtils.parse_datetime` and `TimeUtils.normalize_to_utc` helpers so naive timestamps are interpreted as UTC consistently across the pipeline. If `forecast_time` is missing or unparseable, `ForecastModel.predict` raises `ForecastModelError` (this is a hard failure: the forecast cannot be made without a forecast time).

## Defensive Handling of Bad Evidence

| Condition                                                | Behavior                                                                                       |
|----------------------------------------------------------|------------------------------------------------------------------------------------------------|
| Missing `expected_direction` (or value not in `{UP, DOWN, HOLD}`) | Ignore the item; emit `INVALID_EVIDENCE` warning. (The default `strict = False` mode.) |
| `strict = True` AND missing/invalid `expected_direction` | Raise `ForecastModelError`.                                                                    |
| Duplicate `evidence_id`                                   | First occurrence is kept; subsequent occurrences are dropped and reported as `DUPLICATE_EVIDENCE_ID` warnings. |
| Missing `news_id`                                         | Item is still processed; `news_id` is set to the empty string in outputs.                     |
| Missing `evidence_text`                                   | Item is still processed; `evidence_text` is set to the empty string.                          |
| Missing or unparseable `news_time`                        | Treat as not-future; emit `MALFORMED_NEWS_TIME` warning. Still considered for scoring.         |
| `support_score` missing or not a number                   | Default to `0.0` in the output; not used for V1 scoring.                                        |

One bad item MUST NOT abort the rest of the batch. The `strict` flag is a top-level option that switches from "skip + warn" to "raise on first bad item"; the default is `strict = False` so the system is resilient to upstream noise.

## Faithfulness Support

The Faithfulness Evaluator needs to re-run the model after removing one or more cited evidence IDs. The API is:

```python
ForecastModel.predict_without_evidence(input_data, removed_evidence_ids) -> ForecastResult
```

The behavior is identical to `ForecastModel.predict` except that any evidence item whose `evidence_id` is in `removed_evidence_ids` is filtered out **before** the voting step. The function is intentionally separate from `ForecastModel.predict` (rather than implemented as `ForecastModel.predict` with an optional `removed_evidence_ids` argument) so the call site at the Faithfulness Evaluator is self-documenting and the unit tests can pin the contract independently. Internally both functions call a single private helper `_predict_core(input_data, *, exclude_ids=frozenset())` so they cannot drift.

The Faithfulness Evaluator then computes:

```
confidence_drop = original.confidence - reduced.confidence
```

When `confidence_drop` is small (e.g., `< 0.05`) the cited evidence was not load-bearing; when it is large, the evidence was the reason for the prediction. This is the central signal the prototype is designed to expose.

## Batch API and CSV Output

`ForecastModel.predict_batch(records, *, output_csv_path=None) -> list[ForecastResult]`:

- Iterates `records` in input order and calls `ForecastModel.predict(...)` on each.
- Returns a list of `ForecastResult` dicts, one per record, in input order.
- If `output_csv_path` is provided, writes the per-row scalar fields (`sample_id`, `ticker`, `forecast_time`, `prediction`, `confidence`, `score`, `positive_count`, `negative_count`, `neutral_count`, `total_evidence`, `directional_evidence_count`, `evidence_strength`, `conflict_ratio`, `label`, `model_version`) as a CSV. The default path is `outputs/prediction_results.csv` (relative to the project root) so the dashboard can read it without code changes.
- If a record raises `ForecastModelError`, the error is caught, logged into that record's `warnings` as a structured entry, and the result for that record is filled with a default `HOLD` prediction and `confidence = 0.5` plus an `INPUT_ERROR` warning. The batch never raises.

`ForecastModel.compute_accuracy_and_confusion(results, *, label_key="label") -> dict`:

- For each result, reads `label` (or the `label` field of the corresponding input record — see below).
- Builds a 3×3 confusion matrix over `["UP", "DOWN", "HOLD"]` in that order. Row = predicted, column = actual.
- Returns `{ "accuracy": float, "confusion_matrix": {"labels": [...], "matrix": [[...]]}, "per_class": {"UP": {"precision": ..., "recall": ..., "f1": ..., "support": ...}, ...}, "n_samples": int }`.
- The function accepts a `results` argument that is either a list of result dicts (when each carries its own `label`) or a list of `(input_record, result)` pairs (when the label is on the input). The docstring must make the contract explicit.

## Edge Cases

| Edge case                                          | Expected behavior                                                                                  |
|----------------------------------------------------|----------------------------------------------------------------------------------------------------|
| Empty `evidence` list                              | `prediction = HOLD`, `confidence = 0.5`, all counts 0, `evidence_strength = 0`, `conflict_ratio = 0`, rationale uses the "no valid directional evidence" template. |
| All HOLD evidence                                 | Same as empty: no directional vote.                                                                |
| One UP evidence, no DOWN evidence                  | `score = 1`, `prediction = UP`, `confidence = 0.6`, `evidence_strength = 1.0`, `conflict_ratio = 0`. |
| One DOWN evidence, no UP evidence                  | `score = -1`, `prediction = DOWN`, `confidence = 0.6`.                                             |
| `score = 0` with mixed evidence                    | `prediction = HOLD`, `confidence = 0.5`, rationale uses "balanced" template.                        |
| Future evidence alongside valid evidence           | Future item is excluded; warning emitted; score uses only the valid items.                          |
| Duplicate `evidence_id`s                            | First occurrence kept; subsequent dropped with `DUPLICATE_EVIDENCE_ID` warning.                    |
| `expected_direction = "INVALID"`                    | Item ignored, `INVALID_EVIDENCE` warning. With `strict = True`, raises.                            |
| `forecast_time` missing                            | Raises `ForecastModelError` — hard failure.                                                       |
| `label` field on input                             | Preserved through to the result; never read by `ForecastModel.predict`; read only by the evaluation helper.     |

## Risks and Limitations

- **[Risk] The model is intentionally weak — the goal is faithfulness, not accuracy.** → Mitigation: documented prominently in the module docstring and the README. The pipeline exports `model_version = "rule_based_v1"` so a future learned model can be A/B-tested without breaking the contract.
- **[Risk] Integer score collapses nuance** — five pieces of weak positive evidence look the same as one strong positive. → Mitigation: `evidence_strength` and `conflict_ratio` expose the same information at a glance; the dashboard can show the full evidence list.
- **[Risk] `support_score` is in the input but ignored in V1** — a future change might want to weight by it. → Mitigation: the field is preserved on every output evidence item, so a V2 model can pick it up without changing the input contract.
- **[Risk] Confidence saturates at `abs(score) = 5`.** → Mitigation: documented in the spec; the dashboard can show `abs(score)` and `directional_evidence_count` so the user knows when saturation kicks in.
- **[Risk] The rationale template can lie to a non-technical reader** — e.g., "positive evidence count (1) is greater than negative evidence count (0)" sounds stronger than a single match warrants. → Mitigation: the spec pins the exact template text so the team can add a one-line caveat ("based on a single piece of evidence") in a future change without breaking the contract.
- **[Risk] `ForecastModel.compute_accuracy_and_confusion` requires the `label` to be carried through.** If the upstream pipeline drops `label`, the helper silently returns `n_samples = 0` and `accuracy = 0.0`. → Mitigation: the helper raises `ValueError` if `n_samples` is zero AND the input list is non-empty (a defensive default for a misconfigured pipeline); it returns zero metrics for an empty input list (no false alarms).
- **[Risk] `ForecastModel.predict_without_evidence` could be misused to "cheat" the faithfulness score** — a malicious caller could remove the only counter evidence to make the prediction look more confident. → Mitigation: the function is named clearly; the Faithfulness Evaluator is the only documented caller; the contract explicitly states that the function returns a result computed from the remaining evidence, and `confidence_drop` is signed (positive = confidence went down, negative = confidence went up).
- **[Risk] `outputs/prediction_results.csv` is overwritten on every `ForecastModel.predict_batch` call.** → Mitigation: the default path is configurable; a timestamped filename is documented as a future extension.

## Migration Plan

- Step 1: Land `src/forecast_model.py` and the unit tests behind the existing pipeline. No existing module depends on it, so there is no migration risk.
- Step 2: Land the golden fixtures under `samples/forecast_model/`.
- Step 3: The Faithfulness Evaluator (later change) imports `ForecastModel.predict`, `ForecastModel.predict_without_evidence`, and the rationale template constants from this module.
- Step 4: The Visualization Dashboard (later change) imports `ForecastModel.predict_batch` and the `ForecastModel.compute_accuracy_and_confusion` helper.
- Rollback: removing the module is a single git revert; no data migration.

## Open Questions

- Should `ForecastModel.compute_accuracy_and_confusion` also accept an explicit `(input_record, result)` pair list, or only the result list with `label` echoed on the result? Current plan: accept BOTH; if a list element is a tuple, the first element is the input record (label lives there), else the element is treated as a result. This matches the Evidence Selector's pattern. Revisit when the dashboard mockups are in.
- Should `ForecastModel.predict_batch` write a `prediction_results.json` with the full per-record objects (including the evidence lists) in addition to the CSV? Current plan: yes, when `output_csv_path` is provided, a sibling `prediction_results.json` is also written. The dashboard prefers JSON for full fidelity and CSV for tabular views.
- Should the rationale include a "based on N evidence" suffix when `directional_evidence_count == 1`? Current plan: no — that would be a behavior change to the rationale contract, and the spec pins the exact template text. A future change can add a `rationale_qualifier` field without breaking the existing rationale.
- Should `evidence_strength` be exposed as a percentage (0–100) or a ratio (0–1)? Current plan: ratio. The dashboard can format it.
