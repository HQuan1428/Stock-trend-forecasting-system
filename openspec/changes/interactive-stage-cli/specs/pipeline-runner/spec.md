# Spec: Pipeline Runner

## ADDED Requirements

### Requirement: Thin runner chạy end-to-end

`python -m src.runner --input <csv> --output-dir <dir>` SHALL chạy tuần tự chuỗi stage `ingest → retriever → evidence_extractor → forecast_model → evidence_selector → faithfulness_evaluator → sufficiency_evaluator → market_analyzer` bằng cách gọi `process()` của từng stage module in-process. Runner MUST NOT re-implement bất kỳ logic stage nào.

#### Scenario: Chạy end-to-end trên dataset mẫu

- **WHEN** chạy `python -m src.runner --input data/sample_dataset.csv --output-dir outputs`
- **THEN** exit code 0 và `outputs/` chứa đủ 8 file envelope trung gian `01_samples.json` … `08_market.json`

### Requirement: Ghi envelope trung gian từng stage

Runner SHALL ghi envelope sau mỗi stage ra file `NN_<tên>.json` (đánh số theo thứ tự chuỗi) trong `--output-dir`, dùng cùng serialization deterministic với CLI rời.

#### Scenario: File trung gian dùng lại được cho CLI rời

- **WHEN** runner đã chạy xong và user lấy `outputs/03_evidence.json` làm `--input` cho `python -m src.forecast_model`
- **THEN** stage chạy thành công và cho kết quả trùng với `outputs/04_forecast.json`

### Requirement: Dừng sớm với --stop-after

Runner SHALL hỗ trợ `--stop-after <stage>`: chạy đến hết stage được nêu rồi dừng, chỉ ghi các file của những stage đã chạy.

#### Scenario: Dừng sau forecast

- **WHEN** chạy runner với `--stop-after forecast_model`
- **THEN** `outputs/` có `01`–`04` và không có `05` trở đi

### Requirement: Xuất CSV kết quả

`src/export_csv.py` SHALL chuyển envelope cuối thành các file CSV: `prediction_results.csv`, `evidence_results.csv`, `faithfulness_results.csv` (gồm counterevidence_coverage B2), `sufficiency_results.csv` (B1), `market_consistency_results.csv` (B3), `temporal_leakage_results.csv` — cột và quy tắc dẫn xuất (faithfulness_label HIGH/MEDIUM/LOW, leakage_minutes) giữ nguyên như pipeline cũ. Runner SHALL gọi bước này sau stage cuối (trừ khi `--stop-after` dừng trước đó); bước này cũng chạy độc lập được qua `python -m src.export_csv --input <envelope> --output-dir <dir>`.

#### Scenario: CSV khớp kết quả pipeline cũ

- **WHEN** chạy runner trên `data/sample_dataset.csv` với logic stage không đổi
- **THEN** nội dung `prediction_results.csv` trùng với bản sinh bởi pipeline cũ trong git history

### Requirement: Determinism end-to-end

Chạy runner hai lần trên cùng input SHALL cho toàn bộ file output (JSON + CSV) giống nhau byte-for-byte.

#### Scenario: Hai lần chạy, diff rỗng

- **WHEN** chạy runner 2 lần vào 2 thư mục output khác nhau với cùng input CSV
- **THEN** `diff -r` giữa 2 thư mục rỗng
