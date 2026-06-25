# Faithfulness Evaluator — Golden Fixtures

Each pair below is a small JSON document used by
`tests/test_faithfulness_evaluator.py` to pin the Faithfulness
Evaluator's output byte-for-byte.

## Schema

Each `<scenario>_input.json` carries the `original_input` envelope
(`sample_id`, `ticker`, `forecast_time`, `evidence`) that the
Forecast Model consumes. The `original_result` carried by the test
is the corresponding `ForecastResult` dict — either produced by
`src.forecast_model.predict` (canonical) or hand-built when the
Forecast Model would normally filter the evidence out (e.g., the
temporal-leakage scenario).

The matching `<scenario>_expected.json` is the `FaithfulnessReport`
that the evaluator must produce on that pair. The regression test
asserts `expected == evaluate(input, result)`.

## Coverage

| Scenario | Input shape | Expected verdict | Notes |
|---|---|---|---|
| `01_strong_faithful` | 3 UP + 1 DOWN, prediction UP, 3 cited UP | `strong_faithful_candidate` | Ablation removes the 3 cited UP → prediction flips UP→DOWN. |
| `02_decorative` | 1 UP + 1 DOWN, prediction HOLD, both cited | `decorative_explanation_risk` | Ablation removes the 1 cited UP → still HOLD. |
| `03_temporal_leakage` | Cited evidence includes a future-dated item | `invalid_temporal_leakage` | Hand-built result; the Forecast Model would normally filter the future item out. |
| `04_unsupported` | Prediction UP, cited evidence all DOWN | `unsupported_evidence` | Hand-built result; the Forecast Model would never predict UP with only DOWN evidence. |

## Regeneration

The `_generate_fixtures.py` script is a one-shot helper that
re-materializes the `_expected.json` files. It is intentionally
idempotent — running it twice with the same code produces identical
output.
