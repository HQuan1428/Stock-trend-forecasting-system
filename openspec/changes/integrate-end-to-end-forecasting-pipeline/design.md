## Context

The project has six independently implemented and tested stages (`src/retriever.py`, `src/evidence_extractor.py`, `src/evidence_selector.py`, `src/forecast_model.py`, `src/faithfulness_evaluator.py`, `src/dashboard/`). Each has a public API and its own tests under `tests/`. The dashboard already exists and is read-only with respect to four CSVs under `outputs/`, but no command currently produces those four CSVs from raw input.

The user-facing problem: `data/sample_dataset.csv` has 90+ rows in the schema `news_id, ticker, forecast_time, news_time, news_text, label`. Today, exercising the full pipeline requires a hand-written glue script. We need a single command that takes the raw CSV in, runs the six stages in order, and writes the four dashboard-ready CSVs out.

The current Streamlit dashboard reads four CSVs from `outputs/` (`prediction_results.csv`, `evidence_results.csv`, `faithfulness_results.csv`, `temporal_leakage_results.csv`). When `outputs/` is empty, the dashboard shows a missing-file warning. After this change, the dashboard's happy path is "run the pipeline, then `streamlit run src/dashboard/app.py`".

## Goals / Non-Goals

**Goals**

- One CLI command (`python -m src.pipeline --input <csv> --output-dir <dir>`) that produces all four dashboard CSVs.
- A small orchestration module (`src/pipeline.py`) with one public `PipelineRunner.run(...)` function plus an `argparse` CLI in `if __name__ == "__main__":`.
- Lightweight dataclasses (`src/schema.py`) for `NewsRecord`, `EvidenceItem`, `ForecastResult`, `FaithfulnessResult`, `PipelineResult` so the cross-stage data flow is documented in one place.
- Reuse — zero rewrites of existing module logic. The pipeline imports `TemporalRetriever.retrieve`, `EvidenceExtractor.extract`, `EvidenceSelector.select`, `ForecastModel.predict`, `ForecastModel.predict_without_evidence`, `FaithfulnessEvaluator` as black boxes.
- Strict temporal safety: the `valid_news` list never carries `news_time > forecast_time`. Future news flows only to `outputs/temporal_leakage_results.csv` and `invalid_future_news_count`.
- Integration tests (`tests/test_pipeline.py`) covering the ten scenarios from the proposal.
- README updated with the canonical run command, the four output files, and a one-paragraph end-to-end description.

**Non-Goals**

- Real-time streaming, database storage, authentication, production deployment.
- Trading recommendations, accuracy tuning, hyperparameter search.
- Replacing any existing module. The pipeline is glue code only.
- Changing the dashboard's column contract — the dashboard already consumes the four CSVs; the pipeline writes them.

## Decisions

### D1. Single-file `src/pipeline.py` (no sub-package)

A single orchestration file is enough for a 5-minute demo. Splitting into `src/pipeline/{reader,orchestrator,writers}.py` adds ceremony without benefit at this size. The writer helpers live as private functions in the same file. If the file grows past ~400 lines, splitting is a future change.

**Alternative considered:** `src/pipeline/` package. Rejected because (a) there are no independent test surfaces to isolate, and (b) the existing project uses flat modules (`retriever.py`, `forecast_model.py`) which keeps grep fast.

### D2. Grouping key is `(ticker, forecast_time)`

`data/sample_dataset.csv` has multiple tickers forecasting at the same time and the same ticker forecasting on multiple dates. The Forecast Model takes one forecast request per group, so we partition rows by the natural join key `(ticker, forecast_time)`. This is exactly how the sample data is already structured — rows 1–4 are `(2025-03-12 09:00, AAPL/GOOGL/AMZN/META)`, rows 5–8 are `(2025-03-13 09:00, …)`, etc.

**Alternative considered:** `sample_id` as a separate column. Rejected because the CSV doesn't have one, and inventing one complicates `data/sample_dataset.csv` for no benefit.

### D3. `EvidenceExtractor.extract_batch` then per-group flatten

The Evidence Extractor exposes both single (`EvidenceExtractor.extract`) and batch (`EvidenceExtractor.extract_batch`) entry points. The batch variant preserves input order and is documented as "no time-based filtering", which is exactly what we need: we already filtered with the retriever, so calling the extractor on the (already valid) per-group list is correct.

We call `EvidenceExtractor.extract_batch` once per `(ticker, forecast_time)` group on the group's `valid_news` list, then keep the union of all `evidence` items for downstream stages.

### D4. Skip the Evidence Selector for non-deterministic label leakage protection

The Faithfulness Evaluator already defines `EvidenceSelector.select` semantics. The pipeline DOES call `EvidenceSelector.select` per group (the proposal requires it explicitly) — but only to classify evidence into `pro`/`counter`/`neutral` for the `evidence_results.csv` `evidence_role` column. The actual `ForecastModel.predict(...)` call still receives the full `evidence` list (as its API requires). This keeps the Faithfulness Evaluator's "did the cited evidence actually move the prediction?" test honest: `cited_evidence = pro_evidence + counter_evidence` after classification, never before.

### D5. Output writers as DataFrame `to_csv` calls

For each group, we accumulate rows into four `pd.DataFrame`s in memory, then write them at the end with `to_csv(index=False)`. Each row is a flat dict, so the column order is enforced by `pd.DataFrame(..., columns=[...])`. This is ~40 lines of glue code and is what students can read in five minutes.

**Alternative considered:** `csv.DictWriter`. Rejected because the four outputs need stable column order enforced up-front, which `pd.DataFrame(columns=...)` does for free.

