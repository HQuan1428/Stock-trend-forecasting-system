# Spec: Stage CLI

## ADDED Requirements

### Requirement: Mỗi stage chạy độc lập qua CLI

Mỗi stage runtime (`ingest`, `retriever`, `evidence_extractor`, `forecast_model`, `evidence_selector`, `faithfulness_evaluator`, `sufficiency_evaluator`, `market_analyzer`) SHALL chạy được độc lập bằng `python -m src.<stage> --input <in> -o <out>`. Stage `ingest` nhận CSV; các stage còn lại nhận envelope JSON. Business logic của các stage class MUST NOT thay đổi — CLI chỉ là adapter.

#### Scenario: Chạy một stage với input hợp lệ

- **WHEN** chạy `python -m src.retriever --input 01_samples.json -o 02_retrieved.json` với envelope hợp lệ
- **THEN** exit code 0 và `02_retrieved.json` chứa envelope đã bổ sung `valid_news`/`invalid_future_news` cho từng sample

#### Scenario: Nối chuỗi hai stage qua file

- **WHEN** output file của stage N được đưa làm `--input` cho stage N+1 theo đúng thứ tự chuỗi
- **THEN** stage N+1 chạy thành công không cần chỉnh sửa file

### Requirement: Hàm process() là code path duy nhất

Mỗi stage module SHALL cung cấp hàm module-level `process(envelope: dict) -> dict` thuần (không I/O file, không phụ thuộc thời gian thực). CLI `main()` và runner SHALL cùng gọi `process()` — không tồn tại code path thứ hai.

#### Scenario: CLI và runner cho cùng kết quả

- **WHEN** cùng một envelope đi qua một stage bằng CLI rời và bằng runner
- **THEN** envelope kết quả giống nhau

### Requirement: Ingest chuyển CSV thành envelope

`python -m src.ingest` SHALL đọc CSV có các cột `news_id, ticker, forecast_time, news_time, news_text, label` (tùy chọn `next_day_return, price_5d_return`) bằng stdlib `csv`, group các dòng theo `(ticker, forecast_time)` giữ nguyên thứ tự xuất hiện, sinh `sample_id` từ ticker + forecast_time, và ghi envelope đầu tiên.

#### Scenario: Group giữ thứ tự xuất hiện

- **WHEN** CSV có các dòng thuộc 3 nhóm `(ticker, forecast_time)` xen kẽ nhau
- **THEN** envelope chứa đúng 3 sample theo thứ tự nhóm xuất hiện lần đầu trong CSV, mỗi sample gom đủ các dòng news của nhóm mình

#### Scenario: Cột giá thiếu được mặc định 0.0

- **WHEN** CSV không có cột `next_day_return`/`price_5d_return`
- **THEN** sample nhận giá trị `0.0` cho các field đó, không lỗi

### Requirement: Input hỏng → exit code 2 với message rõ ràng

Khi file input không tồn tại, không phải JSON hợp lệ, hoặc sample không qua được `validate_sample`, CLI SHALL in message lỗi ra stderr (nêu rõ sample_id/key lỗi khi validation fail) và exit code 2. Bug nội bộ SHALL để traceback nổi lên bình thường, không nuốt lỗi.

#### Scenario: Envelope thiếu key stage yêu cầu

- **WHEN** chạy `python -m src.faithfulness_evaluator` với envelope chưa có `forecast` trong sample
- **THEN** exit code 2 và stderr chứa message nêu sample_id và key `forecast` bị thiếu

#### Scenario: File input không tồn tại

- **WHEN** chạy stage với `--input` trỏ tới file không tồn tại
- **THEN** exit code 2 và stderr nêu rõ đường dẫn không tìm thấy
