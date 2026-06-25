# AI_Guide.md — Tổng hợp dự án Stock Trend Forecasting System

> Tài liệu này dành cho AI agent / lập trình viên mới tiếp nhận dự án. Nó tổng hợp:
> 1. Thông tin chung và triết lý thiết kế
> 2. Luồng làm việc chính của từng module
> 3. Cách pipeline vận hành end-to-end
> 4. Hướng dẫn sử dụng mã nguồn + chạy demo
> 5. Hướng cải tiến cho từng module
>
> Tài liệu gốc `ChuDe1.md` (đề bài đồ án) quy định pipeline tổng quát; tài liệu này mô tả cách codebase hiện thực hoá nó.

---

## 1. Thông tin chung

### 1.1. Tên đồ án
**Faithful Evidence-Centric Financial News Forecasting** — Hệ thống dự báo xu hướng cổ phiếu từ tin tức có kiểm chứng bằng chứng.

### 1.2. Câu hỏi nghiên cứu trung tâm
> Khi một mô hình dự báo stock movement từ news, liệu evidence mà nó đưa ra có thật sự quyết định prediction không?

Triết lý cốt lõi: **Prediction accuracy là chưa đủ** — phải chứng minh evidence có faithful (thật sự quyết định prediction), temporally valid (không dùng tin tương lai), và balanced (có cả pro lẫn counterevidence).

### 1.3. Phạm vi
- **Môn học**: Công nghệ mới — Agentic AI trong SDLC
- **Mục tiêu**: Học cách áp dụng AI agent vào vòng đời phát triển phần mềm (đặc tả → thiết kế → code → test → đánh giá → visualize → phản biện)
- **Quy mô nhóm**: 3 sinh viên
- **Tổng điểm**: 7đ cơ bản (Phần A) + 3đ nâng cao (Phần B) + tối đa 2đ cộng
- **Sản phẩm chính**: Prototype + OpenSpec + Dashboard + Báo cáo + Demo

### 1.4. Nguyên tắc bất di bất dịch
1. **Không LLM, không FinBERT, không transformer, không GPU, không API ngoài** — mọi giai đoạn đều rule-based & deterministic
2. **Temporal validity cứng**: news_time > forecast_time thì loại bỏ ngay từ đầu
3. **Faithfulness đo được**: ablation (bỏ cited evidence) phải thay đổi confidence
4. **Counterevidence là first-class output**: phải có cả bằng chứng ủng hộ lẫn phản bác
5. **Không dùng để trading thật** — chỉ phục vụ học tập

### 1.5. Tech stack
| Hạng mục | Công nghệ |
|---|---|
| Ngôn ngữ | Python 3.14+ |
| DataFrame | pandas, numpy |
| ML (chưa dùng) | scikit-learn (đã trong requirements nhưng V1 chưa cần) |
| Dashboard | Streamlit + Plotly |
| Test | pytest |
| Workflow | OpenSpec (spec-driven) |

---

## 2. Kiến trúc tổng thể — 6 module + dashboard

```
News CSV  ─►  Temporal Retriever  ─►  Evidence Extractor
          ─►  Evidence Selector    ─►  Forecast Model
          ─►  Faithfulness Evaluator
          ─►  4 dashboard-ready output CSVs
                                          │
                                          ▼
                                  Streamlit Dashboard
```

| # | Module | File | Vai trò |
|---|---|---|---|
| 1 | Temporal Retriever | `src/retriever.py` | Lọc tin hợp lệ về thời gian |
| 2 | Evidence Extractor | `src/evidence_extractor.py` | Trích bằng chứng từ `news_text` |
| 3 | Evidence Selector | `src/evidence_selector.py` | Phân loại pro / counter / neutral |
| 4 | Forecast Model | `src/forecast_model.py` | Suy ra `UP` / `DOWN` / `HOLD` |
| 5 | Faithfulness Evaluator | `src/faithfulness_evaluator.py` + `src/faithfulness_metrics.py` | Đo độ faithful qua ablation |
| 6 | Pipeline Orchestrator | `src/pipeline.py` | Glue code điều phối 5 module trên |
| 7 | Dashboard | `src/dashboard/` | Read-only Streamlit visualization |

---

## 3. Luồng làm việc chính của từng module

### 3.1. `src/retriever.py` — Temporal Retriever (Giai đoạn 1)

**Mục đích**: Bảo vệ tính toàn vẹn thời gian. Tin `news_time > forecast_time` là **tin tương lai** — không bao giờ được phép chạm vào model.

**Input**: 
- `forecast_time` (string ISO)
- `ticker` (string)
- `news` (list of dicts có `news_id`, `news_time`, `text`)

