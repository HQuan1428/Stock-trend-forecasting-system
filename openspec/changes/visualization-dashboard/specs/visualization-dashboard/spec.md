## ADDED Requirements

### Requirement: Dashboard Loads Result Files
The dashboard SHALL load four result files from `outputs/`: `prediction_results.csv`, `evidence_results.csv` (synthesized when missing), `faithfulness_results.csv`, and `temporal_leakage_results.csv` (synthesized when missing). The dashboard MUST be runnable with `streamlit run src/dashboard/app.py` and SHALL render a main title, a sidebar with six filters, and five tabs (Overview, Evidence, Confidence Drop, Temporal Leakage, Case Detail) without raising an unhandled exception.

#### Scenario: Healthy load
- **WHEN** the four result files exist and conform to the documented column contracts
- **THEN** the dashboard renders the title, sidebar, and five tabs without raising

#### Scenario: Missing file is handled gracefully
- **WHEN** one or more result files are absent
- **THEN** the dashboard SHALL display a user-friendly `st.warning(...)` banner naming the missing file and SHALL NOT raise an unhandled exception

#### Scenario: Empty file is handled gracefully
- **WHEN** a result file exists but contains zero data rows
- **THEN** the dashboard SHALL display a `st.info(...)` banner stating the file is empty and SHALL render the affected tab with an empty-state message

#### Scenario: Required column missing
- **WHEN** a result file exists but is missing a required column
- **THEN** the dashboard SHALL raise a `DashboardDataError` (a `ValueError` subclass) caught at the app boundary and rendered as `st.error(...)` listing the missing column names

### Requirement: Dashboard Shows Prediction Distribution
The Overview tab SHALL display the total number of forecasts, the count of `UP`, `DOWN`, and `HOLD` predictions, the accuracy (when `label` is present), the average confidence, the average confidence drop, the temporal leakage count, the average temporal validity, a Plotly bar chart of prediction distribution, and an accuracy-by-ticker table. The chart and the metric numbers MUST update when any sidebar filter changes.

#### Scenario: Distribution chart renders
- **WHEN** the user opens the Overview tab with unfiltered data
- **THEN** the tab SHALL show a Plotly bar chart with one bar per prediction class (`UP`, `DOWN`, `HOLD`) and the bar heights SHALL equal the count of rows with that prediction

#### Scenario: Filter narrows the distribution
- **WHEN** the user selects ticker `AAPL` in the sidebar
- **THEN** the bar chart, the total count, and the metric cards SHALL all reflect only rows with `ticker == "AAPL"`

#### Scenario: Accuracy shown only when labels exist
- **WHEN** the `label` column is present in `prediction_results.csv`
- **THEN** the Overview tab SHALL show the accuracy as a percentage; when the `label` column is absent, the dashboard SHALL hide the accuracy card and SHALL NOT raise

### Requirement: Dashboard Shows Evidence Table
The Evidence tab SHALL display a table of evidence rows with the columns `sample_id`, `ticker`, `forecast_time`, `news_time`, `prediction`, `evidence_text`, `polarity`, `expected_direction`, `evidence_role`, `support_score`, `is_cited`, and `is_temporally_valid`. The table MUST be sourced from the synthesized `evidence_results.csv` and SHALL respect all sidebar filters except the temporal-leakage-only filter (which only affects the Temporal Leakage tab).

#### Scenario: All evidence columns visible
- **WHEN** the user opens the Evidence tab
- **THEN** the table SHALL render with one row per evidence item and SHALL show all twelve required columns

#### Scenario: Cited-only filter
- **WHEN** the user toggles the "Show only cited evidence" filter to ON
- **THEN** the table SHALL show only rows where `is_cited == True` and SHALL hide non-cited rows

#### Scenario: Ticker filter
- **WHEN** the user selects ticker `AAPL` in the sidebar
- **THEN** the table SHALL show only rows with `ticker == "AAPL"`

