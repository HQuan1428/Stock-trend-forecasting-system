## ADDED Requirements

### Requirement: Pipeline computes counterevidence coverage per prediction

For each `(ticker, forecast_time)` group, after the Evidence Selector step, the pipeline SHALL compute counterevidence coverage and include it in `faithfulness_results.csv`.

The coverage MUST be computed by calling `compute_coverage()` from `src.evidence_selector` with:
- `result`: the Evidence Selector's output for this group.
- `expected_labels`: a dict mapping each candidate's `news_id` to its expected role, derived by applying `CLASSIFICATION_TABLE[(prediction, expected_direction)]` for each candidate.

The pipeline SHALL add 2 fields to `faithfulness_row`:
- `counterevidence_coverage` (float, 0.0–1.0)
- `counterevidence_detected` (bool): `True` when `counterevidence_detected_rate == 1.0`

#### Scenario: Sample has counterevidence candidates within top_k
- **WHEN** a prediction is UP and at least 1 evidence candidate has `expected_direction=DOWN`
- **THEN** `counterevidence_detected` is `True` and `counterevidence_coverage > 0.0`

#### Scenario: Sample has no counterevidence candidates
- **WHEN** all evidence candidates have `expected_direction` aligned with prediction
- **THEN** `counterevidence_detected` is `False` and `counterevidence_coverage == 0.0`

#### Scenario: Counterevidence candidates exceed top_k_counter
- **WHEN** there are N counterevidence candidates and N > top_k_counter (default 3)
- **THEN** `counterevidence_coverage == top_k_counter / N` (< 1.0)

---

### Requirement: `faithfulness_results.csv` includes coverage columns

The output file `outputs/faithfulness_results.csv` SHALL contain the columns (in order):

```
sample_id, ticker, forecast_time, prediction,
original_confidence, confidence_without_cited_evidence,
confidence_drop, temporal_validity, evidence_support,
faithfulness_label, counterevidence_coverage, counterevidence_detected
```

#### Scenario: Pipeline run produces coverage columns
- **WHEN** `python -m src.pipeline` runs to completion
- **THEN** `outputs/faithfulness_results.csv` contains columns `counterevidence_coverage` and `counterevidence_detected`
- **AND** all values in `counterevidence_coverage` are in range [0.0, 1.0]
- **AND** all values in `counterevidence_detected` are boolean (True/False)

---

### Requirement: Dashboard displays counterevidence coverage metric

The dashboard tab "Faithfulness / Confidence Drop" SHALL display a metric card showing average `counterevidence_coverage` across displayed samples.

#### Scenario: Dashboard loads enriched faithfulness data
- **WHEN** `streamlit run src/dashboard/app.py` is opened
- **THEN** the Confidence Drop tab shows a metric card labeled "Avg Counterevidence Coverage"
- **AND** the value is displayed as a percentage (0%–100%)

#### Scenario: Missing columns in old CSV files
- **WHEN** `faithfulness_results.csv` was generated before this change (no coverage columns)
- **THEN** the dashboard MUST NOT crash — `data_loader.py` fills missing columns with `0.0` / `False`
