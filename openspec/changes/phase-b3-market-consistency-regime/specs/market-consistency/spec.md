## ADDED Requirements

### Requirement: MarketAnalyzer computes market consistency and regime

`MarketAnalyzer.analyze(group_row)` SHALL return a dict with the following fields:

- `market_consistent` (bool): `True` nếu prediction direction khớp với dấu `next_day_return` theo ngưỡng.
- `market_consistency_score` (float, 1.0 hoặc 0.0): `1.0` nếu `market_consistent`, else `0.0`.
- `regime` (str: `"bull"` / `"bear"` / `"sideways"`): phân loại chế độ thị trường từ `price_5d_return`.
- `next_day_return` (float): giá trị từ input, echoed lại.
- `price_5d_return` (float): giá trị từ input, echoed lại.

**Mapping prediction → thị trường:**
- `UP` khớp khi `next_day_return > 0.005`
- `DOWN` khớp khi `next_day_return < -0.005`
- `HOLD` khớp khi `-0.005 <= next_day_return <= 0.005`

**Regime classification từ `price_5d_return`:**
- `"bull"` nếu `price_5d_return > 0.02`
- `"bear"` nếu `price_5d_return < -0.02`
- `"sideways"` nếu `-0.02 <= price_5d_return <= 0.02`

The analyzer MUST NOT use any LLM, ML model, or external API. It is deterministic and pure.

#### Scenario: UP prediction consistent with positive return
- **WHEN** prediction is `UP` and `next_day_return = 0.02`
- **THEN** `market_consistent` is `True`
- **AND** `market_consistency_score` is `1.0`

#### Scenario: UP prediction inconsistent with negative return
- **WHEN** prediction is `UP` and `next_day_return = -0.015`
- **THEN** `market_consistent` is `False`
- **AND** `market_consistency_score` is `0.0`

#### Scenario: HOLD prediction in neutral band
- **WHEN** prediction is `HOLD` and `next_day_return = 0.001`
- **THEN** `market_consistent` is `True`

#### Scenario: HOLD prediction inconsistent with strong move
- **WHEN** prediction is `HOLD` and `next_day_return = 0.03`
- **THEN** `market_consistent` is `False`

#### Scenario: Bull regime classification
- **WHEN** `price_5d_return = 0.03`
- **THEN** `regime` is `"bull"`

#### Scenario: Bear regime classification
- **WHEN** `price_5d_return = -0.025`
- **THEN** `regime` is `"bear"`

#### Scenario: Sideways regime classification
- **WHEN** `price_5d_return = 0.01`
- **THEN** `regime` is `"sideways"`

---

### Requirement: Pipeline writes market_consistency_results.csv

After the Sufficiency Evaluator step, the pipeline SHALL compute market consistency metrics and write `outputs/market_consistency_results.csv` with exactly these columns (in order):

```
sample_id, ticker, forecast_time, prediction,
next_day_return, price_5d_return,
market_consistent, regime, market_consistency_score
```

When the input CSV does not contain `next_day_return` or `price_5d_return` columns, the pipeline SHALL still write the file with those fields defaulting to `0.0` and `regime` to `"sideways"`.

#### Scenario: Pipeline run produces market consistency output
- **WHEN** `python -m src.pipeline` completes on a valid input CSV with market columns
- **THEN** `outputs/market_consistency_results.csv` exists with the required 9 columns
- **AND** `market_consistency_score` values are `0.0` or `1.0`
- **AND** `regime` values are one of `"bull"`, `"bear"`, `"sideways"`

#### Scenario: One row per (ticker, forecast_time) group
- **WHEN** input CSV has N unique (ticker, forecast_time) groups
- **THEN** `market_consistency_results.csv` has exactly N rows

#### Scenario: Missing market columns → defaults
- **WHEN** input CSV does not contain `next_day_return` or `price_5d_return`
- **THEN** pipeline does not raise, defaults to `next_day_return=0.0`, `price_5d_return=0.0`, `regime="sideways"`

---

### Requirement: Dashboard renders Market Consistency tab

The dashboard SHALL include a "Market Consistency" tab that displays:
- At least 2 summary metric cards: overall market consistency rate (% of samples where `market_consistent=True`) and accuracy breakdown by regime.
- A table of per-sample results showing `ticker`, `prediction`, `next_day_return`, `market_consistent`, `regime`.

#### Scenario: Market tab renders without crash
- **WHEN** `streamlit run src/dashboard/app.py` opens and `market_consistency_results.csv` exists
- **THEN** the "Market Consistency" tab renders without error

#### Scenario: Market tab handles missing file gracefully
- **WHEN** `market_consistency_results.csv` does not exist
- **THEN** the tab displays an informational message and MUST NOT raise an exception
