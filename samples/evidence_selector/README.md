# Evidence Selector — Sample I/O

Golden fixtures for `select_evidence`. Each pair (`_input.json` +
`_expected.json`) is locked in by a parametrized regression test in
`tests/test_evidence_selector.py`.

## Schema

### Input (per fixture)

| Field                 | Required | Notes                                            |
|-----------------------|----------|--------------------------------------------------|
| `ticker`              | yes      | Stock ticker (echoed in output).                 |
| `forecast_time`       | yes      | Naive ISO timestamp interpreted as UTC.          |
| `prediction`          | yes      | One of `UP`, `DOWN`, `HOLD`.                     |
| `confidence`          | yes      | Echoed in output.                                |
| `evidence_candidates` | yes      | List of candidate objects with 7 fields each.    |

### Output (per fixture)

`SelectionResult` JSON matching the spec's output schema. See
`01_up_with_counter_expected.json` for a worked example covering all
fields, including `invalid_future_evidence`.

## Coverage

| Fixture stem                    | Prediction | Expected groups populated                         |
|---------------------------------|------------|---------------------------------------------------|
| `01_up_with_counter`            | UP         | pro=1, counter=1, neutral=1, invalid_future=1     |
| `02_down`                       | DOWN       | pro=1, counter=1, neutral=0, invalid_future=0     |
| `03_hold`                       | HOLD       | pro=1, counter=1, neutral=0, invalid_future=0     |

The UP fixture is the canonical example that exercises every output
list at once. The DOWN and HOLD fixtures pin the directional evidence
matrix for the remaining two predictions.