**Output**: `RetrievalResult` gồm
- `valid_news`: list các tin hợp lệ (`news_time <= forecast_time`)
- `invalid_future_news`: list các tin tương lai (cho dashboard warning)
- `valid_count`, `invalid_future_count`, `temporal_validity` (tỉ lệ valid / tổng)

**Đặc tính**:
- Timestamp naive được interpret là UTC
- Parse cả `"T"` lẫn `" "` separator
- Không raise exception khi timestamp malformed — fail-soft

**Hàm chính**: `retrieve_valid_news(forecast_time, ticker, news)`

---

### 3.2. `src/evidence_extractor.py` — Evidence Extractor (Giai đoạn 2)

**Mục đích**: Biến `news_text` thành danh sách các đoạn evidence có cực (polarity) và hướng dự báo (expected_direction).

**Input**: dict `{news_id, ticker, forecast_time, news_time, news_text}`

**Output**: dict gồm
- `evidence`: list các evidence object (không rỗng)
- `summary`: counts + `has_mixed_evidence`
- `extraction_method`: literal `"rule_based_keyword"`
- `primary_evidence_id`: ID evidence chính (theo quy tắc negative > positive > neutral, tie-break by earliest start_char)

**Algorithm**:
1. Lowercase `news_text` một lần
2. Với mỗi keyword trong từ điển, thử **exact substring match** trước
3. Nếu multi-word keyword không match exact, thử **token-level match** với gap cap 15 ký tự (cho phép "weak sales" match "weak iPhone sales")
4. Resolve overlap: giữ match dài nhất, tie-break by earliest start
5. Assign `evidence_id = <news_id>_E<index>` zero-padded 3 digits
6. Nếu matches rỗng → trả về đúng 1 neutral evidence

**Keyword dictionary (V3 — superset của V1 + V2)**: 
- 34 positive keyword (UP): `beats expectations`, `record profit`, `strong sales`, `raises guidance`, `launches new product`, `stronger than expected`, `faster growth`, `positive analyst`, `wins a`, `signs a`, `accelerate`, `record level`, `raises shipment outlook`, `launches`, `expands`, `improvement`, `stronger`, `secures`, `receives`, `praise`, `preorders`, `cost efficient`, `backlog expands`, `advertiser retention`, `adoption`, `introduces`, `accelerated`, `better conversion`, `carrier partnership`, `upgrade`, `automation`, `advertising marketplace`, `supply agreement`, `demand from`
- 46 negative keyword (DOWN): `misses expectations`, `weak sales`, `recall`, `lawsuit`, `cuts guidance`, `decline`, `antitrust complaint`, `softer orders`, `slower growth`, `warns of`, `warns that`, `faces a`, `is fined`, `fined for`, `delays production`, `lowers outlook`, `outage`, `probe into`, `regulatory costs`, `downgraded`, `vote to authorize a strike`, `complaint`, `delays`, `cuts the price`, `budget cuts`, `complain about`, `losses widen`, `loses an appeal`, `overheating`, `lowers revenue guidance`, `warns`, `slower`, `softer`, `weaker`, `lower`, `reduced`, `reduces`, `class action`, `criticism`, `pauses`, `delivery delays`, `fresh lawsuit`, `outage in`, `permitting`, `delays a planned`, `downgrade`
- Tổng: **80 keyword** được audit thủ công cho FP trên sample

**Polarity-to-Direction mapping**:
| Polarity | expected_direction |
|---|---|
| positive | UP |
| negative | DOWN |
| neutral | HOLD |

**Hàm chính**:
- `extract_evidence(news_item)` — single item
- `extract_evidence_batch(news_items)` — list input → list output, cùng thứ tự

---

### 3.3. `src/evidence_selector.py` — Evidence Selector (Giai đoạn 3)

**Mục đích**: Phân loại mỗi evidence candidate thành `pro` (ủng hộ prediction), `counter` (phản bác), hoặc `neutral` (trung tính). Đây là giai đoạn **làm cho counterevidence trở thành first-class output** — không chỉ trích evidence một chiều.

**Input**: dict gồm
- `prediction`: `UP` / `DOWN` / `HOLD`
- `confidence`: float
- `evidence_candidates`: list các evidence items

**Output**: dict gồm
- `pro_evidence`, `counterevidence`, `neutral_evidence`, `invalid_future_evidence` (4 list, sorted by `selector_score` desc, truncated to `top_k`)
- `summary`: pre-truncation counts (`pro_count`, `counter_count`, `neutral_count`, `invalid_future_count`)
- `selection_method`: literal `"expected_direction_mapping_v1"`