### Requirement: Dashboard Distinguishes Cited and Invalid Evidence
The Evidence tab SHALL visually distinguish cited from non-cited evidence and SHALL clearly mark temporally invalid evidence. Cited rows MUST carry a "cited" badge; non-cited rows MUST be de-emphasized. Rows where `is_temporally_valid == False` MUST carry a "temporal leakage" badge in red; rows where `is_temporally_valid == True` MUST carry a green check icon.

#### Scenario: Cited badge present
- **WHEN** a row has `is_cited == True`
- **THEN** the table SHALL render a visible "cited" badge for that row

#### Scenario: Temporal leakage badge present
- **WHEN** a row has `is_temporally_valid == False`
- **THEN** the table SHALL render a red "temporal leakage" badge for that row

#### Scenario: Multiple badges coexist
- **WHEN** a row has `is_cited == True` and `is_temporally_valid == False`
- **THEN** the table SHALL render both the "cited" badge and the "temporal leakage" badge for the same row without overlap

### Requirement: Dashboard Shows Confidence Drop Analysis
The Confidence Drop tab SHALL display a Plotly chart of `confidence_drop` per `sample_id` (or aggregated by ticker when the dataset is large), the original confidence, the confidence after removal, the faithfulness level (`high` / `medium` / `low`), and a tabular summary. The faithfulness level SHALL be derived from `confidence_drop` using the thresholds `>= 0.20` → `high`, `0.05 ≤ drop < 0.20` → `medium`, `< 0.05` → `low`. Each row in the chart SHALL be color-coded by its faithfulness level (green = high, yellow = medium, red = low).

#### Scenario: Faithfulness level classification
- **WHEN** a row has `confidence_drop == 0.25`
- **THEN** the row SHALL be classified as `high` and rendered in green

- **WHEN** a row has `confidence_drop == 0.10`
- **THEN** the row SHALL be classified as `medium` and rendered in yellow

- **WHEN** a row has `confidence_drop == 0.01`
- **THEN** the row SHALL be classified as `low` and rendered in red

#### Scenario: Chart updates on filter
- **WHEN** the user changes the ticker filter
- **THEN** the chart, the summary table, and the metric numbers SHALL all reflect only the filtered rows

#### Scenario: Missing `confidence_drop` column
- **WHEN** `faithfulness_results.csv` does not contain `confidence_drop`
- **THEN** the dashboard SHALL raise `DashboardDataError` at the loader boundary and render a `st.error(...)` banner

### Requirement: Dashboard Shows Temporal Leakage Warning
The Temporal Leakage tab SHALL display a severity banner (OK / Warning / Critical) and a leakage table with the columns `sample_id`, `news_id`, `ticker`, `forecast_time`, `news_time`, `leakage_minutes`, and `news_text`. The severity SHALL be derived from the count of leakage rows using the thresholds `0` → `ok`, `1–3` → `warning`, `> 3` → `critical`. The banner color SHALL be green / yellow / red respectively.

#### Scenario: No leakage
- **WHEN** no rows have `news_time > forecast_time`
- **THEN** the tab SHALL show a green "OK — no temporal leakage detected" banner and SHALL hide the leakage table

#### Scenario: One to three leakage rows
- **WHEN** the leakage count is between 1 and 3 inclusive
- **THEN** the tab SHALL show a yellow "Warning" banner and SHALL render the leakage table

#### Scenario: More than three leakage rows
- **WHEN** the leakage count is greater than 3
- **THEN** the tab SHALL show a red "Critical" banner and SHALL render the leakage table sorted by `leakage_minutes` descending

#### Scenario: Leakage table columns
- **WHEN** the leakage table is rendered
- **THEN** the table SHALL show all seven required columns, with `leakage_minutes` formatted as a positive number (e.g., `12.5`)

### Requirement: Dashboard Supports Case Detail Demo
The Case Detail tab SHALL expose a `sample_id` selector populated with the `sample_id`s visible under the current filters. Selecting a `sample_id` SHALL render: ticker, forecast time, label (or "unlabeled"), prediction, original confidence, the cited evidence table (filtered to `is_cited == True` for that sample), the confidence after removal, the confidence drop, the faithfulness level, and a one-paragraph template-based interpretation. The interpretation MUST be assembled from a string template and the report fields; it MUST NOT call any LLM or external API.

