# Stock Trend Forecasting System

Prototype học thuật dự báo xu hướng cổ phiếu (UP/DOWN/HOLD) từ tin tức tài
chính, đồng thời kiểm chứng xem bằng chứng (evidence) mà mô hình trích dẫn
có thật sự liên quan, hợp lệ về mặt thời gian (temporal), và faithful với
từng dự đoán hay không.

## Setup

```bash
pip install -r requirements.txt
```

## Run

### End-to-end (thin runner)

```bash
python3 scripts/fetch_real_data.py   # một lần, cần mạng — tạo data/real_dataset.csv
python -m src.runner --input data/real_dataset.csv --output-dir outputs
# dừng sớm sau một stage:
python -m src.runner --input data/real_dataset.csv --output-dir outputs --stop-after forecast_model
```

`data/sample_dataset.csv` (144 dòng, có cả tin hợp lệ và tin vi phạm thời
gian) vẫn còn trong repo — dùng offline, không cần mạng, và là fixture bắt
buộc cho test suite/regression temporal-leakage:

```bash
python -m src.runner --input data/sample_dataset.csv --output-dir outputs
```

Runner chạy chuỗi stage in-process (cùng hàm `process()` mà CLI rời dùng),
ghi envelope trung gian `01_samples.json` … `08_market.json` rồi 6 CSV kết
quả vào `--output-dir`. Không LLM, FinBERT, transformer, GPU, hay external
API. Deterministic: chạy 2 lần → output byte-identical.

### Per-stage CLI (tương tác từng bước)

Output của stage này là input của stage sau — có thể `cat`/chỉnh file JSON
giữa các bước:

```bash
python -m src.ingest --input data/real_dataset.csv -o outputs/01_samples.json
python -m src.retriever --input outputs/01_samples.json -o outputs/02_retrieved.json
python -m src.evidence_extractor --input outputs/02_retrieved.json -o outputs/03_evidence.json
python -m src.forecast_model --input outputs/03_evidence.json -o outputs/04_forecast.json
python -m src.evidence_selector --input outputs/04_forecast.json -o outputs/05_selected.json
python -m src.faithfulness_evaluator --input outputs/05_selected.json -o outputs/06_faithfulness.json
python -m src.sufficiency_evaluator --input outputs/06_faithfulness.json -o outputs/07_sufficiency.json
python -m src.market_analyzer --input outputs/07_sufficiency.json -o outputs/08_market.json
python -m src.export_csv --input outputs/08_market.json --output-dir outputs
```

Mỗi stage validate schema input ở ranh giới (thiếu key/sai type → message
nêu rõ `sample_id` + key lỗi, exit code 2). Envelope là accumulating: stage
chỉ bổ sung field (`forecast`, `selection`, `faithfulness`, ...), không xóa
field của stage trước.

### Output files

| File | Mục đích |
|------|----------|
| `outputs/01_samples.json` … `08_market.json` | Envelope trung gian sau từng stage — inspect được toàn bộ state. |
| `outputs/prediction_results.csv` | Mỗi dòng ứng với một nhóm `(ticker, forecast_time)`, gồm `prediction`, `confidence`, `score`, `label`, `is_correct`, `rationale`, `cited_evidence_count`, `valid_news_count`, `invalid_future_news_count`. |
| `outputs/evidence_results.csv` | Mỗi dòng ứng với một evidence được trích xuất, kèm `evidence_role` (`pro` / `counter` / `neutral`) và cờ `is_cited`. |
| `outputs/faithfulness_results.csv` | Mỗi dòng ứng với một nhóm, gồm `original_confidence`, `confidence_without_cited_evidence`, `confidence_drop`, `temporal_validity`, `evidence_support`, `faithfulness_label` (`HIGH` / `MEDIUM` / `LOW`), `counterevidence_coverage`, `counterevidence_detected`. |
| `outputs/temporal_leakage_results.csv` | Mỗi dòng ứng với một tin có `news_time > forecast_time`; `leakage_type = future_news`. |
| `outputs/sufficiency_results.csv` | Mỗi dòng ứng với một nhóm, gồm `sufficiency_score` (chỉ dùng cited evidence), `prediction_on_only_cited`, `counterfactual_confidence`, `counterfactual_delta`. |
| `outputs/market_consistency_results.csv` | Mỗi dòng ứng với một nhóm, gồm `market_consistent`, `market_consistency_score`, `regime` (`bull` / `bear` / `sideways`), `next_day_return`, `price_5d_return`. |