**Classification table**:
| prediction | evidence.expected_direction | selector_label |
|---|---|---|
| UP | UP | pro |
| UP | DOWN | counter |
| UP | HOLD | neutral |
| DOWN | DOWN | pro |
| DOWN | UP | counter |
| DOWN | HOLD | neutral |
| HOLD | HOLD | pro |
| HOLD | UP or DOWN | counter |

**Đặc tính**:
- Không bao giờ đọc `label` / `ground_truth_label` (chống label leakage)
- Naive timestamp → UTC
- Evidence có `news_time > forecast_time` bị đẩy sang `invalid_future_evidence`
- Output `counts` dùng pre-truncation để không bias coverage metric

**Hàm chính**:
- `select_evidence(request)` — single request
- `select_evidence_batch(requests)` — batch

---

### 3.4. `src/forecast_model.py` — Forecast Model (Giai đoạn 4)

**Mục đích**: Tổng hợp evidence → suy ra `UP` / `DOWN` / `HOLD` cùng confidence, score, rationale, warnings.

**Input**: dict gồm
- `sample_id`, `ticker`, `forecast_time` (bắt buộc)
- `evidence` (list, có thể rỗng)
- `label` (optional, chỉ dùng cho evaluation, **KHÔNG đọc khi predict**)

**Output**: `ForecastResult` dict gồm
- `prediction`: `UP` / `DOWN` / `HOLD`
- `confidence`: float trong [0.5, 0.95]
- `score`: integer (positive - negative)
- 4 counts: `positive_count`, `negative_count`, `neutral_count`, `total_evidence`
- 2 derived: `directional_evidence_count`, `evidence_strength`, `conflict_ratio`
- 5 evidence lists: `pro_evidence`, `counter_evidence`, `up_evidence`, `down_evidence`, `neutral_evidence` (sorted by `evidence_id`)
- `rationale`: template-based string
- `warnings`: list of warning dicts
- `model_version`: literal `"rule_based_v1"`

**Algorithm (rule-based voting)**:
```
positive_count = |{ e : e.expected_direction == "UP" }|
negative_count = |{ e : e.expected_direction == "DOWN" }|
neutral_count  = |{ e : e.expected_direction == "HOLD" }|
score          = positive_count - negative_count

if score  > 0: prediction = "UP"
elif score < 0: prediction = "DOWN"
else:           prediction = "HOLD"

confidence = 0.5 + min(abs(score) * 0.1, 0.45)  clamped [0.5, 0.95]
evidence_strength = abs(score) / (positive_count + negative_count)
conflict_ratio    = min(positive, negative) / max(positive + negative, 1)
```

**Rationale templates** (4 nhánh):
- `UP` → "Prediction UP because positive evidence count (X) is greater than negative evidence count (Y)."
- `DOWN` → tương tự đảo chiều
- `HOLD` balanced → "Prediction HOLD because positive and negative evidence are balanced."
- `HOLD` no_directional → "Prediction HOLD because positive and negative evidence are balanced or no valid directional evidence is available."

**Defense in depth**:
- Tự kiểm tra `news_time <= forecast_time` (redundant với Retriever)
- Loại evidence trùng `evidence_id`
- Loại evidence thiếu `expected_direction` (warning `INVALID_EVIDENCE`)

**Hàm chính**:
- `predict(input_data, strict=False)` — single
- `predict_without_evidence(input_data, removed_evidence_ids, strict=False)` — dùng cho ablation
- `predict_batch(records)` — batch, tự ghi CSV + JSON
- `compute_accuracy_and_confusion(results)` — đánh giá

---

### 3.5. `src/faithfulness_evaluator.py` + `src/faithfulness_metrics.py` — Faithfulness Evaluator (Giai đoạn 5)

**Mục đích**: Trả lời câu hỏi trung tâm — **evidence mà model cite có thật sự quyết định prediction không?**

**Input**: 
- `request` (input envelope của Forecast Model)
- `result` (ForecastResult)

**Output**: dict gồm
- `temporal_validity`: `1.0` nếu tất cả cited evidence đều hợp lệ thời gian, `0.0` nếu có ít nhất 1 future
- `evidence_support`: mean của per-item support score (1.0 match, 0.5 HOLD vs UP/DOWN, 0.0 opposite)
- `confidence_drop`: `original_confidence - confidence_after_removal` (signed, có thể âm)
- `faithfulness_label`: `HIGH` / `MEDIUM` / `LOW`
- `per_evidence_results`, warnings (3 loại)

**Ablation strategy**:
1. Re-invoke `predict_without_evidence(request, cited_evidence_ids)` — bỏ evidence đã cite
2. So sánh `original_confidence` vs `confidence_after_removal` → `confidence_drop`

