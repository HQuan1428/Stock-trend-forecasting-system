# Evidence Selector — Design (Version 1)

## Context

The Faithful Evidence-Centric Financial News Forecasting pipeline ingests news and price data, runs the Temporal Retriever to enforce "no future news" leakage, then runs the Evidence Extractor to produce a list of evidence phrases with polarity and expected direction. After the Forecast Model emits a prediction (UP / DOWN / HOLD) and a confidence, the system has no module that decides **which evidence is pro, counter, or neutral relative to that prediction**. Without this classification, the Faithfulness Evaluator cannot measure counterevidence coverage and the Visualization Dashboard cannot show balanced explanations.

Version 1 is intentionally simple: a fixed `(prediction, expected_direction) → selector_label` table, a deterministic ranking by `selector_score` (V1: equal to `extractor_score`), and an explicit `invalid_future_evidence` list for defense in depth. No LLM, no FinBERT, no learned weights, no model training. The classification table is small enough to audit at a glance and easy to extend later (e.g., to weight evidence by recency or by the strength of the matched keyword).

The pipeline order becomes:

```
News + Price Data
  → Temporal Retriever       (owns temporal validity)
  → Evidence Extractor       (owns per-phrase evidence)
  → Forecast Model           (owns prediction + confidence)
  → Evidence Selector        (owns pro/counter/neutral classification) ← this change
  → Faithfulness Evaluator   (consumes selector output)
  → Visualization Dashboard  (consumes selector output)
```

## Goals / Non-Goals

**Goals**

- Provide a deterministic `select_evidence(...)` function that classifies every evidence candidate into exactly one of `pro_evidence`, `counterevidence`, or `neutral_evidence`, ranked by `selector_score` descending.
- Expose a per-prediction `summary` block with `pro_count`, `counter_count`, `neutral_count`, `has_counterevidence`, and `counterevidence_ratio` so downstream modules and the dashboard can detect one-sided explanations.
- Surface — not silently drop — any evidence item with `news_time > forecast_time` via an `invalid_future_evidence` list. The Temporal Retriever normally guarantees this never happens, but the Selector must defend in depth and never let a future item pollute the pro/counter/neutral groups.
- Support configurable `top_k` per group with safe defaults (`top_k_pro=5`, `top_k_counter=5`, `top_k_neutral=5`).
- Preserve `news_id`, `ticker`, `news_time`, `evidence_text`, `expected_direction`, `polarity`, and the score on every output evidence item.
- Be fully testable with unit tests that pin the nine-cell classification matrix, ranking order, empty input, future-evidence flagging, and label-leakage protection.
- Ship golden fixtures under `samples/evidence_selector/` for regression testing.

**Non-Goals**

- LLM-based classification, FinBERT, transformer models, or any external NLP model.
- Learned scoring, calibrated confidence, or per-keyword weights beyond the binary `selector_score = extractor_score` baseline.
- Re-implementing temporal filtering (the Temporal Retriever owns this) or re-extracting evidence from raw news text (the Evidence Extractor owns this).
- Producing the forecast or price prediction itself (the Forecast Model owns this).
- Counterfactual reasoning ("what would the prediction be without this evidence") — out of scope for V1.
- Multi-language support.
- Persisting selector state across calls — the function is pure.

## Data Contract

### Input

The selector receives a single prediction request (one per ticker × forecast_time) with this shape:

```json
{
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
      "extractor_score": 0.9
    }
  ]
}
```

- `prediction` ∈ `{"UP", "DOWN", "HOLD"}` (required).
- `evidence_candidates` is a list (possibly empty) of objects with the seven fields above.
- The selector MUST NOT read a ground-truth label from the candidate, the dataset, or any other source. Candidates with an extra `label` field are passed through unchanged but ignored for classification.

### Output

```json
{
  "ticker": "AAPL",
  "forecast_time": "2025-03-12 09:00",
  "prediction": "UP",
  "confidence": 0.82,
  "pro_evidence":       [ { "news_id": "...", "selector_label": "pro",     "selector_score": 0.9, "reason": "..." } ],
  "counterevidence":    [ { "news_id": "...", "selector_label": "counter", "selector_score": 0.85, "reason": "..." } ],
  "neutral_evidence":   [ ... ],
  "invalid_future_evidence": [ { "news_id": "...", "news_time": "...", "reason": "..." } ],
  "summary": {
    "pro_count": 1,
    "counter_count": 1,
    "neutral_count": 0,
    "has_counterevidence": true,
    "counterevidence_ratio": 0.5
  },
  "selection_method": "rule_based"
}
```

Empty lists are returned as `[]`, never `null`. Field metadata (`ticker`, `forecast_time`, `prediction`, `confidence`) is echoed verbatim.

## Classification Rules

The V1 classification is a fixed lookup table; there is no learned policy. Given `prediction = P` and `evidence.expected_direction = D`:

