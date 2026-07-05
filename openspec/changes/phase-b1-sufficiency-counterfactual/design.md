## Context

Phase A đã có `predict_without_evidence()` (xóa cited evidence) và `predict()` (full evidence). Faithfulness Evaluator dùng hai hàm này để tính `confidence_drop`. Phase B1 cần thêm 2 góc nhìn:

1. **Sufficiency**: Chỉ dùng cited evidence (không có uncited evidence) — liệu đó có đủ để ra prediction không?
2. **Counterfactual**: Thay cited evidence bằng neutral placeholder — confidence thay đổi bao nhiêu?

Cả hai đều reuse `predict()` từ `src.forecast_model` — không cần ML model mới.

## Goals / Non-Goals

**Goals:**
- Module `src/sufficiency_evaluator.py` độc lập, pure, deterministic, không IO.
- Pipeline ghi `outputs/sufficiency_results.csv` với 10 cột chuẩn.
- Dashboard có tab mới hiển thị sufficiency_score và counterfactual_delta per sample.

**Non-Goals:**
- Không thay đổi `faithfulness_results.csv` hay bất kỳ output cũ nào.
- Không dùng LLM, ML model, hay external API.
- Không implement individual-item ablation (ablate từng evidence riêng lẻ) — đó là extension tương lai.

## Decisions

**D1 — Input của SufficiencyEvaluator**

`SufficiencyEvaluator.evaluate(original_input, original_result, cited_evidence_ids)` nhận:
- `original_input`: forecast request dict (cùng dạng với FaithfulnessEvaluator)
- `original_result`: kết quả từ `predict()` gốc
- `cited_evidence_ids`: set[str] — news_id của cited evidence (từ pro + counter của Evidence Selector)

**Lý do không nhận selector_result trực tiếp**: giữ SufficiencyEvaluator độc lập khỏi Evidence Selector, pipeline cung cấp `cited_ids` (đã tính sẵn trong `_run_group()`).

**D2 — Sufficiency: chỉ giữ cited evidence**

```python
cited_only_evidence = [ev for ev in evidence if ev["news_id"] in cited_evidence_ids]
```
Chạy `predict({..., "evidence": cited_only_evidence})` → `sufficiency_result`.

- `sufficiency_confidence` = `sufficiency_result["confidence"]`
- `sufficiency_score` = `min(sufficiency_confidence / original_confidence, 1.0)` nếu `original_confidence > 0`, else `0.0`
- `prediction_on_only_cited` = `sufficiency_result["prediction"]`

**D3 — Counterfactual: thay cited evidence bằng neutral placeholder**

Với mỗi cited evidence item, tạo neutral placeholder:
```python
{
    "evidence_id": f"{news_id}_NEUTRAL",
    "news_id": news_id,
    "news_time": original_item["news_time"],
    "evidence_text": "",
    "polarity": "neutral",
    "expected_direction": "HOLD",
    "support_score": 0.5,
}
```
Evidence uncited được giữ nguyên. Chạy `predict({..., "evidence": perturbed_evidence})` → `counterfactual_result`.

- `counterfactual_confidence` = `counterfactual_result["confidence"]`
- `counterfactual_delta` = `original_confidence - counterfactual_confidence` (positive = cited evidence quan trọng)

**D4 — Output CSV riêng, không sửa faithfulness_results.csv**

Schema `sufficiency_results.csv` (10 cột):
```
sample_id, ticker, forecast_time, prediction, original_confidence,
sufficiency_confidence, sufficiency_score, prediction_on_only_cited,
counterfactual_confidence, counterfactual_delta
```

Giữ backward compat tuyệt đối với Phase A outputs.

**D5 — Dashboard: tab mới "Sufficiency"**

Thêm vào `src/dashboard/app.py` một tab thứ 6, render bằng `render_sufficiency_tab()` mới trong `components.py`. `DashboardData` thêm field `sufficiency: Optional[pd.DataFrame]`.

## Risks / Trade-offs

**[Risk] Sufficiency_score luôn = 1.0 khi model vote chỉ từ cited evidence** → Acceptable: `counterfactual_delta` và `prediction_on_only_cited` vẫn cung cấp thông tin. Khi tất cả evidence là cited, sufficiency=1.0 là đúng về nghĩa.

**[Risk] Counterfactual placeholder cứng "HOLD"** → neutral evidence giảm score về 0, confidence về 0.5 — đây là behavior đúng và deterministic.

**[Risk] `sufficiency_results.csv` chưa có trong `samples/dashboard/`** → Dashboard dùng `get(..., None)` với warning message khi file chưa tồn tại, không crash.