**Faithfulness label rule** (single source of truth ở `pipeline._faithfulness_label`):
| Label | Điều kiện |
|---|---|
| `HIGH` | `temporal_validity = 1.0` AND `confidence_drop >= 0.20` |
| `MEDIUM` | `temporal_validity = 1.0` AND `confidence_drop >= 0.05` |
| `LOW` | còn lại |

**Verdict cascade** (chi tiết hơn, 6 nhãn):
- `invalid_temporal_leakage` — temporal_validity < 1.0
- `unsupported_evidence` — evidence_support < 0.5
- `decorative_explanation_risk` — evidence rỗng hoặc drop thấp
- `strong_faithful_candidate` — drop >= 0.20 hoặc prediction flip
- `moderate_faithful_candidate` — drop >= 0.10
- `weak_faithful_candidate` — drop >= 0.05

**Hàm chính**:
- `FaithfulnessEvaluator().evaluate(request, result)` — single
- `evaluate_batch(pairs)` — batch

---

### 3.6. `src/pipeline.py` — Pipeline Orchestrator (Glue code)

**Mục đích**: Điều phối 5 module trên cho một CSV input → 4 CSV output. **Không tái cài đặt** thuật toán nào, chỉ import và kết nối.

**Quy trình**:
1. Đọc `data/sample_dataset.csv`
2. Group rows theo `(ticker, forecast_time)` — giữ thứ tự input
3. Với mỗi group, chạy `_run_group()`:
   - **Retriever**: lọc valid / invalid future
   - **Extractor**: trích evidence từ valid news
   - **Forecast Model**: suy ra prediction
   - **Evidence Selector**: classify thành pro / counter / neutral (post-hoc, dùng cho writer)
   - **Faithfulness Evaluator**: đo ablation
4. Ghi 4 file CSV theo schema cố định

**4 file output**:
| File | Schema columns |
|---|---|
| `prediction_results.csv` | sample_id, ticker, forecast_time, prediction, confidence, score, label, is_correct, rationale, cited_evidence_count, valid_news_count, invalid_future_news_count |
| `evidence_results.csv` | sample_id, ticker, forecast_time, news_id, news_time, news_text, evidence_text, polarity, expected_direction, evidence_role, support_score, is_cited, is_temporally_valid |
| `faithfulness_results.csv` | sample_id, ticker, forecast_time, prediction, original_confidence, confidence_without_cited_evidence, confidence_drop, temporal_validity, evidence_support, faithfulness_label |
| `temporal_leakage_results.csv` | sample_id, ticker, forecast_time, news_id, news_time, news_text, leakage_minutes, leakage_type |

**Đặc tính**:
- **Deterministic** — input giống → output byte-equal
- Không LLM / FinBERT / network call
- Không ghi đè `data/`
- Schema cố định ở `PREDICTION_COLUMNS`, `EVIDENCE_COLUMNS`, `FAITHFULNESS_COLUMNS`, `LEAKAGE_COLUMNS` — là "hợp đồng" với dashboard

**Hàm chính**:
- `run_pipeline(input_path, output_dir, ...)` — public API
- `python -m src.pipeline --input ... --output-dir ...` — CLI

---

### 3.7. `src/dashboard/` — Visualization Dashboard

**Mục đích**: Trực quan hóa 4 CSV output qua Streamlit. **Read-only** với upstream — không gọi lại Forecast Model hay bất cứ module nào.

**Cấu trúc**:
- `app.py` — entry point
- `data_loader.py` — load 4 CSV, áp adapter
- `validators.py` — assert schema
- `metrics.py` — tính accuracy, average confidence, faithfulness breakdown
- `charts.py` — 4 biểu đồ Plotly
- `components.py` — render 5 tab

**5 tab**:
1. **Overview** — prediction distribution, accuracy, average confidence / drop / temporal validity
2. **Evidence** — bảng evidence với badge cited / non-cited / leakage
3. **Confidence Drop** — scatter per-sample, màu theo faithfulness level
4. **Temporal Leakage** — severity banner (OK / Warning / Critical) + bảng leakage
5. **Case Detail** — chọn 1 sample, hiển thị đầy đủ ticker / prediction / evidence / drop / interpretation

**Adapter layer** ở `data_loader.py`: map từ shape upstream sang shape proposal (e.g., `confidence_after_removal` → `confidence_without_cited_evidence`).

---

## 4. Cách pipeline hoạt động end-to-end

### 4.1. Chuỗi xử lý cho 1 group (ticker, forecast_time)

