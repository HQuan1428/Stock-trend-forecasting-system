## 1. Shared data contracts

- [x] 1.1 Create `src/schema.py` with `NewsRecord`, `EvidenceItem`, `ForecastResult`, `FaithfulnessResult`, `PipelineResult` dataclasses matching the spec.
- [x] 1.2 Re-export the dataclasses from `src/__init__.py` so `from src.schema import ...` and `from src import NewsRecord` both work.

## 2. Pipeline orchestration

- [x] 2.1 Create `src/pipeline.py` with `run_pipeline(input_path, output_dir, *, ticker_column="ticker", news_time_column="news_time", forecast_time_column="forecast_time", label_column="label") -> PipelineResult`.
- [x] 2.2 Implement the per-group loop: partition rows by `(ticker_column, forecast_time_column)`, call `retrieve_valid_news`, separate `valid_news` from `invalid_future_news`.
- [x] 2.3 Call `extract_evidence_batch` on each group's `valid_news`, flatten to one evidence list per group.
- [x] 2.4 Call `select_evidence_batch` to classify each evidence item into `pro` / `counter` / `neutral` for the `evidence_role` column.
- [x] 2.5 Build the Forecast Model request envelope from `valid_news` + extracted evidence and call `predict(...)`.
- [x] 2.6 Build a `valid_evidence` list for the Faithfulness Evaluator (excluding any future-dated items defensively) and call `FaithfulnessEvaluator().evaluate(request, result)`.
- [x] 2.7 Compute `confidence_drop = original_confidence - confidence_without_cited_evidence` from the report.
- [x] 2.8 Apply the faithfulness_label rule (`HIGH` / `MEDIUM` / `LOW`).

## 3. Output writers

- [x] 3.1 Write `outputs/prediction_results.csv` with columns `ticker, forecast_time, prediction, confidence, score, label, is_correct, rationale, cited_evidence_count, valid_news_count, invalid_future_news_count`.
- [x] 3.2 Write `outputs/evidence_results.csv` with columns `ticker, forecast_time, news_id, news_time, evidence_text, polarity, expected_direction, evidence_role, support_score, is_cited`.
- [x] 3.3 Write `outputs/faithfulness_results.csv` with columns `ticker, forecast_time, prediction, original_confidence, confidence_without_cited_evidence, confidence_drop, temporal_validity, evidence_support, faithfulness_label`.
- [x] 3.4 Write `outputs/temporal_leakage_results.csv` with columns `ticker, forecast_time, news_id, news_time, news_text, leakage_type` (literal `future_news`).
- [x] 3.5 Use `pd.DataFrame(..., columns=[...]).to_csv(path, index=False)` for deterministic column order.

## 4. CLI entry point

- [x] 4.1 Add `argparse` block at the bottom of `src/pipeline.py` exposing `--input`, `--output-dir`, `--ticker-column`, `--news-time-column`, `--forecast-time-column`, `--label-column` with the defaults documented in design D9.
- [x] 4.2 Verify `python -m src.pipeline` (no args) runs end-to-end on `data/sample_dataset.csv` and exits 0.

## 5. Integration tests

- [x] 5.1 Create `tests/test_pipeline.py` with `pytest`-style tests; no new fixtures library beyond `tmp_path`.
- [x] 5.2 Test 1: pipeline completes without error on `data/sample_dataset.csv`.
- [x] 5.3 Test 2: future news is excluded from prediction (assert: future row's `news_id` not in `evidence_results.csv` `news_id` set).
- [x] 5.4 Test 3: valid news flows into extraction (assert: at least one row in `evidence_results.csv` for an all-valid group).
- [x] 5.5 Test 4: `prediction_results.csv` is created with required columns.
- [x] 5.6 Test 5: `faithfulness_results.csv` is created with required columns.
- [x] 5.7 Test 6: `evidence_results.csv` is created with required columns.
- [x] 5.8 Test 7: `temporal_leakage_results.csv` is created with required columns.
- [x] 5.9 Test 8: `confidence_drop` is a finite float for at least one cited-evidence group.
- [x] 5.10 Test 9: a group with at least one future row shows `invalid_future_news_count > 0` in `prediction_results.csv`.
- [x] 5.11 Test 10: all four output CSVs contain the columns the dashboard's `load_dashboard_data` requires (`PREDICTION_COLUMNS`, `EVIDENCE_COLUMNS`, `FAITHFULNESS_COLUMNS`, `LEAKAGE_COLUMNS`).

## 6. Documentation

- [x] 6.1 Add a "Run the pipeline" section to `README.md` between the "Setup" and "Temporal Retriever" sections.
- [x] 6.2 Document the canonical command `python -m src.pipeline --input data/sample_dataset.csv --output-dir outputs`.
- [x] 6.3 Add a 4-row table describing each output file (path + one-line purpose).
- [x] 6.4 Add a one-paragraph end-to-end flow description: news CSV → retriever → extractor → selector → forecaster → faithfulness → 4 CSVs → dashboard.

## 7. Verification

- [x] 7.1 Run `pytest tests/ -q` and confirm all existing tests + new `test_pipeline.py` pass.
- [x] 7.2 Run `python -m src.pipeline` from a clean checkout and confirm all four CSVs exist and pass the schema tests.
- [x] 7.3 Run `streamlit run src/dashboard/app.py` against the generated CSVs and confirm no missing-file warning.