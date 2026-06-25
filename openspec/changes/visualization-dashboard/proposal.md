# Visualization Dashboard — Proposal

## Why

The Faithful Evidence-Centric Financial News Forecasting pipeline now produces four upstream result files (`outputs/prediction_results.csv` from the Forecast Model, `outputs/faithfulness_results.csv` from the Faithfulness Evaluator, plus the CSV outputs the Temporal Retriever and Evidence Extractor write). Without a visualization layer, reviewers must open raw CSV files in a spreadsheet to understand what the prototype did — there is no way to (a) see at a glance how many `UP`/`DOWN`/`HOLD` predictions were emitted, (b) compare the cited evidence against the prediction, (c) check the confidence drop after ablation, or (d) spot temporal leakage rows.

The Visualization Dashboard is the final read-only layer of the pipeline. It exists for academic visualization, debugging, demo, and report evidence — not for trading decisions. Version 1 uses Streamlit because it is easy to demo locally, easy to screenshot for the final report, and is already in `requirements.txt`.

## What Changes

- Add a new Streamlit-based module under `src/dashboard/` (modular layout, preferred over a single `src/dashboard.py`):
  - `src/dashboard/__init__.py` — public API.
  - `src/dashboard/app.py` — the Streamlit entry point (`streamlit run src/dashboard/app.py`).
  - `src/dashboard/data_loader.py` — CSV loaders with schema validation, missing-file handling, and column-renaming adapters that bridge from the current upstream output shapes to the dashboard contract.
  - `src/dashboard/validators.py` — pure functions that assert required columns, raise `DashboardDataError`, and produce friendly empty-state messages.
  - `src/dashboard/metrics.py` — pure functions that compute prediction distribution, accuracy, average confidence, average confidence drop, average temporal validity, leakage counts, and faithfulness-level labels (`high` / `medium` / `low`).
  - `src/dashboard/charts.py` — Plotly chart builders (prediction distribution bar, confidence-drop scatter, temporal-leakage count, accuracy-by-ticker).
  - `src/dashboard/components.py` — Streamlit components: tab layout, sidebar filters, evidence table renderer with cited/invalid highlighting, leakage table renderer with severity badge, case-detail panel.
- Add a small `DashboardDataError(ValueError)` exception class.
- Add `tests/test_dashboard_data_loader.py`, `tests/test_dashboard_validators.py`, `tests/test_dashboard_metrics.py`, and `tests/test_dashboard_filters.py` covering the eleven scenarios from the spec.
- Add `samples/dashboard/` with three small CSV fixture sets: a healthy batch, a batch with one temporal leakage row, and a batch with one faithfulness label per level.
- Update `README.md` with a "Visualization Dashboard" section explaining how to run it and what each tab shows.
- Update `src/__init__.py` to re-export the dashboard public API.

The dashboard MUST be read-only with respect to upstream artifacts. It MUST NOT re-run the pipeline. It MUST NOT mutate any file under `outputs/`.

### Contract-mismatch caveat (important)

The proposal text specifies column names that do not exactly match what the current source produces:

| Proposal column | Current source column | Bridge |
|---|---|---|
| `prediction_results.csv: valid_news_count` | not emitted | Computed by `data_loader` from the upstream CSV (count of valid evidence rows per `sample_id` joined from `evidence_results.csv`). |
| `prediction_results.csv: invalid_future_news_count` | not emitted | Computed by `data_loader` from `evidence_results.csv` (count of `is_temporally_valid == False` rows per `sample_id`). |
| `prediction_results.csv: label` | emitted as `label` (good) | Rename `label` (no-op). |
| `prediction_results.csv: rationale` | emitted on `prediction_results.json`, not CSV | Joined from the JSON sibling when available; left empty otherwise. |
| `faithfulness_results.csv: sample_id` | not currently emitted | Joined from `prediction_results.csv` on `ticker + forecast_time`. |
| `faithfulness_results.csv: confidence_without_cited_evidence` | emitted as `confidence_after_removal` | Renamed in `data_loader`. |
| `faithfulness_results.csv: faithfulness_label` | emitted as `verdict` (`strong_/moderate_/weak_/decorative_/invalid_/unsupported_`) | Derived from `confidence_drop` per the documented thresholds; the dashboard treats the verdict as a richer alias of the faithfulness label. |
| `evidence_results.csv` | does not exist as a single artifact | Synthesized by `data_loader` from the Forecast Model's `prediction_results.json` (which carries `pro_evidence` / `counter_evidence` / `up_evidence` / `down_evidence` / `neutral_evidence`). |
| `temporal_leakage_results.csv` | does not exist as a separate file | Synthesized by `data_loader` from the temporal-leakage rows in `prediction_results.json` warnings (the Forecast Model emits `TEMPORAL_LEAKAGE_BLOCKED` warnings with `news_time` / `forecast_time`). |

The design therefore includes an **adapter layer** in `data_loader.py` that resolves the four proposal-defined tables to either (a) direct file loads when the file already exists in the proposal shape, or (b) joins / derivations from the current upstream outputs. The adapter is the single source of truth for the dashboard's column contract; downstream code (charts, components) consumes only the proposal-shape tables.

## Capabilities

### New Capabilities

- `visualization-dashboard`: A Streamlit-based read-only visualization layer that consumes the four upstream output files (`prediction_results.csv`, `evidence_results.csv`, `faithfulness_results.csv`, `temporal_leakage_results.csv`) and renders five tabs (Overview, Evidence, Confidence Drop, Temporal Leakage, Case Detail) with consistent sidebar filters (ticker, prediction, faithfulness level, forecast date range, cited-only, leakage-only). The dashboard is deterministic given the same input files, side-effect-free with respect to upstream artifacts, and never invokes any LLM, FinBERT, transformer model, or external API.

### Modified Capabilities

_None._ This change introduces a new capability. The Temporal Retriever, Evidence Extractor, Evidence Selector, Forecast Model, and Faithfulness Evaluator specs are unaffected. The dashboard consumes the existing output contracts (with an adapter layer for missing `evidence_results.csv` and `temporal_leakage_results.csv`); it does not change any upstream behavior.

## Impact

- New code: `src/dashboard/__init__.py`, `src/dashboard/app.py`, `src/dashboard/data_loader.py`, `src/dashboard/validators.py`, `src/dashboard/metrics.py`, `src/dashboard/charts.py`, `src/dashboard/components.py`.
- New tests: `tests/test_dashboard_data_loader.py`, `tests/test_dashboard_validators.py`, `tests/test_dashboard_metrics.py`, `tests/test_dashboard_filters.py`.
- New sample fixtures: `samples/dashboard/` with healthy, leakage, and faithfulness-label fixtures.
- New dependency: `streamlit` and `plotly` are already in `requirements.txt` — no new packages required.
- Downstream consumers: the dashboard is the final stage. It is the only documented consumer of the four `outputs/*.csv` files in Version 1.
- Documentation: `README.md` gains a "Visualization Dashboard" section. The pipeline order diagram in `README.md` is extended to include the dashboard as the final stage.
- No external services, no model downloads, no GPU, no network access required at runtime.
- **Not in scope:** trading advice, real-time streaming, authentication, database storage, buy/sell signal generation, LLM-based explanation generation inside the dashboard, full pipeline orchestration, production deployment setup.