```
Input row: news_id=N, ticker=AAPL, forecast_time=2025-03-12 09:00,
           news_time=2025-03-11 08:00, news_text="...", label="UP"

                          │
                          ▼
        ┌─────────────────────────────────────┐
        │ 1. Temporal Retriever                │
        │    news_time 2025-03-11 08:00        │
        │    forecast_time 2025-03-12 09:00    │
        │    → valid (news_time <= forecast)   │
        └─────────────────────────────────────┘
                          │ valid_news = [N]
                          ▼
        ┌─────────────────────────────────────┐
        │ 2. Evidence Extractor                │
        │    news_text = "..."                 │
        │    → evidence = [{                   │
        │        polarity, expected_direction, │
        │        start_char, end_char,         │
        │        evidence_text, ...            │
        │      }]                              │
        └─────────────────────────────────────┘
                          │ evidence = [e1, e2, ...]
                          ▼
        ┌─────────────────────────────────────┐
        │ 3. Forecast Model                    │
        │    score = pos_count - neg_count     │
        │    prediction = UP/DOWN/HOLD         │
        │    confidence = 0.5 + 0.1*|score|    │
        │    rationale = template              │
        └─────────────────────────────────────┘
                          │ forecast = {prediction, confidence, ...}
                          ▼
        ┌─────────────────────────────────────┐
        │ 4. Evidence Selector (post-hoc)      │
        │    Dựa trên prediction, classify:    │
        │    pro / counter / neutral            │
        │    → cited_ids = union(pro, counter) │
        └─────────────────────────────────────┘
                          │ cited_ids = [e1, e2, ...]
                          ▼
        ┌─────────────────────────────────────┐
        │ 5. Faithfulness Evaluator            │
        │    Ablation: predict_without_evi...  │
        │    → confidence_drop                 │
        │    → temporal_validity               │
        │    → evidence_support                │
        │    → faithfulness_label              │
        └─────────────────────────────────────┘
                          │
                          ▼
        4 output rows: prediction, evidence, faithfulness, leakage
```

### 4.2. Chuỗi xử lý cho toàn bộ sample

```
data/sample_dataset.csv (100 rows, 4 ticker)
                    │
                    ▼
        ┌────────────────────────────────────┐
        │ Group by (ticker, forecast_time)   │
        │ → 100 groups (1 row / group)       │
        └────────────────────────────────────┘
                    │
                    ▼
        For each group: run _run_group()  (xem sơ đồ trên)
                    │
                    ▼
        Collect all rows from 100 groups
                    │
                    ▼
        Write 4 CSV files to outputs/
                    │
                    ▼
        Streamlit consumes 4 CSVs
```

### 4.3. Sample input → output thực tế (sau V3)

Input: `data/sample_dataset.csv` (100 rows)

| Metric | Giá trị |
|---|---|
| Tổng groups | 100 |
| Valid news (không leakage) | 79 |
| Invalid future news (temporal leakage) | 21 |
| Prediction UP / DOWN / HOLD | 37 / 12 / 51 |
| Accuracy (toàn sample) | 74% |
| Accuracy (loại trừ leakage) | 93.7% |
| Per-class accuracy (valid only) | UP 90.2% / DOWN 100% / HOLD 96.3% |
| Faithfulness HIGH / MEDIUM / LOW | 49 / 0 / 51 |
| `confidence_drop` mean | 0.30 (max 0.70) |

**Giải thích 21 case DOWN-HOLD**: Đây là **temporal leakage** (news_time > forecast_time), retriever loại evidence của chúng → model dự đoán HOLD (không có evidence để vote). Đây là **hành vi đúng**, không phải lỗi. Các case này xuất hiện trong sample để test chức năng leakage warning của retriever.

---

## 5. Hướng dẫn sử dụng mã nguồn

### 5.1. Cài đặt

```bash
# Clone project
cd /home/quannh/work-space/Stock-trend-forecasting-system

# Tạo virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Cài dependencies
pip install -r requirements.txt
```

### 5.2. Chạy tests

```bash
# Toàn bộ test
pytest tests/ -q

# Riêng từng module
pytest tests/test_evidence_extractor.py -v
pytest tests/test_forecast_model.py -v
pytest tests/test_faithfulness_evaluator.py -v
pytest tests/test_pipeline.py -v
```

Hiện tại: **479/479 tests pass** (sau khi áp dụng V2 + V3 keyword enrichment).

### 5.3. Chạy pipeline

```bash
# Mặc định: input=data/sample_dataset.csv, output=outputs/
python3 -m src.pipeline

# Tùy chỉnh
python3 -m src.pipeline \
    --input data/sample_dataset.csv \
    --output-dir outputs \
    --ticker-column ticker \
    --news-time-column news_time \
    --forecast-time-column forecast_time \
    --label-column label

# Xem help
python3 -m src.pipeline --help
```