## Project status

Chuỗi stage tương tác được: 8 stage CLI độc lập + thin runner end-to-end, 8 envelope JSON trung gian + 6 output CSV, và các metric nâng cao (B1–B4). Toàn bộ logic là deterministic, rule-based, không dùng LLM/ML/GPU.

**Baseline (A1–A7):**

- `temporal-retriever` — lọc tin theo thời gian, đảm bảo không dùng tin tương lai.
- `evidence-extractor` — trích xuất evidence bằng keyword matching (V1/V2/V3 dictionary).
- `evidence-selector` — phân loại pro / counter / neutral evidence theo prediction.
- `forecast-model-basic` — rule-based voting: UP/DOWN/HOLD với confidence và rationale.
- `faithfulness-evaluator` — 3 metric: temporal_validity, evidence_support, confidence_drop.
- `interactive-stage-cli` — mỗi stage một CLI (`python -m src.<stage>`), accumulating JSON envelope, schema validation ở ranh giới stage, thin runner (`src/runner.py`).

**Nâng cao (B1–B4):**

- `phase-b2-counterevidence-coverage` — tính counterevidence_coverage và counterevidence_detected.
- `phase-b1-sufficiency-counterfactual` — sufficiency score (chỉ dùng cited evidence) và counterfactual delta (thay cited bằng neutral placeholder).
- `phase-b3-market-consistency-regime` — so sánh prediction với next_day_return, phân tích regime bull/bear/sideways.
- `phase-b4-agentic-sdlc-maturity` — trace log (run_log.json), 3 agent role, quality gate, reflection.

## Dashboard

Dashboard Streamlit + Plotly, **read-only** trên envelope cuối
(`outputs/08_market.json`) — không gọi pipeline, không ghi file.

```bash
streamlit run src/dashboard/app.py
```

6 tab:

1. **🎬 Live Demo** — kịch bản demo 5 phút (ChuDe1.md §11.1): chọn ticker →
   chọn forecast date → tin hợp lệ (kèm cảnh báo tin tương lai bị loại) →
   prediction + phân rã vote UP/DOWN/HOLD → cited evidence + rationale →
   toggle "Remove cited evidence" so sánh confidence trước/sau (số liệu
   ablation đã tính sẵn ở faithfulness stage) → banner kết luận faithful.
2. **📊 Overview** — prediction distribution, accuracy, avg confidence/drop,
   accuracy theo ticker.
3. **📄 Evidence** — bảng evidence toàn dataset, filter ticker/role/cited.
4. **🔍 Faithfulness** — confidence drop chart (màu HIGH/MEDIUM/LOW) +
   radar 5 trục (temporal validity, evidence support, normalized drop,
   sufficiency B1, coverage B2).
5. **⏰ Temporal Leakage** — banner mức độ + bảng tin vi phạm sort theo
   leakage_minutes.
6. **🧪 B-metrics** — B1 sufficiency/counterfactual, B2 coverage,
   B3 market consistency/regime, B4 agent trace log.

### Export figure PNG cho báo cáo

Mỗi biểu đồ Plotly có nút camera (📷 *Download plot as png*) ở góc trên
phải — dùng nó để xuất 4 hình cho `outputs/figures/`:
`prediction_distribution.png` (tab Overview), `confidence_drop.png` và
`faithfulness_radar.png` (tab Faithfulness), `temporal_leakage_warning.png`
(chụp banner + bảng tab Temporal Leakage).

## Tests

```bash
pytest tests/
```

## Temporal Retriever

Temporal Retriever là stage đầu tiên của pipeline. Nó đảm bảo không có tin
tức được đăng **sau** thời điểm forecast có thể lọt xuống các module phía
sau.

```python
from src import TemporalRetriever

result = TemporalRetriever().retrieve(
    forecast_time="2025-03-12 09:00",  # naive → hiểu là UTC
    ticker="AAPL",
    news=[
        {"news_id": "n1", "news_time": "2025-03-11 08:00", "text": "Tin quá khứ"},
        {"news_id": "n2", "news_time": "2025-03-12 15:30", "text": "Tin tương lai"},
    ],
)
assert result.valid_count == 1
assert result.invalid_future_count == 1
assert result.temporal_validity == 0.5
assert result.ticker == "AAPL"
```