| `P`  | `D`    | `selector_label` | `reason`                                                                                       |
|------|--------|------------------|------------------------------------------------------------------------------------------------|
| UP   | UP     | `pro`            | "Evidence expected direction UP matches prediction UP"                                          |
| UP   | DOWN   | `counter`        | "Evidence expected direction DOWN conflicts with prediction UP"                                 |
| UP   | HOLD   | `neutral`        | "Evidence expected direction HOLD is not directional for prediction UP"                         |
| DOWN | DOWN   | `pro`            | "Evidence expected direction DOWN matches prediction DOWN"                                      |
| DOWN | UP     | `counter`        | "Evidence expected direction UP conflicts with prediction DOWN"                                 |
| DOWN | HOLD   | `neutral`        | "Evidence expected direction HOLD is not directional for prediction DOWN"                       |
| HOLD | HOLD   | `pro`            | "Evidence expected direction HOLD matches prediction HOLD"                                      |
| HOLD | UP     | `counter`        | "Evidence expected direction UP conflicts with prediction HOLD"                                 |
| HOLD | DOWN   | `counter`        | "Evidence expected direction DOWN conflicts with prediction HOLD"                               |

A candidate is classified by exactly one cell. The `reason` string is emitted verbatim in the output for auditability — it is part of the contract, not free text.

## Ranking Strategy

Each group (`pro_evidence`, `counterevidence`, `neutral_evidence`) is sorted by `selector_score` descending. Ties are broken by the order in which the items appeared in the input list (stable sort). After sorting, each group is truncated to its `top_k` cap.

```text
selector_score := extractor_score        # V1
# V2 candidate formula (not implemented in V1):
# selector_score := extractor_score * keyword_strength * recency_weight
```

The cap is applied per group independently, so a long counter list cannot starve the pro list, and vice versa. Items beyond the cap are dropped from the visible group; they are NOT moved to another group and NOT silently lost — they are still part of the `summary.pro_count + summary.counter_count + summary.neutral_count` total for that group before truncation. (V1 documentation may refine this; the contract requires only that the visible lists respect `top_k`.)

## Metrics

`summary` is computed across the **full** groups (before `top_k` truncation) so the dashboard can show "5 counter evidence items, top 3 shown":

- `pro_count = len(pro_evidence)` (full, pre-truncation).
- `counter_count = len(counterevidence)`.
- `neutral_count = len(neutral_evidence)`.
- `has_counterevidence = (counter_count > 0)`.
- `counterevidence_ratio = counter_count / (pro_count + counter_count)` when `pro_count + counter_count > 0`, else `0.0`.

Optional dataset-level metrics (not in the per-prediction output; exposed by a separate helper when manual annotation exists):

- `counterevidence_coverage = detected_counterevidence_count / available_counterevidence_count` — per-prediction, when the dataset has a manually annotated `expected_selector_label` per candidate.
- `counterevidence_detected_rate = number of predictions with at least one counterevidence / total number of predictions` — when manual annotation is unavailable.

## Error Handling

| Condition                                              | Behavior                                                                                       |
|--------------------------------------------------------|------------------------------------------------------------------------------------------------|
| `prediction` not in `{"UP","DOWN","HOLD"}`             | Raise `EvidenceSelectorError(ValueError)` with the offending value.                            |
| `evidence_candidates` is missing / not a list           | Raise `EvidenceSelectorError(TypeError)`.                                                      |
| A candidate is missing `expected_direction`             | Skip the candidate, append it to a `invalid_candidates` list with `reason = "missing_expected_direction"`. Counts in `summary` exclude skipped items. |
| A candidate has an unknown `expected_direction`         | Same: skip + append to `invalid_candidates` with `reason = "unknown_expected_direction"`.      |
| A candidate has `news_time > forecast_time`             | Do **not** classify it. Append to `invalid_future_evidence` with `reason = "future_evidence"`. Counts in `summary` exclude it. |
| `news_time` is missing or unparseable                  | Treat the candidate as not-future (defensive: do not block the rest of the batch on a parse error). Append a note to `invalid_candidates` with `reason = "missing_or_malformed_news_time"`. |
| `extractor_score` is missing                            | Default to `0.0` for ranking only (still classified normally). Document this fallback.        |

The selector never raises on a single bad candidate — one malformed item must not abort the entire prediction.

## Dashboard Integration

The Visualization Dashboard (later change) consumes the output of `select_evidence` to render:

- A "Pro evidence" table (top `top_k_pro` rows, descending score).
- A "Counter evidence" table (top `top_k_counter` rows, descending score) — the most important signal for faithfulness.
- A "Neutral evidence" table (top `top_k_neutral` rows).
- A summary tile showing `has_counterevidence` (red badge if true, green if false) and `counterevidence_ratio` (gauge).
- A warning banner when `invalid_future_evidence` is non-empty — this should never happen if the Temporal Retriever is wired correctly, but a non-empty list is a smoke alarm for pipeline integrity.

