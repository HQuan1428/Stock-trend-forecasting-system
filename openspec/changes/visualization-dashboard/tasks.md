# Tasks: Visualization Dashboard (Version 1)

Tasks are grouped by dependency order. Each task is small enough to complete in one session and produces a verifiable artifact. Tasks intentionally do NOT include source-code lines — they describe the artifact to be produced, not the exact text to type.

## 1. Module Skeleton and Package Layout

- [x] 1.1 Create `src/dashboard/__init__.py` with a module docstring documenting the contract: read-only, no IO mutation, no LLM, deterministic, side-effect-free in single-eval mode. Re-export the public API from the submodules.
- [x] 1.2 Create `src/dashboard/validators.py` with a typed `DashboardDataError(ValueError)` exception class and a pure `assert_columns(df, required_columns, *, file_label) -> None` helper that raises `DashboardDataError` listing the missing column names.
- [x] 1.3 Create `src/dashboard/metrics.py` with module-level constants `FAITHFULNESS_HIGH_THRESHOLD = 0.20`, `FAITHFULNESS_MEDIUM_THRESHOLD = 0.05`, `LEAKAGE_WARNING_THRESHOLD = 1`, `LEAKAGE_CRITICAL_THRESHOLD = 3`, `VALID_PREDICTIONS = ("UP", "DOWN", "HOLD")`, `FAITHFULNESS_LEVELS = ("high", "medium", "low")`, `LEAKAGE_SEVERITIES = ("ok", "warning", "critical")`.
- [x] 1.4 Create `src/dashboard/data_loader.py` with module-level constants for the four proposal-defined column lists: `PREDICTION_COLUMNS`, `EVIDENCE_COLUMNS`, `FAITHFULNESS_COLUMNS`, `LEAKAGE_COLUMNS`.
- [x] 1.5 Create `src/dashboard/charts.py` with module-level constants `COLOR_HIGH = "#2ca02c"`, `COLOR_MEDIUM = "#ffbb33"`, `COLOR_LOW = "#d62728"`, `COLOR_OK = "#2ca02c"`, `COLOR_WARNING = "#ffbb33"`, `COLOR_CRITICAL = "#d62728"`.
- [x] 1.6 Update `src/__init__.py` to re-export the dashboard public API: `DashboardDataError`, `assert_columns`, `load_dashboard_data`, the metric functions from task 3, the chart builders from task 5, and the four column lists from task 1.4.

## 2. Pure Validators

- [x] 2.1 Implement `assert_columns(df, required_columns, *, file_label) -> None` in `validators.py` that raises `DashboardDataError` with a message of the form `"<file_label> is missing required columns: [<list>]"`. The function MUST NOT raise when all required columns are present.
- [x] 2.2 Implement `assert_dashboard_data(data) -> None` in `validators.py` that runs `assert_columns` on every non-empty DataFrame in a `DashboardData` dataclass.
- [x] 2.3 Add unit tests in `tests/test_dashboard_validators.py` covering: missing column raises with the expected message; multiple missing columns all appear in the message; extra columns are ignored; empty DataFrame is treated as "missing all columns" (raises); `assert_dashboard_data` aggregates errors from multiple files.

## 3. Pure Metric Helpers