**Contract cho các module phía sau:** chỉ được dùng `valid_news`. Nhóm
`invalid_future_news` tồn tại để truy vết và cảnh báo trên dashboard — TUYỆT
ĐỐI không được đưa vào evidence extractor hay forecast model.

## Evidence Extractor

Evidence Extractor là stage thứ hai. Nó nhận một tin tức (đã được Temporal
Retriever kiểm chứng hợp lệ) và trả về danh sách evidence có cấu trúc, gồm
polarity, expected direction, character offset, và một `primary_evidence_id`
xác định deterministic.

Đây là module **rule-based, deterministic, và test được** — không LLM,
không FinBERT, không transformer. Xem
[`openspec/changes/evidence-extractor/specs/evidence-extractor/spec.md`](openspec/changes/evidence-extractor/specs/evidence-extractor/spec.md)
để biết spec đầy đủ.

### Một item đơn lẻ

```python
from src import EvidenceExtractor

result = EvidenceExtractor().extract({
    "news_id": "N001",
    "ticker": "GOOGL",
    "forecast_time": "2025-03-12 09:00",
    "news_time": "2025-03-11 15:30",
    "news_text": "Google raises guidance despite lawsuit risk",
})

# Hai evidence: một positive ("raises guidance"), một negative
# ("lawsuit"). summary.has_mixed_evidence là True. primary_evidence_id
# trỏ vào "lawsuit" (negative) vì Primary Evidence Rule ưu tiên
# negative > positive > neutral.
assert result["summary"]["has_mixed_evidence"] is True
assert result["primary_evidence_id"] == "N001_E002"
```

### Batch

```python
results = EvidenceExtractor().extract_batch([item1, item2, item3])
# Mỗi input trả về một result, giữ đúng thứ tự input. Không lọc theo thời gian.
```

### Contract cho module phía sau

- Evidence Extractor **không** lọc theo thời gian. Temporal Retriever sở
  hữu logic temporal validity; Extractor phải được giữ ngoài mọi code path
  tương lai có ý định lọc lại theo thời gian.
- `evidence_text` được **lowercase** theo spec. Character offset
  (`start_char`, `end_char`) tham chiếu đến `news_text` **gốc**.
- `matched_keyword` có thể là `null` với trường hợp fallback neutral.
  `support_score` là `1.0` khi match keyword và `0.5` khi neutral.
- Format `evidence_id` là `<news_id>_E<index>`, zero-pad 3 chữ số
  (ví dụ `N001_E001`).
- `extraction_method` luôn là literal `"rule_based_keyword"`.

### Keyword dictionary — single source of truth

Bảng polarity và direction nằm ở `src/evidence_extractor.py` dưới dạng
hằng số module-level:

- `POSITIVE_KEYWORDS`, `NEGATIVE_KEYWORDS`, `KEYWORDS`, `KEYWORD_TO_POLARITY`
- `POLARITY_TO_DIRECTION`, `SUPPORT_SCORES`

Các module tương lai (Evidence Selector, Counterevidence Coverage, Forecast
Model) PHẢI import từ module này thay vì tự định nghĩa lại rule polarity.

## Evidence Selector

Evidence Selector nhận prediction từ Forecast Model cùng danh sách candidate
từ Evidence Extractor, rồi phân loại từng candidate thành `pro`, `counter`,
hoặc `neutral` bằng một mapping rule-based deterministic. Selector chủ ý
không dùng ML: không LLM, không FinBERT, không training, không truy cập
mạng.

### Vì sao cần selector này

Một lời giải thích một chiều — chỉ đưa ra evidence ủng hộ prediction — sẽ
che giấu mâu thuẫn. Selector tồn tại để biến counterevidence thành một
output hạng nhất, giúp Faithfulness Evaluator và Dashboard thể hiện góc
nhìn cân bằng hơn.

### Phân loại

| prediction | evidence.expected_direction | selector_label |
| ---------- | --------------------------- | -------------- |
| UP         | UP                          | pro            |
| UP         | DOWN                        | counter        |
| UP         | HOLD                        | neutral        |
| DOWN       | DOWN                        | pro            |
| DOWN       | UP                          | counter        |
| DOWN       | HOLD                        | neutral        |
| HOLD       | HOLD                        | pro            |
| HOLD       | UP or DOWN                  | counter        |

### Một prediction đơn lẻ

