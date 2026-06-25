# Forecast Model — Sample I/O

Golden fixtures for `predict`. Each pair (`_input.json` + `_expected.json`)
is locked in by a parametrized regression test in
`tests/test_forecast_model.py`.

## Schema

### Input (per fixture)

| Field           | Required | Notes                                                          |
|-----------------|----------|----------------------------------------------------------------|
| `sample_id`     | yes      | Stable identifier; echoed in output.                           |
| `ticker`        | yes      | Stock ticker; echoed in output. Not used as a filter.          |
| `forecast_time` | yes      | Naive ISO timestamp interpreted as UTC.                        |
| `evidence`      | yes      | List of selected evidence items (may be empty).                |
| `label`         | no       | Ground truth, echoed in output. NEVER read by `predict`.       |

Each `evidence` entry requires `evidence_id`, `news_id`, `news_time`,
`evidence_text`, `polarity`, and `expected_direction`. `support_score` is
optional (defaulted to `0.0` in output).

### Output (per fixture)

The full `ForecastResult` dict matching the spec's output schema. See
`01_up_expected.json` for a worked example covering every output field,
including all five evidence lists and `model_version`.

## Coverage

| Fixture stem              | Scenario                          | Key result                                         |
|---------------------------|-----------------------------------|----------------------------------------------------|
| `01_up`                   | 3 UP + 1 DOWN                     | `UP`, score 2, confidence 0.7, rationale UP         |
| `02_down`                 | 1 UP + 3 DOWN                     | `DOWN`, score -2, confidence 0.7, rationale DOWN     |
| `03_balanced_hold`        | 2 UP + 2 DOWN                     | `HOLD`, score 0, confidence 0.5, balanced rationale  |
| `04_empty_hold`           | empty evidence                    | `HOLD`, confidence 0.5, "no valid directional"      |
| `05_future_evidence`      | mixed evidence + one future item  | future item excluded, `TEMPORAL_LEAKAGE_BLOCKED`   |

`05_future_evidence` is the canonical example that exercises the temporal
defense-in-depth path. The other four fixtures pin the directional-evidence
matrix for the four canonical prediction branches.