- [x] 3.1 Implement `prediction_distribution(df) -> Dict[str, int]` returning counts of `UP`, `DOWN`, `HOLD` in `df["prediction"]`. Missing classes SHALL be reported as `0`. Invalid prediction values SHALL be ignored (counted in neither total nor per-class).
- [x] 3.2 Implement `accuracy(df) -> Optional[float]` returning `df["prediction"] == df["label"]` mean when both columns are present, else `None`. Boolean / non-numeric `label` SHALL be cast to string for the comparison.
- [x] 3.3 Implement `average_confidence(df) -> float` returning the mean of `df["confidence"]`, defaulting to `0.0` for empty input.
- [x] 3.4 Implement `average_confidence_drop(df) -> float` returning the mean of `df["confidence_drop"]`, defaulting to `0.0` for empty input.
- [x] 3.5 Implement `temporal_leakage_count(df) -> int` returning the number of rows in the leakage DataFrame (or, when given the evidence DataFrame, the count where `is_temporally_valid == False`).
- [x] 3.6 Implement `average_temporal_validity(df) -> float` returning the mean of `df["temporal_validity"]`, defaulting to `1.0` for empty input (no evidence means no leakage).
- [x] 3.7 Implement `classify_faithfulness_level(confidence_drop) -> str` returning `"high"` when `drop >= 0.20`, `"medium"` when `0.05 <= drop < 0.20`, `"low"` otherwise. Negative drops SHALL be classified as `"low"`. NaN SHALL be classified as `"low"`.
- [x] 3.8 Implement `leakage_severity(count) -> str` returning `"ok"` when `count == 0`, `"warning"` when `1 <= count <= 3`, `"critical"` when `count > 3`. Negative counts SHALL be treated as `0`.
- [x] 3.9 Implement `accuracy_by_ticker(df) -> pd.DataFrame` returning a DataFrame indexed by ticker with columns `count`, `accuracy`. Tickers with no labels SHALL have `accuracy == None`.
- [x] 3.10 Implement `apply_filters(df, filters) -> pd.DataFrame` applying the six filter dimensions (ticker list, prediction list, faithfulness level list, date range, cited-only, leakage-only) to any of the four dashboard DataFrames.
- [x] 3.11 Add unit tests in `tests/test_dashboard_metrics.py` for tasks 3.1–3.10, including boundary cases for `classify_faithfulness_level` (`0.20` → high, `0.19` → medium, `0.05` → medium, `0.049` → low, `-0.1` → low, `float("nan")` → low) and `leakage_severity` (`0` → ok, `1` → warning, `3` → warning, `4` → critical, `-1` → ok).

## 4. Data Loader and Adapter

- [x] 4.1 Define a `DashboardData` dataclass in `data_loader.py` with fields `predictions: Optional[pd.DataFrame]`, `evidence: Optional[pd.DataFrame]`, `faithfulness: Optional[pd.DataFrame]`, `leakage: Optional[pd.DataFrame]`, `missing_files: List[str]`, `empty_files: List[str]`.
- [x] 4.2 Implement `_read_csv_or_none(path) -> Optional[pd.DataFrame]` returning `None` when the file is absent, an empty DataFrame when the file has zero rows, and the loaded DataFrame otherwise. Files with the wrong columns SHALL raise `DashboardDataError`.
- [x] 4.3 Implement `_synthesize_evidence_rows(predictions_json_path) -> pd.DataFrame` reading `prediction_results.json` and emitting one row per `pro_evidence` / `counter_evidence` / `up_evidence` / `down_evidence` / `neutral_evidence` snippet. The `is_cited` flag SHALL be `True` for `pro_evidence` and `counter_evidence`, `False` for the others. The `evidence_role` column SHALL mirror the source list name.
- [x] 4.4 Implement `_synthesize_leakage_rows(predictions_json_path) -> pd.DataFrame` reading `prediction_results.json` and emitting one row per `TEMPORAL_LEAKAGE_BLOCKED` warning. The `leakage_minutes` SHALL be `(news_time - forecast_time) / 60` and SHALL be a positive number.
- [x] 4.5 Implement `_enrich_predictions(predictions_df, evidence_df) -> pd.DataFrame` adding `valid_news_count` and `invalid_future_news_count` columns derived from `evidence_df` grouped by `sample_id`. When `evidence_df` is empty / missing, the columns SHALL be `0`.
- [x] 4.6 Implement `_normalize_faithfulness(faithfulness_df) -> pd.DataFrame` renaming `confidence_after_removal` → `confidence_without_cited_evidence`, mapping `verdict` → `faithfulness_label` using `classify_faithfulness_level(confidence_drop)`. The original `verdict` column SHALL be retained as `verdict_legacy` for reference.
- [x] 4.7 Implement `load_dashboard_data(output_dir="outputs") -> DashboardData` that orchestrates the loaders, the synthesizers, and the normalizers, returning a `DashboardData` instance with all four DataFrames populated, with `missing_files` listing absent CSVs, and with `empty_files` listing present-but-empty CSVs.
- [x] 4.8 Add unit tests in `tests/test_dashboard_data_loader.py` covering the eleven scenarios from the spec: each proposal-shaped table loads from a healthy fixture; each loader raises `DashboardDataError` on a missing column; each loader returns `None` / empty when the file is missing; the adapter correctly synthesizes `valid_news_count`, `invalid_future_news_count`, `evidence_results`, and `temporal_leakage_results` from current-shape fixtures; the `faithfulness_label` is correctly derived from `confidence_drop`.

## 5. Chart Builders