```python
from src import EvidenceSelector

request = {
    "ticker": "AAPL",
    "forecast_time": "2025-03-12 09:00",
    "prediction": "UP",
    "confidence": 0.82,
    "evidence_candidates": [
        {
            "news_id": "N001",
            "ticker": "AAPL",
            "news_time": "2025-03-11 08:30",
            "evidence_text": "Apple launches new product",
            "polarity": "positive",
            "expected_direction": "UP",
            "extractor_score": 0.9,
        },
        {
            "news_id": "N002",
            "ticker": "AAPL",
            "news_time": "2025-03-11 10:00",
            "evidence_text": "iPhone sales in China decline",
            "polarity": "negative",
            "expected_direction": "DOWN",
            "extractor_score": 0.85,
        },
    ],
}

result = EvidenceSelector().select(request)
# result["pro_evidence"], result["counterevidence"], result["neutral_evidence"]
# result["invalid_future_evidence"], result["summary"], result["selection_method"]
```

### Batch

```python
results = EvidenceSelector().select_batch([request_a, request_b, request_c])
# Mỗi input trả về một result, giữ đúng thứ tự input.
```

### Contract cho module phía sau

- **Input**: `prediction` phải là `UP` / `DOWN` / `HOLD`; `evidence_candidates`
  phải là một list. Bất kỳ trường hợp nào khác sẽ raise `EvidenceSelectorError`.
- **Output**: `pro_evidence`, `counterevidence`, `neutral_evidence`,
  `invalid_future_evidence` luôn là list (không bao giờ `None`), sort giảm
  dần theo `selector_score`, cắt còn `top_k` mỗi nhóm.
- **Đếm số lượng**: `summary.pro_count` / `counter_count` / `neutral_count`
  dùng tổng số *trước khi cắt* (top_k) để coverage metric của Faithfulness
  Evaluator không bị lệch do giới hạn hiển thị.
- **Tin tương lai**: candidate có `news_time > forecast_time` được đưa vào
  `invalid_future_evidence` và loại khỏi pro/counter/neutral. Timestamp
  naive được hiểu là UTC.
- **Không rò rỉ label**: selector không bao giờ đọc ground-truth label.
  Kể cả khi candidate có thêm field `ground_truth_label` hay `actual`,
  việc phân loại chỉ dựa vào `expected_direction`, và các field đó bị
  loại khỏi output.
- **`compute_coverage`**: helper tùy chọn cho Faithfulness Evaluator; tính
  Counterevidence Coverage từ `expected_labels` dict do caller cung cấp,
  không bao giờ lấy từ input candidates.

### Configuration

| kwarg           | mặc định | ghi chú                          |
| --------------- | -------- | --------------------------------- |
| `top_k_pro`     | 3        | giới hạn số pro evidence mỗi nhóm  |
| `top_k_counter` | 3        | giới hạn số counter evidence       |
| `top_k_neutral` | 3        | giới hạn số neutral evidence       |

### Hạn chế

- Phân loại rule-based có thể sai với tin có sắc thái phức tạp, mixed-sentiment,
  hoặc mỉa mai (sarcastic) — nơi `expected_direction` không phản ánh đúng
  ý nghĩa thật.
- Ranking V1 chỉ dùng `extractor_score`. Field `selector_score` được giữ
  lại như một điểm mở rộng tương lai cho công thức
  `extractor_score * keyword_strength * recency_weight`.
- `top_k` cắt bớt sẽ âm thầm loại bỏ item vượt giới hạn. Consumer phía sau
  cần biết số lượng trước khi cắt phải đọc `summary.pro_count` /
  `counter_count` / `neutral_count`.
- Selector không validate field `confidence`. Nó được giữ nguyên trong
  output để Faithfulness Evaluator sử dụng.

## Forecast Model

Forecast Model là stage thứ tư. Nó nhận một forecast request (một cho mỗi
`sample_id`) và danh sách **evidence đã được chọn lọc, hợp lệ** — đã qua
lọc của Temporal Retriever và phân loại của Evidence Selector — rồi trả về
một prediction deterministic `UP` / `DOWN` / `HOLD` kèm confidence ổn định,
số lượng evidence, danh sách pro/counter evidence, rationale dạng template,
và một danh sách warnings có cấu trúc.

Version 1 là **rule-based, deterministic, và truy vết được**. KHÔNG dùng
LLM, FinBERT, transformer model, logistic regression, deep-learning model,
external API, hay price feature. Rationale được chọn từ một tập nhỏ cố
định các template string.