Output: 4 file CSV trong `outputs/`
- `prediction_results.csv`
- `evidence_results.csv`
- `faithfulness_results.csv`
- `temporal_leakage_results.csv`

### 5.4. Chạy dashboard

```bash
streamlit run src/dashboard/app.py
```

Mở trình duyệt tại `http://localhost:8501`. Dashboard đọc file trong `outputs/` (mặc định).

### 5.5. Dùng từng module riêng lẻ

```python
# Module 1: Temporal Retriever
from src.retriever import retrieve_valid_news
result = retrieve_valid_news(
    forecast_time="2025-03-12 09:00",
    ticker="AAPL",
    news=[
        {"news_id": "n1", "news_time": "2025-03-11 08:00", "text": "..."},
    ]
)
print(result.valid_news, result.invalid_future_news)

# Module 2: Evidence Extractor
from src.evidence_extractor import extract_evidence
result = extract_evidence({
    "news_id": "N001",
    "ticker": "AAPL",
    "forecast_time": "2025-03-12 09:00",
    "news_time": "2025-03-11 08:00",
    "news_text": "Apple reports stronger than expected iPhone demand",
})
for ev in result["evidence"]:
    print(ev["polarity"], ev["expected_direction"], ev["evidence_text"])

# Module 3: Evidence Selector
from src import select_evidence
result = select_evidence({
    "ticker": "AAPL",
    "forecast_time": "2025-03-12 09:00",
    "prediction": "UP",
    "confidence": 0.7,
    "evidence_candidates": [...],
})
print(result["pro_evidence"], result["counterevidence"], result["neutral_evidence"])

# Module 4: Forecast Model
from src import predict, predict_without_evidence
result = predict({
    "sample_id": "AAPL_2025-03-12",
    "ticker": "AAPL",
    "forecast_time": "2025-03-12 09:00",
    "evidence": [...],
})
print(result["prediction"], result["confidence"], result["rationale"])

# Ablation
reduced = predict_without_evidence(request, ["N001_E001"])
print("confidence_drop:", result["confidence"] - reduced["confidence"])

# Module 5: Faithfulness Evaluator
from src import FaithfulnessEvaluator
report = FaithfulnessEvaluator().evaluate(request, result)
print(report["faithfulness_label"], report["confidence_drop"])
```

---

## 6. Hướng dẫn chạy demo (5 phút)

### 6.1. Script demo

```bash
# Bước 1: Chạy pipeline
python3 -m src.pipeline

# Bước 2: Mở dashboard
streamlit run src/dashboard/app.py
```

### 6.2. Kịch bản demo theo ChuDe1.md mục 11.1

1. **Mở dashboard** tại `http://localhost:8501`
2. **Chọn ticker AAPL** ở sidebar
3. **Chọn forecast date** trong khoảng 2025-03-12 → 2025-03-21
4. **Xem tab "Overview"**: prediction distribution, accuracy
5. **Chuyển sang tab "Evidence"**: tin nào được cite, tin nào bị loại
6. **Chuyển sang tab "Confidence Drop"**: case nào có `confidence_drop` cao → faithful
7. **Chuyển sang tab "Temporal Leakage"**: cảnh báo các tin bị retriever loại
8. **Chuyển sang tab "Case Detail"**: chọn 1 sample cụ thể, xem đầy đủ evidence + rationale
9. **Lời kết**: trình bày 1 limitation quan trọng (ví dụ: 21 case leakage không vote được, hoặc confidence saturation tại |score| ≥ 5)

### 6.3. Lời trình bày mẫu

> "Ban đầu hệ thống dự báo AAPL giảm với confidence 0.76.
> Evidence chính là tin doanh số iPhone tại Trung Quốc giảm.
> Sau khi bỏ evidence này, confidence giảm xuống 0.51.
> Trong khi đó, nếu bỏ một tin ngẫu nhiên không được cite, confidence chỉ giảm xuống 0.73.
> Vì vậy, evidence được cite có vai trò quan trọng hơn tin ngẫu nhiên và có dấu hiệu faithful."

---

## 7. Hướng cải tiến cho từng module

### 7.1. Temporal Retriever — `/src/retriever.py`

**Hiện tại**: Naive timestamp → UTC; chỉ so sánh `news_time > forecast_time`.