#### Scenario: All fields render for a selected sample
- **WHEN** the user selects a `sample_id` that exists in the filtered data
- **THEN** the tab SHALL render all the fields above without raising

#### Scenario: Interpretation is template-based
- **WHEN** a `sample_id` is selected
- **THEN** the interpretation paragraph SHALL contain the prediction, original confidence, confidence drop, and faithfulness level, formatted from a static string template (verifiable by checking that the text appears in the rendered output and that no LLM/network call is made during the render)

#### Scenario: No cited evidence
- **WHEN** the selected `sample_id` has zero cited evidence rows
- **THEN** the cited evidence sub-table SHALL be replaced with an `st.info(...)` message "No cited evidence for this sample"

### Requirement: Dashboard Provides Consistent Sidebar Filters
The sidebar SHALL expose six filters: ticker (multi-select with "All" option), prediction (multi-select: All / UP / DOWN / HOLD), faithfulness level (multi-select: All / high / medium / low), forecast date range (two `st.date_input` widgets), cited-only (checkbox), and leakage-only (checkbox). All six filters SHALL be applied uniformly to every tab that displays data; the leakage-only filter SHALL additionally scope the Overview temporal-leakage count and the Confidence Drop chart.

#### Scenario: Filter state is consistent across tabs
- **WHEN** the user changes any sidebar filter
- **THEN** the Overview, Evidence, Confidence Drop, Temporal Leakage, and Case Detail tabs SHALL all reflect the new filter state on the next render

#### Scenario: Ticker filter applies to charts
- **WHEN** the user selects tickers `AAPL` and `GOOGL`
- **THEN** all charts and tables SHALL show only rows where `ticker` is in that set

#### Scenario: Faithfulness-level filter
- **WHEN** the user selects faithfulness level `high`
- **THEN** the Confidence Drop chart and the Overview metric cards SHALL show only rows where the faithfulness level is `high`

#### Scenario: Forecast date range
- **WHEN** the user picks a start date and an end date
- **THEN** the dashboard SHALL keep only rows with `forecast_time` in the inclusive range `[start, end]`; if no rows fall in the range, the dashboard SHALL show an `st.info(...)` empty-state message

#### Scenario: Cited-only filter
- **WHEN** the cited-only checkbox is ON
- **THEN** the Evidence tab SHALL show only rows where `is_cited == True`; the other tabs SHALL be unaffected (except Case Detail, which SHALL show a warning if the selected `sample_id` has no cited evidence)

#### Scenario: Leakage-only filter
- **WHEN** the leakage-only checkbox is ON
- **THEN** the Temporal Leakage tab SHALL show only rows where `news_time > forecast_time`; the Overview tab SHALL also restrict its temporal-leakage count to those rows

### Requirement: Dashboard Is Read-Only and Deterministic
The dashboard MUST NOT mutate any file under `outputs/` (or anywhere else on disk) during normal operation. The dashboard MUST be deterministic given the same input files (the same `sample_id` selection, the same filters, and the same input files SHALL produce the same rendered output). The dashboard MUST NOT invoke any LLM, FinBERT, transformer, logistic-regression, deep-learning model, or external API. The dashboard MUST NOT re-run the upstream pipeline.

#### Scenario: Dashboard does not mutate outputs
- **WHEN** the dashboard is run end-to-end
- **THEN** a byte-level snapshot of `outputs/` taken before the run SHALL equal the snapshot taken after the run (verifiable by `test_dashboard_does_not_mutate_outputs`)

#### Scenario: Determinism
- **WHEN** the dashboard is rendered twice with the same input files, same filters, and same `sample_id` selection
- **THEN** the rendered table values, chart trace data, and metric numbers SHALL be byte-equal across the two runs (verifiable by snapshotting the DataFrame inside the chart / component builder)

#### Scenario: No LLM or network call
- **WHEN** the dashboard code is loaded
- **THEN** the static import set SHALL NOT include `openai`, `anthropic`, `transformers`, `finbert`, `huggingface_hub`, `requests`, or `urllib` (verifiable by `test_dashboard_no_external_imports`)
