# User Guide — Pipeline Faithful Evidence-Centric Forecasting

Tài liệu này mô tả chi tiết từng phase triển khai của pipeline: input, xử lý, và output của mỗi giai đoạn. Orchestrator duy nhất là `src/pipeline.py::run_pipeline()`, hàm `_run_group()` chạy tuần tự các phase dưới đây cho **mỗi nhóm** `(ticker, forecast_time)`.

Không có ML/LLM/API trong bất kỳ phase nào — toàn bộ là rule-based, deterministic, không có file config riêng (YAML/JSON), tham số là hằng số Python hard-code ở đầu mỗi module.

## Sơ đồ tổng quan

```
data/sample_dataset.csv
    │  group by (ticker, forecast_time)
    ▼
Phase 1: Temporal Retriever          (retriever.py)
    ▼
Phase 2: Evidence Extractor          (evidence_extractor.py)
    ▼
Phase 3: Forecast Model              (forecast_model.py)
    ▼
Phase 4: Evidence Selector           (evidence_selector.py)
    ▼
Phase 4b: Counterevidence Coverage — B2   (evidence_selector.py::compute_coverage)
    ▼
Phase 5: Faithfulness Evaluator      (faithfulness_evaluator.py)
    ▼
Phase 6: Ghép output rows            (pipeline.py, không phải module riêng)
    ▼
Phase 6b: Sufficiency Evaluator — B1  (sufficiency_evaluator.py)
    ▼
Phase 6c: Market Analyzer — B3        (market_analyzer.py)
    ▼
outputs/*.csv (6 file)
```

---

## Phase 1 — Temporal Retriever

**Module**: `retriever.py::retrieve_valid_news`

- **Input**: `forecast_time` (str ISO 8601) + list tin thô của nhóm (`news_id`, `news_time`, `news_text`, `ticker`)
- **Xử lý**: parse timestamp về UTC (naive → coi là UTC), so sánh từng `news_time` với `forecast_time`
- **Output**: `valid_news` (news_time ≤ forecast_time), `invalid_future_news` (news_time > forecast_time), `valid_count`, `invalid_future_count`, `temporal_validity` (tỷ lệ valid/total)

---

## Phase 2 — Evidence Extractor

**Module**: `evidence_extractor.py::extract_evidence_batch`

- **Input**: chỉ `valid_news` từ Phase 1 (news_id, ticker, forecast_time, news_time, news_text)
- **Xử lý**: quét `news_text` theo `POSITIVE_KEYWORDS`/`NEGATIVE_KEYWORDS` (matching 2 tầng: exact substring rồi token-gap ≤15 ký tự cho cụm từ), resolve overlap (giữ match dài nhất), gán `polarity` → `expected_direction` (positive→UP, negative→DOWN, không match→neutral/HOLD)
- **Output**: list evidence item mỗi cái có `evidence_id`, `evidence_text`, `polarity`, `expected_direction`, `support_score` (1.0 directional / 0.5 neutral); không tin nào có match → sinh đúng 1 evidence "neutral" mặc định

---

## Phase 3 — Forecast Model

**Module**: `forecast_model.py::predict`

- **Input**: request gồm `sample_id`, `ticker`, `forecast_time`, `label` (ground truth, chỉ echo không dùng để tính), toàn bộ evidence từ Phase 2
- **Xử lý**: dedup evidence_id, lọc lại temporal (defense-in-depth), vote — `expected_direction=UP` → +1, `DOWN` → -1, `HOLD` → 0 → `score = positive_count - negative_count`; `prediction` = UP/DOWN/HOLD theo dấu score; `confidence = 0.5 + min(|score|*0.1, 0.45)`
- **Output**: `prediction`, `confidence`, `score`, `pro_evidence`/`counter_evidence`/`up_evidence`/`down_evidence`/`neutral_evidence`, `rationale` (template string), `warnings`

---

## Phase 4 — Evidence Selector

**Module**: `evidence_selector.py::select_evidence_batch`

- **Input**: `prediction` + `confidence` từ Phase 3, toàn bộ evidence (kèm `polarity`, `expected_direction`, `support_score` đổi tên thành `extractor_score`)
- **Xử lý**: tra `CLASSIFICATION_TABLE[(prediction, expected_direction)]` → nhãn `pro`/`counter`/`neutral`; sort theo `selector_score` giảm dần, cắt top_k=3 mỗi nhóm
- **Output**: `pro_evidence`, `counterevidence`, `neutral_evidence` (đã top_k), `summary` (đếm trước khi cắt), `invalid_future_evidence` (smoke-check phụ)

### Phase 4b — Counterevidence Coverage (B2)

**Module**: `evidence_selector.py::compute_coverage`

- **Input**: kết quả Phase 4 + `expected_labels` (suy ra lại từ `CLASSIFICATION_TABLE` cho mọi candidate, không đọc ground-truth label)
- **Xử lý**: đếm bao nhiêu counterevidence "đáng lẽ phải có" (`expected_labels == counter`) thực sự xuất hiện trong `result["counterevidence"]`
- **Output**: `counterevidence_coverage` (detected/available), `counterevidence_detected_rate`

