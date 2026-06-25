# Dashboard Sample Fixtures

Three fixture sets under this directory back the dashboard's unit tests
and give a reviewer something to load before any real pipeline run.

| Fixture | Records | Notes |
|---|---|---|
| `healthy/` | 5 predictions | Mix of UP / DOWN / HOLD, no temporal leakage. Faithfulness coverage is `high` + `low`. |
| `leakage/` | 5 predictions | Same shape as `healthy/` but record `DSH-03` has one cited evidence item with `news_time > forecast_time`. |
| `faithfulness_levels/` | 3 predictions | One record per faithfulness level: `DSH-HIGH` (high), `DSH-LOW` (low), `DSH-MED` (medium, hand-overridden). |

## Schema

Each fixture directory contains four CSVs in the proposal-defined
shape:

- `prediction_results.csv` — `sample_id`, `ticker`, `forecast_time`,
  `prediction`, `confidence`, `score`, `rationale`, `label`,
  `valid_news_count`, `invalid_future_news_count`.
- `evidence_results.csv` — `sample_id`, `news_id`, `ticker`,
  `forecast_time`, `news_time`, `news_text`, `evidence_text`,
  `polarity`, `expected_direction`, `evidence_role`, `support_score`,
  `is_cited`, `is_temporally_valid`.
- `faithfulness_results.csv` — `sample_id`, `ticker`, `forecast_time`,
  `prediction`, `original_confidence`,
  `confidence_without_cited_evidence`, `confidence_drop`,
  `evidence_support`, `temporal_validity`, `faithfulness_label`.
- `temporal_leakage_results.csv` — `sample_id`, `news_id`, `ticker`,
  `forecast_time`, `news_time`, `leakage_minutes`, `news_text`.

Plus the JSON sibling `prediction_results.json` used by the adapter
when the proposal-shaped CSVs are absent.

## Regeneration

To regenerate the fixtures from the upstream pipeline (recommended
after changes to the Forecast Model or Faithfulness Evaluator)::

```bash
python3 samples/dashboard/_generate_fixtures.py
```

The generator runs `predict_batch` + `evaluate_batch` on a small batch
and writes the proposal-shaped CSVs by hand. The output is
byte-stable across runs (deterministic upstream, fixed input records).
