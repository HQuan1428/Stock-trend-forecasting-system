## 1. Module src/sufficiency_evaluator.py

- [x] 1.1 Tạo file `src/sufficiency_evaluator.py` với docstring mô tả mục đích (B1: Sufficiency + Counterfactual Perturbation)
- [x] 1.2 Implement hàm `_only_cited_evidence(evidence, cited_ids)` — lọc chỉ giữ lại items có `news_id in cited_ids`
- [x] 1.3 Implement hàm `_perturb_to_neutral(evidence, cited_ids)` — thay mỗi cited item bằng neutral placeholder (`expected_direction=HOLD`, `support_score=0.5`, `evidence_text=""`, `polarity="neutral"`); giữ nguyên uncited items
- [x] 1.4 Implement `_compute_sufficiency_score(sufficiency_confidence, original_confidence)` — trả về `min(s/o, 1.0)` nếu `o > 0`, else `0.0`
- [x] 1.5 Implement class `SufficiencyEvaluator` với method `evaluate(original_input, original_result, cited_evidence_ids)`:
  - Tách cited evidence: `cited_only = _only_cited_evidence(evidence, cited_ids)`
  - Gọi `predict({..., "evidence": cited_only})` → lấy `sufficiency_confidence`, `prediction_on_only_cited`
  - Tính `sufficiency_score`
  - Perturb: `perturbed = _perturb_to_neutral(evidence, cited_ids)`
  - Gọi `predict({..., "evidence": perturbed})` → lấy `counterfactual_confidence`
  - Tính `counterfactual_delta = original_confidence - counterfactual_confidence`
  - Trả về dict đủ 5 fields theo spec

## 2. Pipeline — tích hợp SufficiencyEvaluator

- [x] 2.1 Trong `src/pipeline.py`, import `SufficiencyEvaluator` từ `src.sufficiency_evaluator`
- [x] 2.2 Thêm `SUFFICIENCY_COLUMNS` tuple vào `src/pipeline.py`:
  `("sample_id", "ticker", "forecast_time", "prediction", "original_confidence", "sufficiency_confidence", "sufficiency_score", "prediction_on_only_cited", "counterfactual_confidence", "counterfactual_delta")`
- [x] 2.3 Trong `_run_group()`, sau bước Faithfulness Evaluator, thêm bước Sufficiency:
  - Khởi tạo `SufficiencyEvaluator()` và gọi `evaluate(request, forecast, cited_ids)`
  - Build `sufficiency_row` dict với 10 fields từ `SUFFICIENCY_COLUMNS`
  - Return `sufficiency_row` trong dict kết quả của `_run_group()`
- [x] 2.4 Trong `run_pipeline()`, thu thập `sufficiency_rows` và ghi `sufficiency_results.csv` bằng `_write_csv(sufficiency_rows, SUFFICIENCY_COLUMNS, suff_path)`
- [x] 2.5 Thêm `sufficiency_results_csv` vào summary dict trả về của `run_pipeline()`

## 3. Dashboard Data Loader

- [x] 3.1 Trong `src/dashboard/data_loader.py`, thêm `SUFFICIENCY_COLUMNS` tuple
- [x] 3.2 Thêm field `sufficiency: Optional[pd.DataFrame] = None` vào `DashboardData` dataclass
- [x] 3.3 Trong `load_dashboard_data()`, đọc `sufficiency_results.csv` tương tự các CSV khác — missing → `None`, empty → empty DataFrame; không crash nếu file chưa tồn tại

## 4. Dashboard UI

- [x] 4.1 Trong `src/dashboard/components.py`, thêm hàm `render_sufficiency_tab(sufficiency_df)`:
  - Nếu `sufficiency_df` là `None` hoặc rỗng: hiện `st.info("Sufficiency results not available.")`
  - Hiện 2 metric card: avg `sufficiency_score` (format `:.0%`) và avg `counterfactual_delta` (format `:.2f`)
  - Hiện bảng `sufficiency_df` với các cột chính
- [x] 4.2 Trong `src/dashboard/app.py`, thêm tab "Sufficiency" vào list tabs và gọi `render_sufficiency_tab(data.sufficiency)`
- [x] 4.3 Export `render_sufficiency_tab` trong `__all__` của `components.py`

## 5. Tests

- [x] 5.1 Tạo `tests/test_sufficiency_evaluator.py`:
  - Test `sufficiency_score` nằm trong [0.0, 1.0]
  - Test `prediction_on_only_cited` là một trong `UP`/`DOWN`/`HOLD`
  - Test `counterfactual_delta` là signed float
  - Test khi `cited_evidence_ids` rỗng: `sufficiency_confidence=0.5`, `sufficiency_score=0.0`
  - Test khi toàn bộ evidence là cited: `sufficiency_score` ≈ 1.0
- [x] 5.2 Trong `tests/test_pipeline.py`, thêm test: pipeline tạo `sufficiency_results.csv` với 10 cột đúng
- [x] 5.3 Trong `tests/test_pipeline.py`, thêm test: số dòng trong `sufficiency_results.csv` bằng số nhóm (ticker, forecast_time)

## 6. Verification

- [x] 6.1 Chạy `python3.14 -m src.pipeline --input data/sample_dataset.csv --output-dir outputs` — không lỗi, `sufficiency_results.csv` xuất hiện
- [x] 6.2 Kiểm tra `outputs/sufficiency_results.csv` có đủ 10 cột và `sufficiency_score` trong [0,1]
- [x] 6.3 Chạy `pytest tests/ -v` — toàn bộ 497 tests pass