### Thuật toán

```
positive_count = |{ e : e.expected_direction == "UP" }|
negative_count = |{ e : e.expected_direction == "DOWN" }|
neutral_count  = |{ e : e.expected_direction == "HOLD" }|
score          = positive_count - negative_count

if score  > 0: prediction = "UP"
elif score < 0: prediction = "DOWN"
else:           prediction = "HOLD"

confidence         = 0.5 + min(abs(score) * 0.1, 0.45)   clamp về [0.5, 0.95]
evidence_strength  = abs(score) / (positive_count + negative_count)  (= 0 khi mẫu số bằng 0)
conflict_ratio     = min(positive_count, negative_count) / max(positive_count + negative_count, 1)
```

Neutral evidence (`expected_direction = "HOLD"`) không ảnh hưởng đến score
nhưng vẫn được giữ trong `neutral_evidence` để truy vết.

**`class_confidences`** — phân rã vote UP/DOWN/HOLD deterministic (tổng
bằng 1.0, `class_confidences[prediction] == confidence`), tính thuần từ
`positive_count`/`negative_count`/`neutral_count`: class thắng giữ
`confidence`, phần còn lại (`1.0 - confidence`) chia cho hai class kia theo
tỷ lệ số lượng của chúng (chia đều nếu cả hai bằng 0). Đây là một phân rã
mô tả rule-based, **không phải xác suất được hiệu chỉnh (calibrated)** —
nó tồn tại để tab Live Demo của dashboard có thể hiển thị "vote thực sự
chia như thế nào" thay vì chỉ confidence của class thắng. Được lưu dưới
dạng `class_confidence_up` / `class_confidence_down` / `class_confidence_hold`
trong `prediction_results.csv`.

### Input schema

| Field           | Kiểu   | Bắt buộc | Mô tả |
|-----------------|--------|----------|-------|
| `sample_id`     | string | có       | Định danh ổn định; được echo lại trong output. |
| `ticker`        | string | có       | Mã cổ phiếu; echo lại trong output. Không dùng để filter. |
| `forecast_time` | string | có       | Timestamp ISO naive (hiểu là UTC). So sánh với `evidence[].news_time` của từng item. |
| `evidence`      | list   | có       | Danh sách evidence đã chọn. Có thể rỗng. |
| `label`         | string | không    | Ground-truth label (`UP` / `DOWN` / `HOLD`) dùng để evaluation. `predict` **KHÔNG** được đọc field này. |

Mỗi evidence item cần `evidence_id`, `news_id`, `news_time`,
`evidence_text`, `polarity`, và `expected_direction`. `support_score` là
optional (mặc định `0.0` trong output).

### Output schema

Kết quả là một dict `ForecastResult` gồm `sample_id`, `ticker`,
`forecast_time`, `prediction`, `confidence`, `score`, bốn số đếm
(`positive_count`, `negative_count`, `neutral_count`,
`total_evidence`, `directional_evidence_count`), hai metric dẫn xuất
(`evidence_strength`, `conflict_ratio`), năm danh sách evidence
(`pro_evidence`, `counter_evidence`, `up_evidence`, `down_evidence`,
`neutral_evidence`), `rationale`, `warnings`, và `model_version` (literal
string `"rule_based_v1"`).

Cả năm danh sách evidence luôn là list (không bao giờ `null`), sort tăng
dần theo `evidence_id`. `warnings` luôn tồn tại và có thể rỗng.

### Rationale templates

| Nhánh | Template |
|--------|----------|
| `prediction = UP`   | `"Prediction UP because positive evidence count ({positive_count}) is greater than negative evidence count ({negative_count})."` |
| `prediction = DOWN` | `"Prediction DOWN because negative evidence count ({negative_count}) is greater than positive evidence count ({positive_count})."` |
| `prediction = HOLD`, `directional_evidence_count > 0` | `"Prediction HOLD because positive and negative evidence are balanced."` |
| `prediction = HOLD`, `directional_evidence_count == 0` | `"Prediction HOLD because positive and negative evidence are balanced or no valid directional evidence is available."` |

Các template này cũng được export dưới dạng hằng số `RATIONALE_TEMPLATES`
trong `src.forecast_model` để module phía sau import thay vì định nghĩa
lại literal string.

### Một prediction đơn lẻ

