# Sample Dataset

The file `sample_dataset.csv` is a small, hand-crafted dataset used to
demo and regression-test the temporal-retriever pipeline.

## Schema

| Column         | Type        | Notes                                                |
|----------------|-------------|------------------------------------------------------|
| `news_id`      | string      | Unique identifier of the news item.                   |
| `ticker`       | string      | Stock ticker the news is associated with.            |
| `forecast_time`| ISO 8601    | Naive timestamp (interpreted as UTC).                 |
| `news_time`    | ISO 8601    | Publication time of the news. Naive = UTC.           |
| `news_text`    | string      | Body of the news item.                               |
| `label`        | string      | Forecast label: `UP`, `DOWN`, or `HOLD`.             |

## Temporal scenario coverage

The first three rows are tagged for quick reference when demoing or
writing regression tests. They cover the three temporal scenarios
relative to each row's `forecast_time`:

| `news_id` | Scenario          | Notes                                   |
|-----------|-------------------|-----------------------------------------|
| `1`       | `valid` (past)    | `news_time` is before `forecast_time`.  |
| `2`       | `invalid_future`  | `news_time` is after `forecast_time`.   |
| `3`       | `equal`           | `news_time == forecast_time` (valid).   |

These three rows are sufficient for the temporal-retriever regression
suite. The remaining rows (`news_id` 4..100) are an unlabeled mix of
scenarios used to feed the broader pipeline demo.
