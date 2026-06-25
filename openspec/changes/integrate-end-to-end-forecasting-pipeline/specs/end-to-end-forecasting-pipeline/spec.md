## ADDED Requirements

### Requirement: Single-command pipeline execution

The system SHALL provide a CLI command `python -m src.pipeline` that, given a CSV of news rows, produces all four output CSVs under a target directory in a single run.

#### Scenario: Default invocation on the sample dataset
- **WHEN** the user runs `python -m src.pipeline` with no arguments from the repository root
- **THEN** the pipeline reads `data/sample_dataset.csv`, writes `outputs/prediction_results.csv`, `outputs/evidence_results.csv`, `outputs/faithfulness_results.csv`, and `outputs/temporal_leakage_results.csv`, and exits with status code 0.

#### Scenario: Custom input and output paths
- **WHEN** the user runs `python -m src.pipeline --input <path> --output-dir <path>`
- **THEN** the pipeline reads the CSV at `<path>` and writes the four output CSVs under `<path>`, creating `<path>` if it does not already exist.

#### Scenario: Renamed column override
- **WHEN** the user runs `python -m src.pipeline --ticker-column SYMBOL --news-time-column published_at --forecast-time-column as_of`
- **THEN** the pipeline partitions rows using the renamed columns and the rest of the run is unchanged.

### Requirement: Shared data contracts

The system SHALL expose lightweight dataclasses in `src/schema.py` describing the cross-stage data flow: `NewsRecord`, `EvidenceItem`, `ForecastResult`, `FaithfulnessResult`, `PipelineResult`.

#### Scenario: Imports resolve
- **WHEN** a caller does `from src.schema import NewsRecord, EvidenceItem, ForecastResult, FaithfulnessResult, PipelineResult`
- **THEN** every name resolves to a documented dataclass with the fields described below.

#### Scenario: Field presence
- **WHEN** the caller inspects each dataclass
- **THEN** `NewsRecord` exposes `news_id`, `ticker`, `forecast_time`, `news_time`, `news_text`, `label`; `EvidenceItem` exposes `evidence_id`, `news_id`, `news_time`, `evidence_text`, `polarity`, `expected_direction`, `support_score`, `evidence_role`, `is_cited`; `ForecastResult` exposes `prediction`, `confidence`, `score`, `positive_count`, `negative_count`, `neutral_count`, `rationale`, `warnings`; `FaithfulnessResult` exposes `temporal_validity`, `evidence_support`, `confidence_drop`, `faithfulness_label`; `PipelineResult` exposes `ticker`, `forecast_time`, `prediction`, `faithfulness_label`, `valid_news_count`, `invalid_future_news_count`.

### Requirement: Temporal safety for future news

The system MUST never pass a news item whose `news_time > forecast_time` into the Evidence Extractor, Evidence Selector, Forecast Model, or Faithfulness Evaluator. Future news MUST flow only into the leakage report.

#### Scenario: Future news is excluded from prediction
- **WHEN** a `(ticker, forecast_time)` group contains at least one row with `news_time > forecast_time`
- **THEN** that row's `news_id` appears in `outputs/temporal_leakage_results.csv` and is absent from the `evidence` list passed to `extract_evidence`, `select_evidence`, `predict`, and `FaithfulnessEvaluator.evaluate`.

#### Scenario: All-future group still produces a prediction row
- **WHEN** every row in a group has `news_time > forecast_time`
- **THEN** the pipeline still emits one row in `outputs/prediction_results.csv` for that group with `prediction=HOLD`, `valid_news_count=0`, `invalid_future_news_count>0`, and no rows in `outputs/evidence_results.csv`.

### Requirement: Required output file set

The system MUST produce exactly these four files in the `--output-dir`: `prediction_results.csv`, `evidence_results.csv`, `faithfulness_results.csv`, `temporal_leakage_results.csv`. The dashboard (`src/dashboard/app.py`) MUST be able to load them without falling back to synthesizing from JSON.

#### Scenario: File presence after a successful run
- **WHEN** the pipeline completes without error
- **THEN** all four files exist on disk, each with at least the required columns below.

#### Scenario: prediction_results.csv schema
- **WHEN** the dashboard loads `prediction_results.csv`
- **THEN** the file contains the columns `ticker`, `forecast_time`, `prediction`, `confidence`, `score`, `label`, `is_correct`, `rationale`, `cited_evidence_count`, `valid_news_count`, `invalid_future_news_count`.