```python
from src import ForecastModel

request = {
    "sample_id": "S0001",
    "ticker": "AAPL",
    "forecast_time": "2025-03-12 09:00",
    "label": "UP",
    "evidence": [
        {
            "evidence_id": "N001_E001",
            "news_id": "N001",
            "news_time": "2025-03-11 08:30",
            "evidence_text": "strong sales",
            "polarity": "positive",
            "expected_direction": "UP",
            "support_score": 1.0,
        },
        # ... thêm evidence khác
    ],
}

result = ForecastModel().predict(request)
# result["prediction"], result["confidence"], result["score"],
# result["pro_evidence"], result["counter_evidence"],
# result["rationale"], result["warnings"], result["model_version"]
```

### Hỗ trợ faithfulness

```python
# Chạy lại forecast sau khi loại bỏ cited evidence. Dùng cho
# Faithfulness Evaluator để tính confidence_drop.
reduced = ForecastModel().predict_without_evidence(request, ["N001_E001", "N002_E001"])

confidence_drop = original["confidence"] - reduced["confidence"]
```

### Batch và CSV

```python
model = ForecastModel()
results = model.predict_batch([r1, r2, r3])
# Mỗi input trả về một result, giữ đúng thứ tự input.
# Mặc định ghi CSV vào outputs/prediction_results.csv và
# JSON sibling vào outputs/prediction_results.json. Truyền
# output_csv_path=None / output_json_path=None để tắt.

metrics = model.compute_accuracy_and_confusion(results)
# metrics["accuracy"], metrics["confusion_matrix"], metrics["per_class"], metrics["n_samples"]
```

Header CSV cố định, khớp với `CSV_COLUMNS` trong `src.forecast_model`:
`sample_id`, `ticker`, `forecast_time`, `prediction`, `confidence`,
`score`, `positive_count`, `negative_count`, `neutral_count`,
`total_evidence`, `directional_evidence_count`, `evidence_strength`,
`conflict_ratio`, `label`, `model_version`.

### Contract cho module phía sau

- **Không đọc raw news**: model KHÔNG được đọc `news_text`, `title`, hay
  bất kỳ field raw-news nào khác. Nó chỉ tiêu thụ evidence đã được
  pipeline phía trước xác thực.
- **Không đọc `label` khi predict**: `predict` echo lại `label` vào result
  để phục vụ helper evaluation; không bao giờ đọc nó để scoring.
- **Defense in depth**: `news_time` của từng evidence item luôn được so
  sánh với `forecast_time`. Item tương lai bị loại và báo warning
  `TEMPORAL_LEAKAGE_BLOCKED`. Đây là bước kiểm tra chủ ý trùng lặp với
  Temporal Retriever.
- **Default phòng thủ**: evidence item xấu (`INVALID_EVIDENCE`,
  `DUPLICATE_EVIDENCE_ID`, `MALFORMED_NEWS_TIME`) bị bỏ qua kèm warning;
  `predict_batch` bắt `ForecastModelError` cho từng record và thay bằng
  result `HOLD` mặc định kèm warning `INPUT_ERROR`. Dùng `strict=True` để
  raise khi `expected_direction` không hợp lệ.
- **Determinism**: input giống hệt nhau cho ra output byte-equal
  (`json.dumps(result, sort_keys=True)` ổn định). Thứ tự item trong mỗi
  danh sách evidence là tăng dần theo `evidence_id`.

### Hạn chế

- **Score chỉ là số nguyên**: không có trọng số `support_score`, không
  weighting theo keyword, không weighting theo độ mới (recency). Năm item
  positive yếu trông giống hệt một item positive mạnh. Field
  `evidence_strength` và `conflict_ratio` phơi bày cùng thông tin đó ở
  cái nhìn nhanh.
- **Confidence bão hòa**: confidence bão hòa khi `abs(score) = 5`
  (`0.95`). Vượt ngưỡng này, thêm evidence không làm confidence thay đổi.
- **Rationale dạng template**: rationale chủ ý dùng template (không có
  sắc thái, không LLM). Người đọc không rành kỹ thuật có thể hiểu
  "positive evidence count (1) is greater than negative evidence count
  (0)" mạnh hơn thực tế một match đơn lẻ đáng có.
- **V1 không phải hệ thống giao dịch**: model chủ ý được thiết kế yếu.
  Mục đích là faithful với evidence nó trích dẫn (mọi prediction đều suy
  ra được từ evidence được cite, mọi cited evidence đều loại bỏ được qua
  `predict_without_evidence`), chứ không phải để chính xác.