### D6. `faithfulness_label` rule

```
HIGH   if confidence_drop >= 0.20 and temporal_validity == 1.0
MEDIUM if confidence_drop >= 0.05 and temporal_validity == 1.0
LOW    otherwise
```

This matches the proposal text exactly. It's a V1 heuristic — same status as the existing `verdict` cascade in `faithfulness_metrics`. The dashboard already classifies into `high`/`medium`/`low` from `confidence_drop` thresholds; this proposal unifies the two by computing the label at the pipeline boundary (one source of truth), so the dashboard adapter can drop its own derivation.

### D7. `evidence_role` mapping

After `EvidenceSelector.select` returns `pro_evidence` / `counterevidence` / `neutral_evidence`, every evidence item gets exactly one of those labels in `evidence_results.csv`. Cited = `True` if its `evidence_id` is in `pro_evidence ∪ counterevidence`; non-cited = `True` otherwise (incl. neutral). The mapping is per-group, deterministic.

### D8. Dashboard contract is preserved — no dashboard edits

The existing `src/dashboard/data_loader.py` already adapts the upstream CSV columns (incl. synthesizing `evidence_results.csv` and `temporal_leakage_results.csv` from `prediction_results.json` warnings when the standalone files are absent). After this change, the dashboard will load the four real CSVs from disk rather than synthesizing them. This means the dashboard's adapter code becomes mostly a no-op for the evidence and leakage frames — that's fine; we leave it alone to avoid touching unrelated tests. **No dashboard edits in this change.**

### D9. CLI flags and defaults

```python
--input              default "data/sample_dataset.csv"
--output-dir         default "outputs"
--ticker-column      default "ticker"
--news-time-column   default "news_time"
--forecast-time-column default "forecast_time"
--label-column       default "label"   (optional; absent → empty string)
```

Defaults match the existing CSV schema exactly, so the canonical command `python -m src.pipeline` (no args) is enough.

### D10. Error handling: per-group, not whole-pipeline

A malformed row (e.g. unparseable `news_time`) goes into the retriever's `errors` list and is dropped from prediction. A group that fails at any stage (e.g. all-evidence-future, leaving an empty evidence list) goes through the Forecast Model with an empty list — the Forecast Model already handles empty evidence correctly (`HOLD` prediction, all counts zero). The pipeline never crashes the whole run on a single bad row.

### D11. Tests structure

`tests/test_pipeline.py` follows the existing test layout — `pytest`, no fixtures library beyond `tmp_path`. Each scenario uses a small in-memory CSV built with `io.StringIO` or a `tmp_path` file. The `data/sample_dataset.csv` smoke test uses the real file.

## Risks / Trade-offs

- **[Memory blowup on large inputs]** The pipeline holds all four DataFrames in memory before writing. For the 90-row sample this is trivial; for a 1M-row dataset this is a real concern. → Mitigation: documented as a non-goal; the project is a teaching prototype. A future change can add row-streaming writers.

- **[Schema drift between proposal and dashboard]** The proposal text uses some column names that differ from the dashboard's adapter-derived contract (e.g. dashboard synthesizes `evidence_results.csv` from JSON; pipeline writes it directly). → Mitigation: write the column names exactly as the proposal specifies; the dashboard already tolerates either shape via its adapter. If a downstream consumer breaks, only `data_loader.py` needs to change.

- **[Determinism with the rule-based stack]** All six stages are deterministic. The pipeline is a pure function of the input CSV given the column flags. → Verified by running the smoke test twice and `md5sum`-ing the outputs in CI (out of scope for this change but documented as a future verification step).

- **`label` column absent in some inputs]** Some real-world datasets may not have ground truth. → Mitigation: `--label-column` defaults to `label`; when absent in the CSV, every row's `label` is `""` and `is_correct` is `False`. The pipeline never raises on missing labels.

- **[Empty group after retriever]** If every row in a group is `news_time > forecast_time`, the Forecast Model receives `[]`. The Forecast Model already handles this — but the `evidence_results.csv` row for that group will be empty. → Mitigation: the writer still writes a `prediction_results.csv` row (with `prediction=HOLD`, `valid_news_count=0`, `invalid_future_news_count>0`), and `temporal_leakage_results.csv` gets one row per leaked news item.

- **[The Faithfulness Evaluator's CSV writer conflicts]** The Faithfulness Evaluator already writes `faithfulness_results.csv` when called via `FaithfulnessEvaluator.evaluate_batch`. If we call `FaithfulnessEvaluator.evaluate_batch`, it will write to that path with its own column order. → Mitigation: do NOT call `FaithfulnessEvaluator.evaluate_batch`. Call `FaithfulnessEvaluator().evaluate(request, result)` per group and build the CSV row by hand from the report dict using the proposal's column order. This keeps `FaithfulnessEvaluator.evaluate_batch` available for ad-hoc use but does not couple the pipeline to its file-writing side effect.

## Migration Plan

No migration. This is purely additive:

1. Add `src/pipeline.py`, `src/schema.py`, `tests/test_pipeline.py`.
2. Update `README.md` with the new section.
3. Re-run existing tests to confirm no regression.

No existing file is renamed or removed. No existing public API changes.

## Open Questions

None blocking. Possible future questions:

- Should the pipeline accept JSON input as well as CSV? (Out of scope; CSV is the documented format.)
- Should `evidence_results.csv` carry `start_char` / `end_char` offsets? (Out of scope; the dashboard already drops them.)
- Should the pipeline print a summary table at the end (accuracy / leakage count)? (Nice-to-have; left for a follow-up change.)