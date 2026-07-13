# Spec: Stage Envelope

## ADDED Requirements

### Requirement: Accumulating envelope format

Dữ liệu trao đổi giữa các stage SHALL là một JSON document dạng `{"stage": <tên stage vừa chạy>, "samples": [<sample>, ...]}`. Mỗi stage SHALL chỉ bổ sung field vào từng sample và cập nhật giá trị `stage`; stage MUST NOT xóa hoặc ghi đè field do stage trước tạo ra.

#### Scenario: Stage bổ sung field, không phá field cũ

- **WHEN** envelope output của `retriever` (chứa `news`, `valid_news`, `invalid_future_news`) đi qua `evidence_extractor`
- **THEN** envelope output chứa thêm `evidence` trong mỗi sample, và mọi field trước đó (`news`, `valid_news`, `invalid_future_news`) vẫn nguyên vẹn

#### Scenario: Kết quả stage nằm dưới key riêng

- **WHEN** một stage tạo output (ví dụ forecast, selection, faithfulness, sufficiency, market)
- **THEN** kết quả được đặt dưới một key riêng của sample (`forecast`, `selection`, `coverage`, `faithfulness`, `sufficiency`, `market`) — không merge phẳng vào sample

### Requirement: Schema validation ở ranh giới stage

`src/schema.py` SHALL cung cấp `validate_sample(sample: dict, stage: str) -> list[str]` kiểm tra key bắt buộc và type của sample theo yêu cầu input của từng stage, chỉ dùng stdlib. Hàm SHALL trả về danh sách message lỗi (rỗng nếu hợp lệ), mỗi message nêu rõ `sample_id` và key lỗi.

#### Scenario: Sample thiếu key bắt buộc

- **WHEN** `validate_sample` nhận sample thiếu key mà stage yêu cầu (ví dụ thiếu `forecast` khi vào `faithfulness_evaluator`)
- **THEN** danh sách trả về chứa message nêu rõ sample_id và tên key thiếu

#### Scenario: Sample hợp lệ

- **WHEN** `validate_sample` nhận sample có đủ key đúng type cho stage đó
- **THEN** trả về danh sách rỗng

### Requirement: Deterministic serialization

Việc ghi envelope ra file SHALL deterministic: JSON với `sort_keys=True`, `indent=2`, `ensure_ascii=False`, kết thúc bằng newline. Cùng envelope → cùng file byte-for-byte.

#### Scenario: Ghi hai lần cho kết quả trùng khớp

- **WHEN** cùng một envelope được ghi ra hai file khác nhau
- **THEN** hai file giống nhau byte-for-byte
