## Why

Phase A đã trích xuất và phân loại evidence thành pro/counter/neutral, nhưng chưa có metric đo lường mức độ hệ thống phát hiện được counterevidence — bằng chứng trái chiều có thể ảnh hưởng đến độ tin cậy của prediction. Bổ sung **Counterevidence Coverage** là yêu cầu bắt buộc của Phase B2 (0.75 điểm) trong đồ án.

## What Changes

- Gọi `compute_coverage()` (đã có trong `src/evidence_selector.py`) từ pipeline sau bước Evidence Selector.
- Bổ sung 2 cột vào `outputs/faithfulness_results.csv`:
  - `counterevidence_coverage` (float 0.0–1.0): tỉ lệ counterevidence trên tổng directional evidence của sample
  - `counterevidence_detected` (bool): có tìm thấy ít nhất 1 counterevidence không
- Cập nhật `FAITHFULNESS_COLUMNS` trong `src/pipeline.py` và `src/dashboard/data_loader.py` để nhận 2 cột mới.
- Thêm metric card "Avg Counterevidence Coverage" vào dashboard (tab Faithfulness / Confidence Drop).

## Capabilities

### New Capabilities

- `counterevidence-coverage`: Đo lường tỉ lệ evidence trái chiều được phát hiện trong một prediction — proxy cho khả năng hệ thống tìm thấy cả hai chiều bằng chứng (balanced evidence detection).

### Modified Capabilities

- `evidence-extractor`: Không thay đổi spec, nhưng output của Evidence Selector (`counterevidence` list) sẽ được sử dụng trực tiếp bởi coverage metric.

## Impact

- **`src/pipeline.py`**: Thêm gọi `compute_coverage()` trong `_run_group()`, bổ sung 2 field vào `faithfulness_row`, cập nhật `FAITHFULNESS_COLUMNS`.
- **`src/evidence_selector.py`**: Không sửa — `compute_coverage()` đã tồn tại, chỉ cần gọi.
- **`src/dashboard/data_loader.py`**: Bổ sung 2 cột mới vào `FAITHFULNESS_COLUMNS` contract.
- **`src/dashboard/components.py`**: Thêm metric card counterevidence coverage vào `render_confidence_drop_tab`.
- **`tests/`**: Thêm test cases cho `compute_coverage()` integration trong pipeline và dashboard loader.
- **Breaking**: `faithfulness_results.csv` schema thêm 2 cột — dashboard cũ sẽ thiếu 2 cột này (cần update `data_loader.py` đồng thời).