---

## Phase 5 — Faithfulness Evaluator

**Module**: `faithfulness_evaluator.py::FaithfulnessEvaluator.evaluate`

- **Input**: request gốc (Phase 3 input) + `forecast` (Phase 3 output, đã có `pro_evidence`/`counter_evidence`)
- **Xử lý**: ablation — loại bỏ evidence đã cited (`pro_evidence`) rồi gọi lại `predict_without_evidence()` để có prediction/confidence "sau khi bỏ bằng chứng"; tính `confidence_drop = original_confidence - confidence_after_removal`
- **Output**: `temporal_validity`, `evidence_support`, `confidence_drop`, `confidence_after_removal`, `verdict` nội bộ (không dùng để gán label cuối — xem Phase 6)

---

## Phase 6 — Ghép dòng output

Nằm trong `pipeline.py`, không phải module riêng.

- **Xử lý**: `_faithfulness_label(confidence_drop, temporal_validity)` → HIGH (drop≥0.20) / MEDIUM (drop≥0.05) / LOW; ghép `prediction_row`, `evidence_rows`, `faithfulness_row` (kèm `counterevidence_coverage` từ Phase 4b), `leakage_rows` (từ `invalid_future_news` của Phase 1, kèm tính `leakage_minutes`)

---

## Phase 6b — Sufficiency Evaluator (B1)

**Module**: `sufficiency_evaluator.py::SufficiencyEvaluator.evaluate`

- **Input**: request gốc + `forecast` (Phase 3) + `cited_ids` (news_id trong pro+counter của Phase 4)
- **Xử lý**:
  - **Sufficiency**: chạy lại `predict()` chỉ với evidence đã cited → `sufficiency_score = min(conf_cited_only/original_conf, 1.0)`
  - **Counterfactual**: thay từng evidence cited bằng placeholder neutral (`expected_direction=HOLD`) rồi chạy lại `predict()` → `counterfactual_delta = original_conf - conf_perturbed`
- **Output**: `sufficiency_confidence`, `sufficiency_score`, `prediction_on_only_cited`, `counterfactual_confidence`, `counterfactual_delta`

---

## Phase 6c — Market Analyzer (B3)

**Module**: `market_analyzer.py::MarketAnalyzer.analyze`

- **Input**: `prediction` (Phase 3) + `next_day_return`, `price_5d_return` (đọc trực tiếp từ dòng đầu CSV input; mặc định `0.0` nếu thiếu cột)
- **Xử lý**: so khớp `prediction` với dấu của `next_day_return` (ngưỡng ±0.005) → `market_consistent`; phân loại `price_5d_return` thành bull (>0.02) / bear (<-0.02) / sideways
- **Output**: `market_consistent`, `market_consistency_score`, `regime`

---

## Tổng hợp I/O toàn pipeline

| Phase | Input chính | Output chính | Ghi vào CSV |
|---|---|---|---|
| 1. Retriever | forecast_time, tin thô | valid/invalid_future_news | `temporal_leakage_results.csv` |
| 2. Extractor | valid_news | evidence list (polarity, direction) | (feed Phase 3/4) |
| 3. Forecast Model | evidence list | prediction, confidence, score | `prediction_results.csv` |
| 4. Selector | prediction + evidence | pro/counter/neutral evidence | `evidence_results.csv` |
| 4b. Coverage (B2) | selector result | counterevidence_coverage | → gộp vào `faithfulness_results.csv` |
| 5. Faithfulness | request + forecast | temporal_validity, evidence_support, confidence_drop | `faithfulness_results.csv` |
| 6b. Sufficiency (B1) | request + forecast + cited_ids | sufficiency_score, counterfactual_delta | `sufficiency_results.csv` |
| 6c. Market (B3) | prediction + return data | market_consistent, regime | `market_consistency_results.csv` |

Dữ liệu chảy **một chiều tuyến tính** qua các phase, không có vòng lặp — mỗi phase chỉ đọc output của phase trước (hoặc request gốc), không phase nào ghi ngược lại dữ liệu của phase trước đó.

## Ghi chú riêng — B4 (Agentic SDLC trace)

`src/agent_trace.py` **không** nằm trong `run_pipeline()`. Module này đọc trace log riêng (ghi lại quá trình dùng AI-agent trong lúc làm đồ án) và chỉ được `src/dashboard/components.py::render_agentic_sdlc_tab` đọc trực tiếp để hiển thị trên dashboard, tách biệt hoàn toàn khỏi luồng dự báo 8 phase ở trên.

## Chạy pipeline

```bash
python -m src.pipeline --input data/sample_dataset.csv --output-dir outputs
```

Xem toàn bộ cấu hình bắt đầu từ `src/pipeline.py::run_pipeline()` (dòng ~489) và `_run_group()` (dòng ~122) — đây là bản đồ duy nhất nối tất cả các phase lại với nhau.