The contract that downstream modules MUST import the selector's classification table and reasons from `src/evidence_selector.py` is codified in a module docstring (analogous to the Evidence Extractor's `KEYWORD_TO_POLARITY` rule).

## Testing Strategy

1. **Unit tests** (`tests/test_evidence_selector.py`):
   - The full nine-cell classification matrix (parametrized over `(prediction, expected_direction, expected_label)`).
   - The `reason` string for each cell.
   - Empty `evidence_candidates` → all groups empty, counts zero, `counterevidence_ratio = 0.0`, no exception.
   - Ranking: items in the same group are sorted by `selector_score` descending; ties preserve input order.
   - `top_k` truncation: each group respects its cap; other groups unaffected.
   - Future-evidence flagging: a candidate with `news_time > forecast_time` goes to `invalid_future_evidence`, NOT to any pro/counter/neutral group.
   - Label leakage: even if a candidate carries a `label` (or `ground_truth_label`) field, the selector classifies purely on `expected_direction`.
   - Field preservation: every output evidence item retains `news_id`, `ticker`, `news_time`, `evidence_text`, `expected_direction`, `polarity`, and `extractor_score`.
   - Bad-input error handling: bad `prediction`, non-list candidates, missing `expected_direction`, unknown `expected_direction`, missing `news_time` — all raise or skip per the table above, never crash.
   - Determinism: same input → same output (byte-equal for the JSON-serializable parts).

2. **Golden fixtures** (`samples/evidence_selector/`):
   - `01_up_with_counter_input.json` / `_expected.json` — UP prediction, one pro, one counter, one neutral, one future.
   - `02_down_input.json` / `_expected.json` — DOWN prediction, one pro, one counter.
   - `03_hold_input.json` / `_expected.json` — HOLD prediction, one pro, one counter.

3. **Integration smoke test** (optional, V2): a small end-to-end test that wires Temporal Retriever → Evidence Extractor → Forecast Model (mocked) → Evidence Selector and asserts the dashboard-ready output is well-formed.

## Risks and Limitations

- **[Risk] Rule-based classification cannot capture nuance** — e.g., a positive article about a competitor that the model still predicts "DOWN" for our ticker is counter, but the selector does not know that. → Mitigation: a documented limitation; the Faithfulness Evaluator and dashboard surface `has_counterevidence` and `counterevidence_ratio` so human reviewers can spot the gap.
- **[Risk] The selector and the Extractor may disagree about `expected_direction`** — the Extractor's `expected_direction` is itself keyword-derived. → Mitigation: the selector consumes the Extractor's output as-is and never re-derives direction. A future change can tighten this by exposing per-keyword directional weights.
- **[Risk] A future-evidence item that is also a strong counter** would be hidden in `invalid_future_evidence` rather than surfaced in the counter list. → Mitigation: the dashboard shows `invalid_future_evidence` as a warning banner; a smoke alarm for pipeline integrity.
- **[Risk] `top_k` truncation can hide items a human reviewer would want to see** — V1 truncates silently. → Mitigation: the `summary` counts reflect the full (pre-truncation) totals; the dashboard can show "5 of 12 shown" affordances. A future change can emit a separate `truncated` flag.
- **[Risk] `extractor_score` is the only ranking signal in V1** — a candidate with a high score but a stale news_time can outrank a fresher candidate. → Mitigation: V1 documents the `selector_score = extractor_score * keyword_strength * recency_weight` extension point; the `news_time` field is preserved on every output item so a V2 selector can compute recency.
- **[Risk] Misclassification of HOLD** — when both `prediction` and `expected_direction` are `HOLD`, the item is `pro`; this is intentional (the model is "right" to predict HOLD if it has only neutral evidence) but a reviewer expecting "no evidence means no support" may be surprised. → Mitigation: documented in the classification table; the `reason` string is explicit ("matches prediction HOLD").

## Migration Plan

- Step 1: Land `src/evidence_selector.py` and the unit tests behind the existing pipeline. No existing module depends on it, so there is no migration risk.
- Step 2: Land the golden fixtures under `samples/evidence_selector/`.
- Step 3: The Faithfulness Evaluator (later change) imports the selector's classification table and reasons from this module rather than redefining them.
- Rollback: removing the module is a single git revert; no data migration.

## Open Questions

- Should `top_k` truncation be per-group, per-prediction, or per-news-item? Current plan: per-group per-prediction. Revisit when the dashboard mockups are in.
- Should the selector expose a `select_evidence_batch(predictions)` helper for pipeline use, or only `select_evidence` (one at a time)? Current plan: ship both; batch is a thin loop, no parallelism (V1).
- Should the `reason` string be machine-translatable? Current plan: emit English literal strings; a future change can add a `reason_id` integer for i18n.
- Should we surface `selector_score_components` (e.g., `{"extractor_score": 0.9, "keyword_strength": 1.0, "recency_weight": 1.0}`) in V1 to ease the V2 extension? Current plan: deferred to V2; V1 emits a single `selector_score` field.