#### Scenario: evidence_results.csv schema
- **WHEN** the dashboard loads `evidence_results.csv`
- **THEN** the file contains the columns `ticker`, `forecast_time`, `news_id`, `news_time`, `evidence_text`, `polarity`, `expected_direction`, `evidence_role`, `support_score`, `is_cited`, and `evidence_role` is one of `pro`, `counter`, `neutral` for every row.

#### Scenario: faithfulness_results.csv schema
- **WHEN** the dashboard loads `faithfulness_results.csv`
- **THEN** the file contains the columns `ticker`, `forecast_time`, `prediction`, `original_confidence`, `confidence_without_cited_evidence`, `confidence_drop`, `temporal_validity`, `evidence_support`, `faithfulness_label`, where `faithfulness_label` is one of `HIGH`, `MEDIUM`, `LOW`.

#### Scenario: temporal_leakage_results.csv schema
- **WHEN** the dashboard loads `temporal_leakage_results.csv`
- **THEN** the file contains the columns `ticker`, `forecast_time`, `news_id`, `news_time`, `news_text`, `leakage_type`, and `leakage_type` is the literal `future_news` for every row.

### Requirement: Faithfulness label rule

The pipeline SHALL compute `faithfulness_label` for each group with the rule:
- `HIGH` if `confidence_drop >= 0.20` and `temporal_validity == 1.0`
- `MEDIUM` if `confidence_drop >= 0.05` and `temporal_validity == 1.0`
- `LOW` otherwise.

#### Scenario: High label when both thresholds pass
- **WHEN** a group has `confidence_drop == 0.25` and `temporal_validity == 1.0`
- **THEN** the `faithfulness_label` for that group in `faithfulness_results.csv` is `HIGH`.

#### Scenario: Low label when temporal validity is broken
- **WHEN** a group has `confidence_drop == 0.30` but `temporal_validity < 1.0`
- **THEN** the `faithfulness_label` is `LOW` even though the drop threshold passes.

### Requirement: Confidence drop computation

The pipeline MUST compute `confidence_drop = original_confidence - confidence_without_cited_evidence` for every group whose cited evidence is non-empty. The value MUST be a finite float (not `NaN`, not `±Inf`).

#### Scenario: Single cited evidence removed
- **WHEN** a group has exactly one cited evidence item and the Forecast Model re-run with that item removed returns a lower confidence
- **THEN** the row's `confidence_drop` is positive and finite.

#### Scenario: Empty cited evidence
- **WHEN** a group has zero cited evidence items
- **THEN** the row's `confidence_drop` is `0.0` and the row is still written to `faithfulness_results.csv`.

### Requirement: Module reuse without rewrites

The pipeline MUST reuse `src.retriever.retrieve_valid_news`, `src.evidence_extractor.extract_evidence_batch`, `src.evidence_selector.select_evidence_batch`, `src.forecast_model.predict`, `src.forecast_model.predict_without_evidence`, and `src.faithfulness_evaluator.FaithfulnessEvaluator.evaluate` as black-box functions. It MUST NOT reimplement temporal filtering, keyword matching, classification logic, voting, or ablation logic.

#### Scenario: No duplicate logic
- **WHEN** the pipeline source is grepped for keyword lists, vote counts, or classification rules
- **THEN** none of the upstream constants are redefined; the pipeline only orchestrates.

### Requirement: Integration tests

The system SHALL provide `tests/test_pipeline.py` covering at least: pipeline completes without error, future news is excluded from prediction, valid news is fed into extraction, all four output files are created, `confidence_drop` is finite, a group with future news shows `invalid_future_news_count > 0`, and the four output CSVs contain the required columns.

#### Scenario: Smoke test on the real sample dataset
- **WHEN** `tests/test_pipeline.py` is invoked with the real `data/sample_dataset.csv`
- **THEN** the run produces all four files and every assertion passes.

#### Scenario: Synthetic minimal CSV
- **WHEN** the test feeds a 3-row in-memory CSV with one valid row, one future row, and one valid-row-of-a-different-group
- **THEN** the run produces exactly two groups in `prediction_results.csv`, exactly one leakage row in `temporal_leakage_results.csv`, and zero leakage rows for the all-valid group.

### Requirement: README documents the canonical run

The repository `README.md` SHALL contain a section titled "Run the pipeline" that includes the canonical command, a list of the four output files with one-line descriptions, and a short end-to-end explanation.

#### Scenario: New reader follows the README
- **WHEN** a reader runs the command from the README on a clean checkout
- **THEN** they can produce all four CSVs in under a minute and read them with the existing dashboard.