- **Điểm mở rộng cho V2**: keyword strength và recency weighting được ghi
  nhận là công việc tương lai, sẽ thay đổi thuật toán nhưng không phá vỡ
  public API contract (`model_version` trở thành filter key).

## Faithfulness Evaluator

Faithfulness Evaluator là stage thứ năm. Với một `ForecastResult` từ
Forecast Model và envelope input đã tạo ra nó, module này trả lời câu hỏi
nghiên cứu trung tâm: **"Khi model trích dẫn evidence cho prediction của
nó, evidence đó có thật sự ảnh hưởng đến prediction hay không?"**

Version 1 là **deterministic, rule-based, và không side-effect trong chế
độ evaluate đơn lẻ**. KHÔNG dùng LLM, FinBERT, transformer model, logistic
regression, deep-learning model, hay external API. KHÔNG re-extract hay
re-classify evidence. Nó gọi lại `src.forecast_model.predict_without_evidence`
cho bước ablation, còn lại chỉ thao tác trên result được truyền vào.

### Ba metric bắt buộc

| Metric               | Công thức                                                                                                                                       |
|----------------------|-----------------------------------------------------------------------------------------------------------------------------------------------|
| `temporal_validity`  | `1.0` nếu mọi cited evidence có `news_time <= forecast_time`; `0.0` nếu có item bất kỳ với `news_time > forecast_time`; `1.0` khi list rỗng. |
| `evidence_support`   | Trung bình support score của từng item (`1.0` match chính xác, `0.5` HOLD so với UP/DOWN, `0.0` ngược chiều). `1.0` khi list rỗng.          |
| `confidence_drop`    | `original_confidence - confidence_after_removal`. Có dấu; có thể âm. Warning `confidence_increased_after_removal` được thêm khi giá trị âm. |

### Composite score tùy chọn (heuristic V1)

```
normalized_drop = min(max(confidence_drop, 0.0) / 0.30, 1.0)
faithfulness_score = 0.35 * temporal_validity
                   + 0.30 * evidence_support
                   + 0.35 * normalized_drop
```

`faithfulness_score` nằm trong `[0.0, 1.0]`. `confidence_drop` âm được
clamp về `0.0` cho composite; giá trị có dấu vẫn được giữ nguyên trong
report. **Composite được ghi nhận là heuristic V1 cho dashboard, không
phải một metric đã được validate khoa học.** `confidence_drop` mới là
tín hiệu chính.

### Verdict cascade

```
temporal_validity < 1.0          → invalid_temporal_leakage
evidence_support  < 0.5           → unsupported_evidence
cited_evidence rỗng                → decorative_explanation_risk
prediction_after_removal != prediction → strong_faithful_candidate
confidence_drop >= 0.20           → strong_faithful_candidate
confidence_drop >= 0.10           → moderate_faithful_candidate
confidence_drop >= 0.05           → weak_faithful_candidate
còn lại                            → decorative_explanation_risk
```

Sáu label này được export dưới dạng hằng số `VERDICTS` (`frozenset`).

### Chiến lược ablation

| Chiến lược                    | Mô tả                                                                                                |
|-----------------------------|-----------------------------------------------------------------------------------------------------|
| `remove_cited_pro_evidence` | Mặc định. Loại mọi evidence item có `evidence_id` nằm trong `pro_evidence` (evidence ủng hộ). |
| `remove_all_cited_evidence` | Loại mọi evidence item có `evidence_id` nằm trong `pro_evidence` HOẶC `counter_evidence`.     |

Khi Forecast Model chỉ nhận input ở mức news-level, tập `evidence_id`
được gộp thành tập `news_id`, và việc mở rộng đó được ghi lại trong
`ablation_warnings` dưới dạng
`"COLLAPSED_BY_NEWS_ID: <news_id> (expanded from <evidence_id_list>)"`.

### Một lượt evaluate

```python
from src import FaithfulnessEvaluator, ForecastModel

request = {
    "sample_id": "S0001",
    "ticker": "AAPL",
    "forecast_time": "2025-03-12 09:00",
    "label": "UP",
    "evidence": [
        {
            "evidence_id": "N001_E001",
            "news_id": "N001",
            "news_time": "2025-03-11 08:30",
            "evidence_text": "strong sales",
            "polarity": "positive",
            "expected_direction": "UP",
            "support_score": 1.0,
        },
        # ... thêm evidence khác
    ],
}
result = ForecastModel().predict(request)
report = FaithfulnessEvaluator().evaluate(request, result)
# report["temporal_validity"], report["evidence_support"],
# report["confidence_drop"], report["faithfulness_score"],
# report["verdict"], report["per_evidence_results"],
# report["temporal_warnings"], report["support_warnings"],
# report["ablation_warnings"]
```

