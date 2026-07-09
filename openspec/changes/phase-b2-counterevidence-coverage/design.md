## Context

`EvidenceSelector.compute_coverage()` đã tồn tại trong `src/evidence_selector.py` (dòng 414–460). Hàm này nhận `result` (output của Evidence Selector) và `expected_labels` (dict `news_id → "pro"/"counter"/"neutral"`) và trả về 4 metrics bao gồm `counterevidence_coverage` và `counterevidence_detected_rate`.

Hiện tại `FaithfulnessEvaluator` và `pipeline.py` không gọi `EvidenceSelector.compute_coverage()`. `faithfulness_results.csv` chưa có cột counterevidence.

## Goals / Non-Goals

**Goals:**
- Wire `EvidenceSelector.compute_coverage()` vào `pipeline.py::PipelineRunner._run_group()` sau bước Evidence Selector.
- Bổ sung 2 cột vào `faithfulness_results.csv`: `counterevidence_coverage`, `counterevidence_detected`.
- Hiển thị coverage metric trên dashboard (1 metric card).
- Giữ backward compatibility với sample fixtures hiện có bằng cách dùng `get()` với default khi đọc CSV.

**Non-Goals:**
- Không sửa logic của `EvidenceSelector.compute_coverage()` hay Evidence Selector.
- Không thêm manual annotation vào dataset.
- Không tạo file output riêng — cột mới thêm vào `faithfulness_results.csv` hiện có.

## Decisions

**D1 — Cách xây dựng `expected_labels` không cần annotation thủ công**

`EvidenceSelector.compute_coverage()` nhận `expected_labels: Dict[str, str]` — mapping từ `news_id` sang `"pro"/"counter"/"neutral"`. Trong pipeline, ta không có annotation thủ công.

**Chọn**: Derive `expected_labels` từ `evidence_candidates` bằng cách áp dụng `EvidenceSelector.CLASSIFICATION_TABLE` của Evidence Selector (cùng bảng tra mà selector đang dùng):

```python
from src.evidence_selector import EvidenceSelector
expected_labels = {
    cand["news_id"]: EvidenceSelector.CLASSIFICATION_TABLE.get(
        (prediction, cand.get("expected_direction", "HOLD")), "neutral"
    )
    for cand in evidence_candidates
}
```

**Tại sao không dùng annotation thủ công?** Prototype scope — dataset 30–100 dòng không có ground truth annotation. Derived labels từ classification table là consistent và deterministic.

**Hệ quả**: Khi selector không áp dụng `top_k` cắt bớt, coverage = 1.0 (vì selector và expected dùng cùng rule). Coverage < 1.0 xảy ra khi `top_k_counter` bị giới hạn (default=3) và số counterevidence candidates > 3. Đây là signal đúng: có nhiều bằng chứng trái chiều nhưng chỉ một phần được đưa vào report.

**D2 — Tên 2 cột mới**

- `counterevidence_coverage` (float 0.0–1.0): trực tiếp từ `EvidenceSelector.compute_coverage()`.
- `counterevidence_detected` (bool): True khi `counterevidence_detected_rate == 1.0` (ít nhất 1 counterevidence được phát hiện). Dùng bool thay vì float để dễ filter trên dashboard.

**D3 — Không sửa `FaithfulnessEvaluator`**

Coverage là pipeline-level metric, không phải faithfulness-level metric. Tính trong `PipelineRunner._run_group()` của `pipeline.py` và ghi trực tiếp vào `faithfulness_row` — giữ `FaithfulnessEvaluator` độc lập (single responsibility).

**D4 — Dashboard: thêm vào tab hiện có, không tạo tab mới**

Thêm 1 metric card vào `render_confidence_drop_tab()` trong `components.py`. Tab này đã hiển thị faithfulness metrics — counterevidence coverage là metric faithfulness phụ thêm, không cần tab riêng.

## Risks / Trade-offs

**[Risk] Coverage luôn = 1.0 khi top_k không bị giới hạn** → Acceptable: `counterevidence_detected` (bool) vẫn hữu ích để filter "có/không có counterevidence". Phần demo sẽ nhấn vào `counterevidence_detected` và tỉ lệ sample có counterevidence trong dataset.

**[Risk] `faithfulness_results.csv` schema thay đổi** → Cập nhật `FAITHFULNESS_COLUMNS` trong cả `pipeline.py` và `data_loader.py` cùng lúc trong một PR. Dashboard cũ load file cũ thiếu 2 cột sẽ được handle bởi `_normalize_faithfulness()` trong `data_loader.py` với `get(..., default)`.
