## ADDED Requirements

### Requirement: SufficiencyEvaluator computes sufficiency metrics

`SufficiencyEvaluator.evaluate(original_input, original_result, cited_evidence_ids)` SHALL return a dict with the following fields:

- `sufficiency_confidence` (float): confidence khi chỉ dùng cited evidence.
- `sufficiency_score` (float, [0.0, 1.0]): `min(sufficiency_confidence / original_confidence, 1.0)` nếu `original_confidence > 0`, else `0.0`.
- `prediction_on_only_cited` (str): prediction khi chỉ dùng cited evidence (`UP`/`DOWN`/`HOLD`).
- `counterfactual_confidence` (float): confidence sau khi thay cited evidence bằng neutral placeholder.
- `counterfactual_delta` (float): `original_confidence - counterfactual_confidence`.

The evaluator MUST NOT use any LLM, ML model, or external API. It MUST reuse `src.forecast_model.predict`.

#### Scenario: All evidence is cited and supports prediction
- **WHEN** original prediction is `UP` with confidence `0.7` and all evidence items are cited
- **THEN** `sufficiency_confidence` equals the confidence from running `predict()` on only cited items
- **AND** `sufficiency_score` is in range [0.0, 1.0]
- **AND** `prediction_on_only_cited` is one of `UP`, `DOWN`, `HOLD`

#### Scenario: Counterfactual replaces cited evidence with neutral
- **WHEN** cited evidence items are replaced by neutral placeholders (`expected_direction=HOLD`)
- **THEN** `counterfactual_confidence` equals the confidence of the perturbed prediction
- **AND** `counterfactual_delta = original_confidence - counterfactual_confidence`

#### Scenario: No cited evidence
- **WHEN** `cited_evidence_ids` is empty
- **THEN** `sufficiency_confidence` is `0.5` (default HOLD with no evidence)
- **AND** `sufficiency_score` is `0.0`
- **AND** `counterfactual_delta` is `0.0` (nothing to perturb)

---

### Requirement: Pipeline writes sufficiency_results.csv

After the Faithfulness Evaluator step, the pipeline SHALL compute sufficiency metrics and write `outputs/sufficiency_results.csv` with exactly these columns (in order):

```
sample_id, ticker, forecast_time, prediction, original_confidence,
sufficiency_confidence, sufficiency_score, prediction_on_only_cited,
counterfactual_confidence, counterfactual_delta
```

#### Scenario: Pipeline run produces sufficiency output
- **WHEN** `python -m src.pipeline` completes on any valid input CSV
- **THEN** `outputs/sufficiency_results.csv` exists with the required 10 columns
- **AND** `sufficiency_score` values are in range [0.0, 1.0]
- **AND** `counterfactual_delta` can be positive, zero, or negative (signed float)

#### Scenario: One row per (ticker, forecast_time) group
- **WHEN** input CSV has N unique (ticker, forecast_time) groups
- **THEN** `sufficiency_results.csv` has exactly N rows

---

### Requirement: Dashboard renders Sufficiency tab

The dashboard SHALL include a "Sufficiency" tab that displays:
- A scatter/bar chart of `sufficiency_score` per sample.
- A table of `counterfactual_delta` per sample.
- At least 2 summary metric cards: avg `sufficiency_score` and avg `counterfactual_delta`.

#### Scenario: Sufficiency tab renders without crash
- **WHEN** `streamlit run src/dashboard/app.py` opens and `sufficiency_results.csv` exists
- **THEN** the "Sufficiency" tab renders with chart and table without error

#### Scenario: Sufficiency tab gracefully handles missing file
- **WHEN** `sufficiency_results.csv` does not exist
- **THEN** the tab displays an informational message — MUST NOT raise an exception