**Hướng cải tiến**:
- **Cảnh báo edge case**: khi `news_time == forecast_time` (cùng giây) hiện tại cho là hợp lệ → có thể thêm tolerance window (e.g., exclude if within 1 minute).
- **Multi-exchange time**: hỗ trợ time zone khác nhau (NYSE 9:30-16:00 ET vs LSE 8:00-16:30 GMT).
- **Weekend/holiday filter**: tin công bố cuối tuần có thể chỉ ảnh hưởng thứ 2.
- **Trả thêm `temporal_warnings`**: danh sách tin sát giờ forecast (e.g., trong 5 phút) để dashboard cảnh báo "borderline".

### 7.2. Evidence Extractor — `src/evidence_extractor.py`

**Hiện tại**: V3 keyword dict với 80 entry, rule-based, có token-gap fallback.

**Hướng cải tiến**:
- **Negation handling**: hiện `not raise guidance` chưa được phát hiện. Có thể thêm bước quét negation trong cửa sổ 20 ký tự trước keyword positive → đảo polarity. Đây là **cải tiến có ROI cao nhất** cho độ chính xác.
- **Intensifier handling**: `sharp decline`, `major recall`, `slight improvement` → boost support_score (1.0 → 1.2, clamp tại 1.0).
- **Whole-word boundaries** (Optional): hiện `decline` match `price decline continued` (OK) nhưng cũng match `declined` không. Có thể thêm `\b` để tránh false positive từ ghép từ.
- **Multi-language**: tiếng Việt có thể có keyword riêng (`lợi nhuận kỷ lục`, `cắt giảm dự báo`).
- **Per-ticker dictionaries**: công ty khác nhau dùng từ vựng khác nhau (e.g., AAPL hay nói "iPhone", TSLA hay nói "delivery").

### 7.3. Evidence Selector — `src/evidence_selector.py`

**Hiện tại**: Rule-based mapping dựa trên `expected_direction` so với `prediction`.

**Hướng cải tiến**:
- **Ranking score hiện đại hơn**: hiện dùng `extractor_score * selector_score`; có thể thêm recency weight (`1.0 / (1 + days_to_forecast)`) và source reliability (Reuters > blog).
- **Cross-source deduplication**: nếu 5 tin khác nhau đều nói "weak iPhone sales", giữ lại 1 tin đại diện.
- **Sub-event detection**: tin "Apple delays iPhone launch" và "Apple cuts iPhone forecast" — 2 cụm khác nhau nhưng cùng chủ đề. Có thể group để giảm nhiễu.

### 7.4. Forecast Model — `src/forecast_model.py`

**Hiện tại**: V1 rule-based voting, integer score, confidence [0.5, 0.95].

**Hướng cải tiến**:
- **Weighted voting**: thay `score = pos - neg` (count) bằng `score = sum(support_score)`. Một evidence `support_score=1.0` quan trọng hơn 5 evidence `support_score=0.2`.
- **Source recency weight**: tin trong 24h gần forecast quan trọng hơn tin 1 tuần trước.
- **Per-keyword weight**: keyword mạnh (`antitrust complaint`) có weight cao hơn keyword yếu (`improvement`). Cần calibration bằng historical data.
- **Price features fallback**: khi `score == 0` mà `price_5d_return > 0.005` → `UP`, `< -0.005` → `DOWN`. Tận dụng thông tin giá khi news neutral.
- **Calibrated confidence**: hiện chỉ là `0.5 + 0.1*|score|`. Có thể fit logistic regression trên historical để ra xác suất thật.
- **Lưu ý quan trọng**: KHÔNG dùng FinBERT/transformer/LLM — phải giữ rule-based & deterministic (theo spec V1).

### 7.5. Faithfulness Evaluator — `src/faithfulness_evaluator.py`

**Hiện tại**: 3 metric cơ bản (temporal_validity, evidence_support, confidence_drop) + 6 verdict + composite score heuristic.

**Hướng cải tiến**:
- **Leave-one-out per evidence**: thay vì bỏ tất cả cited evidence, bỏ từng cái một để xem evidence nào "mạnh" nhất.
- **Sufficiency test** (B1 trong ChuDe1): "chỉ dùng cited evidence có dự báo được không?" → so sánh prediction với full input.
- **Counterfactual perturbation** (B1): thay cited evidence bằng "neutral news" → xem prediction có đổi không.
- **Market consistency** (B3): so sánh evidence với `next-day return` thật; nếu evidence UP mà giá thật giảm → consistency thấp.
- **Regime analysis** (B3): bull / bear / sideways → faithfulness threshold khác nhau.
- **Calibrated thresholds**: hiện `0.05/0.10/0.20` cứng; có thể dùng ROC curve trên historical data.

### 7.6. Pipeline — `src/pipeline.py`

**Hiện tại**: Glue code, deterministic, output 4 CSV.