- [x] 5.1 Implement `build_prediction_distribution_chart(df) -> plotly.graph_objects.Figure` returning a Plotly bar chart with one bar per `UP` / `DOWN` / `HOLD`. The bar height SHALL be the count of rows with that prediction. The figure SHALL be deterministic given the same input.
- [x] 5.2 Implement `build_confidence_drop_chart(df) -> plotly.graph_objects.Figure` returning a Plotly scatter chart with one point per `sample_id` and the `y` value as `confidence_drop`. The marker color SHALL be green / yellow / red per `classify_faithfulness_level`. The legend SHALL be hidden.
- [x] 5.3 Implement `build_temporal_leakage_chart(df) -> plotly.graph_objects.Figure` returning a Plotly bar chart of leakage count grouped by `ticker`.
- [x] 5.4 Implement `build_accuracy_by_ticker_chart(accuracy_df) -> plotly.graph_objects.Figure` returning a Plotly bar chart of accuracy per ticker.
- [x] 5.5 Add unit tests in `tests/test_dashboard_charts.py` (or extend `tests/test_dashboard_metrics.py`) that assert each builder returns a `go.Figure` with the expected trace count, x-axis category order, y-axis label, and marker-color mapping.

## 6. Streamlit Components

- [x] 6.1 Implement `render_sidebar(data) -> dict` in `components.py` that renders the six filters in the documented order and returns the active filter state as a dict with keys `tickers`, `predictions`, `faithfulness_levels`, `date_range`, `cited_only`, `leakage_only`. The "All" option for ticker / prediction / faithfulness-level SHALL expand to the union of available values from `data`.
- [x] 6.2 Implement `render_overview_tab(data, filtered_predictions, filtered_evidence, filtered_faithfulness, filtered_leakage) -> None` that renders the metric cards, the prediction distribution chart, the temporal-leakage count, the average temporal validity, and the accuracy-by-ticker table.
- [x] 6.3 Implement `render_evidence_tab(filtered_evidence) -> None` that renders the evidence table with the four visual cues (cited badge, temporal-leakage badge, evidence-role chip, support-score progress bar).
- [x] 6.4 Implement `render_confidence_drop_tab(filtered_faithfulness) -> None` that renders the confidence-drop chart, the faithfulness-level table, and the high/medium/low counts.
- [x] 6.5 Implement `render_temporal_leakage_tab(filtered_leakage) -> None` that renders the severity banner and the leakage table (sorted by `leakage_minutes` descending when severity is critical).
- [x] 6.6 Implement `render_case_detail_tab(data, filters) -> None` that exposes the `sample_id` selector and renders the case-detail panel using a static interpretation template.
- [x] 6.7 Add unit tests in `tests/test_dashboard_components.py` that snapshot the rendered output of each helper (verifiable by capturing the Streamlit `st.write` / `st.dataframe` calls and asserting on the captured text — the test should NOT need a running Streamlit server).

## 7. Streamlit App Glue

- [x] 7.1 Implement `app.py::main() -> None` that:
  - Calls `load_dashboard_data("outputs")`.
  - Calls `assert_dashboard_data(data)` and catches `DashboardDataError` for `st.error(...)`.
  - Renders the page title and caption.
  - Renders the sidebar.
  - Renders the five tabs and routes the right filtered DataFrame to each tab.
  - Caches the load with `@st.cache_data` keyed on the file mtimes.
- [x] 7.2 Add `if __name__ == "__main__": main()` so the file is runnable directly with `streamlit run src/dashboard/app.py`.
- [x] 7.3 Add a top-of-file `st.set_page_config(page_title="Faithfulness Dashboard", layout="wide")` call.

## 8. Sample Fixtures

- [x] 8.1 Create `samples/dashboard/healthy/` with four small CSVs: `prediction_results.csv` (5 rows, mix of UP / DOWN / HOLD with `label` present for some), `evidence_results.csv` (15 rows, mix of cited / non-cited, valid / invalid), `faithfulness_results.csv` (5 rows, all three faithfulness levels represented), `temporal_leakage_results.csv` (empty, no leakage).
- [x] 8.2 Create `samples/dashboard/leakage/` with the same schema but with one row in `evidence_results.csv` having `is_temporally_valid == False` and one row in `temporal_leakage_results.csv`.
- [x] 8.3 Create `samples/dashboard/faithfulness_levels/` with the same schema but with one row in `faithfulness_results.csv` for each of the three faithfulness levels (high / medium / low) at exact boundary confidence drops (0.20, 0.10, 0.01).
- [x] 8.4 Add `samples/dashboard/README.md` describing the schema and the example coverage.
- [x] 8.5 Add a parametrized regression test in `tests/test_dashboard_data_loader.py` that asserts byte-equality on every fixture pair.