### Batch evaluation và export CSV/JSON

```python
from src import FaithfulnessEvaluator, ForecastModel

records = [request1, request2, request3]
results = ForecastModel().predict_batch(records, output_csv_path=None)
reports = FaithfulnessEvaluator().evaluate_batch(
    list(zip(records, results)),
    output_csv_path="outputs/faithfulness_results.csv",
    output_json_path="outputs/faithfulness_results.json",
)
```

Header CSV là hằng số `CSV_COLUMNS` trong `src.faithfulness_evaluator`:

```
ticker, forecast_time, prediction, original_confidence,
prediction_after_removal, confidence_after_removal, confidence_drop,
temporal_validity, evidence_support, faithfulness_score,
verdict, warnings
```

Cột `warnings` là JSON encoding của ba danh sách nối lại
`temporal_warnings + support_warnings + ablation_warnings`.

### Hạn chế

- **Composite là heuristic**: `faithfulness_score` V1 là một blend có
  trọng số của ba sub-metric; `confidence_drop` là tín hiệu chính, còn
  composite chỉ dùng để hiển thị nhanh trên dashboard.
- **Verdict cascade cố định**: ngưỡng (`0.05`, `0.10`, `0.20`) được pin
  cứng trong spec, chưa configurable ở V1. Thay đổi tương lai có thể expose
  chúng thành parameter mà không phá vỡ verdict hiện có.
- **Single-ticker, single-ablation**: mỗi lần gọi `evaluate(...)` độc lập
  và chỉ dùng một chiến lược ablation. Leave-one-out ablation cho từng
  evidence được ghi nhận là điểm mở rộng V2.
- **Gọi lại Forecast Model**: evaluator tốn gấp đôi runtime mỗi lần
  evaluate (một lần gọi `predict`, một lần gọi
  `predict_without_evidence`). Với batch 100 dòng, mức này chấp nhận
  được.
- **V1 không phải calibration**: evaluator là một hàm deterministic của
  result và model; nó không phải một bộ ước lượng faithfulness theo xác
  suất.

## Agentic SDLC

Dự án áp dụng mô hình **Agentic AI trong SDLC**: AI agent hỗ trợ từng bước của vòng đời phát triển phần mềm, nhưng con người luôn kiểm soát và review trước khi accept.

### Ba agent role

| Role | Nhiệm vụ | Bước SDLC |
|------|----------|-----------|
| **Research Agent** | Phân tích bài toán, xác định metric gap, viết `proposal.md` cho từng change (B1–B4) | Requirement, Design |
| **Coding Agent** | Implement module theo spec (`sufficiency_evaluator.py`, `market_analyzer.py`, `agent_trace.py`, stage CLI/runner) | Implementation |
| **Testing/Review Agent** | Sinh test case, chạy pytest, verify output CSV, review code | Testing, Evaluation |

### Quality gates

Mỗi change trong `openspec/changes/` phải qua các gate trước khi được merge:

1. **Spec review** — proposal.md và design.md phải được con người đọc và approve.
2. **pytest pass** — toàn bộ `pytest tests/` phải green.
3. **Runner smoke test** — `python -m src.runner --input data/sample_dataset.csv --output-dir outputs` không lỗi.
4. **Output review** — output CSV được kiểm tra cột, kiểu dữ liệu, và giá trị mẫu.

### Minh chứng

- `src/agent_trace.py` — API trace log (write/load/summarize) cho 3 role.
- `openspec/changes/phase-b4-agentic-sdlc-maturity/reflection.md` — phân tích lessons learned từ Agentic SDLC.
- `openspec/changes/` — mỗi thư mục có `proposal.md`, `design.md`, `tasks.md` là bằng chứng spec-driven workflow.

Con người không để AI tự quyết định kiến trúc hay merge code — mỗi bước đều có checkpoint review rõ ràng.

## Disclaimer

Dự án này phục vụ mục đích nghiên cứu và học tập. Đây không phải một hệ
thống giao dịch và không đưa ra khuyến nghị đầu tư.