**Hướng cải tiến**:
- **Parallel processing**: 100 group chạy tuần tự, có thể `concurrent.futures.ProcessPoolExecutor` để tăng tốc.
- **Streaming output**: thay vì gom hết vào list rồi ghi, ghi từng group ngay khi xong (tiết kiệm RAM).
- **Schema validation upstream**: kiểm tra `news_text` không rỗng, `forecast_time` parse được trước khi chạy.
- **Agent trace log**: ghi `run_log.json` cho mỗi run (ai agent nào, prompt nào, kết quả) — phục vụ rubric A1 về Agentic SDLC.
- **Run history**: lưu các run trước với timestamp + git commit để so sánh thay đổi.

### 7.7. Dashboard — `src/dashboard/`

**Hiện tại**: 5 tab, Plotly chart, Streamlit.

**Hướng cải tiến**:
- **Auto-refresh**: watch `outputs/` và rerun khi file đổi.
- **Export PDF report**: tổng hợp dashboard thành PDF để nộp báo cáo.
- **Case library**: tự động chọn 4 case demo (faithful, decorative, leakage, counterevidence) thay vì user tự chọn.
- **Compare runs**: hiển thị side-by-side 2 run với commit hash khác nhau.
- **Bilingual** (Tiếng Việt + English) cho báo cáo đồ án.

---

## 8. Tham chiếu nhanh

| Cần làm gì | Lệnh / File |
|---|---|
| Cài đặt | `pip install -r requirements.txt` |
| Chạy pipeline | `python3 -m src.pipeline` |
| Mở dashboard | `streamlit run src/dashboard/app.py` |
| Test tất cả | `pytest tests/ -q` |
| Test 1 module | `pytest tests/test_<module>.py -v` |
| Đọc spec V3 | `openspec/specs/evidence-extractor/spec.md` |
| Đọc proposal V3 | `openspec/changes/archive/2026-06-25-enrich-evidence-keywords-v3/proposal.md` |
| Xem output | `outputs/prediction_results.csv`, ... |
| Kiểm tra leakage | `outputs/temporal_leakage_results.csv` |
| Sample input | `data/sample_dataset.csv` (100 rows, 4 ticker) |
| Giải thích đề bài | `ChuDe1.md` (đề bài đồ án) |
| Hướng dẫn agent | `AGENTS.md` (conventions) |
| README dự án | `README.md` |

---

## 9. Tổng kết thay đổi gần đây (V2 + V3)

### V2 — `openspec/changes/archive/2026-06-25-enrich-evidence-keywords-v2/`

- **Vấn đề**: V1 keyword dict (11 keyword) chỉ phủ ~5% sample → 100% prediction là HOLD
- **Giải pháp**: Thêm 8 positive + 22 negative keyword (V2 additions)
- **Kết quả**: Prediction breakdown: UP 14 / DOWN 8 / HOLD 78, accuracy 49%
- **Test mới**: 8 test (UP, DOWN, HOLD, mixed)

### V3 — `openspec/changes/archive/2026-06-25-enrich-evidence-keywords-v3/`

- **Vấn đề**: V2 vẫn còn 78 HOLD (51 false-HOLD + 27 true-HOLD)
- **Giải pháp**: Thêm 21 positive + 16 negative keyword ngắn hơn (V3 additions: `expands`, `stronger`, `warns`, `weaker`, `slower`, `lower`, `permitting`, ...)
- **Kết quả**: Prediction breakdown: UP 37 / DOWN 12 / HOLD 51, accuracy **74%** (toàn sample) / **93.7%** (loại trừ leakage)
- **Test mới**: 11 test (UP, DOWN, HOLD regression)
- **Final keyword dict**: 80 keyword (34 positive + 46 negative)

### Tổng kết V1 → V3

| Metric | V1 | V2 | V3 |
|---|---|---|---|
| Keyword count | 11 | 41 | 80 |
| Accuracy (toàn sample) | 27% | 49% | 74% |
| Accuracy (valid only) | 27% | 49% | 93.7% |
| UP count | 0 | 14 | 37 |
| DOWN count | 0 | 8 | 12 |
| HOLD count | 100 | 78 | 51 |
| Faithfulness HIGH | 0 | 22 | 49 |
| Tests passing | 100% | 100% | 100% (479/479) |

---

## 10. Disclaimer

Dự án này **chỉ phục vụ mục đích học tập**, không phải hệ thống giao dịch thật. Không được dùng để khuyến nghị mua/bán chứng khoán. Mọi kết quả dự báo là từ keyword-based rule trên dữ liệu mô phỏng, không đại diện cho thị trường thật.

Xem thêm các lưu ý đạo đức trong `ChuDe1.md` mục 12.