## 9. Unit Tests — Acceptance Scenarios from the Spec

- [x] 9.1 Scenario 1 — Dashboard runs successfully (healthy load, no exception).
- [x] 9.2 Scenario 2 — Prediction distribution visible (count + chart + filter-narrows-chart).
- [x] 9.3 Scenario 3 — Evidence table visible (twelve columns + cited-only + ticker filters).
- [x] 9.4 Scenario 4 — Cited and invalid evidence are distinguishable (badges present).
- [x] 9.5 Scenario 5 — Confidence drop chart visible (high/medium/low classification at boundaries).
- [x] 9.6 Scenario 6 — Temporal leakage warning visible (1–3 rows → warning).
- [x] 9.7 Scenario 7 — No-leakage state handled (0 rows → OK banner, table hidden).
- [x] 9.8 Scenario 8 — Case detail supports demo (template-based interpretation, no LLM call).
- [x] 9.9 Scenario 9 — Missing / empty files handled gracefully (no unhandled exception).
- [x] 9.10 Scenario 10 — Sidebar filters are consistent across tabs (changing ticker updates all five tabs).
- [x] 9.11 Scenario 11 — Dashboard is read-only and deterministic (byte-equal snapshot of `outputs/` before and after a dashboard run).

## 10. Defensive Tests

- [x] 10.1 Test that the dashboard code does not import any LLM / network libraries (`openai`, `anthropic`, `transformers`, `finbert`, `huggingface_hub`, `requests`, `urllib`).
- [x] 10.2 Test that the dashboard does not import any of the upstream pipeline modules (`src.forecast_model`, `src.faithfulness_evaluator`, etc.) at runtime — the dashboard is read-only with respect to those modules.
- [x] 10.3 Test that `load_dashboard_data` is idempotent — calling it twice with the same files returns equal DataFrames.
- [x] 10.4 Test that `apply_filters` is a no-op when all filter values are `None` or `[]` or `(None, None)` for the date range.
- [x] 10.5 Test that the leakage table is sorted by `leakage_minutes` descending when severity is critical and by `sample_id` ascending otherwise.
- [x] 10.6 Test that the case-detail template is the same string constant across runs (no time-based or random content).
- [x] 10.7 Test that a fixture with a column type mismatch (e.g., `confidence` is a string) raises `DashboardDataError` from the loader, not a generic `ValueError` or `TypeError` from pandas.

## 11. Documentation

- [x] 11.1 Update `README.md` to add a "Visualization Dashboard" section with: how to run the dashboard (`streamlit run src/dashboard/app.py`), a screenshot placeholder for the Overview tab, the four-tab navigation summary, the adapter-layer note explaining the bridge between the proposal column contract and the current upstream output shapes, the limitations (academic use only, not a trading tool, no authentication), and a pointer to the sample fixtures.
- [x] 11.2 Document the rule-based scope in the module docstrings of `src/dashboard/metrics.py`, `src/dashboard/data_loader.py`, and `src/dashboard/charts.py` (no LLM, no network, no model training, no upstream pipeline re-run).
- [x] 11.3 Add a "Limitations" subsection enumerating: Streamlit is heavyweight for a static visualization, the adapter layer must be updated if the upstream output shape changes, the dashboard does not auto-refresh on file change, the dashboard is for academic / demo use only.
- [x] 11.4 Add a "Figure generation" subsection explaining how to capture screenshots for the final report: open the dashboard in a browser, navigate to each tab, take a screenshot at 1280x800, name them `fig_overview.png`, `fig_evidence.png`, `fig_confidence_drop.png`, `fig_temporal_leakage.png`, `fig_case_detail.png`. Note the Plotly chart export as an alternative (right-click → "Download plot as PNG").

## 12. Validation

- [x] 12.1 Run `pytest tests/ -v` and confirm a green run, including the new `test_dashboard_data_loader.py`, `test_dashboard_validators.py`, `test_dashboard_metrics.py`, and `test_dashboard_filters.py` suites, the golden fixture regression, and the acceptance-scenario tests.
- [x] 12.2 Run `openspec validate visualization-dashboard --strict` and resolve any reported issues.
- [x] 12.3 Run `openspec status --change visualization-dashboard` and confirm the change is ready to apply.
- [x] 12.4 Run `streamlit run src/dashboard/app.py` from a clean checkout, navigate the five tabs, and confirm the dashboard renders without error.
