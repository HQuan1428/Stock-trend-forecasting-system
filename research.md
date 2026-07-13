# Research: Thuật toán các phase pipeline (trừ Forecast Model)

> Tổng hợp từ đọc trực tiếp source code (`src/retriever.py`, `src/evidence_extractor.py`,
> `src/evidence_selector.py`, `src/faithfulness_evaluator.py`, `src/faithfulness_metrics.py`,
> `src/sufficiency_evaluator.py`, `src/market_analyzer.py`). Không bao gồm `ForecastModel`
> (`src/forecast_model.py`) theo yêu cầu.

## 1. `TemporalRetriever` (src/retriever.py) — lọc thời gian

**Input**: `forecast_time: str`, `news: List[dict]` (mỗi item cần `news_id`, `news_time`, body ở
`text`/`news_text`), `ticker` (optional, chỉ echo lại).

**Output**: `RetrievalResult` (frozen dataclass) gồm `valid_news`, `invalid_future_news`,
`valid_count`, `invalid_future_count`, `total_count`, `temporal_validity` (= valid/total),
`errors`.

**Thuật toán**:
1. Parse `forecast_time` qua `TimeUtils.parse_utc` (naive → gán UTC, aware → convert UTC). Lỗi
   parse → raise `TemporalValidationError`.
2. Với mỗi news item: parse `news_time`; nếu malformed/missing → đẩy vào `errors`, loại khỏi cả
   2 nhóm.
3. So sánh `news_time <= forecast_time` → `valid_news`, ngược lại → `invalid_future_news`. Copy
   dict, không mutate, giữ nguyên mọi field lạ.

## 2. `EvidenceExtractor` (src/evidence_extractor.py) — trích evidence bằng keyword

**Input**: news item (`news_id`, `ticker`, `forecast_time`, `news_time`, `news_text`).

**Output**: `{news_id, ticker, forecast_time, news_time, evidence: [...], summary,
extraction_method="rule_based_keyword", primary_evidence_id}`.

**Thuật toán**:
1. Tìm mọi occurrence của từng keyword trong `POSITIVE_KEYWORDS`/`NEGATIVE_KEYWORDS`
   (case-insensitive):
   - Exact substring match trước.
   - Nếu keyword nhiều từ và không match exact → token-level match: tách từ, tìm vị trí từng
     từ, chấp nhận cửa sổ có thứ tự tăng dần và gap ≤ 15 ký tự giữa 2 từ liên tiếp (cho phép
     chèn 1 từ bổ nghĩa, vd "weak iPhone sales").
2. Resolve overlap: sort theo (độ dài giảm dần, start_char tăng dần), giữ match dài nhất, loại
   match chồng lấn.
3. Build evidence objects: `evidence_id = news_id_E00N`, `polarity`, `expected_direction`
   (positive→UP, negative→DOWN), `support_score` (1.0 directional, 0.5 neutral). Nếu không
   match gì → trả về đúng 1 evidence neutral(cơ chế fallback trả về) rỗng.
4. `summary`: đếm positive/negative/neutral, cờ `has_mixed_evidence`. -> bước này là chuẩn bị cho bước chọn `primary_evidence_id`.
5. `primary_evidence_id`: ưu tiên negative > positive > neutral, tie-break theo `start_char`
   nhỏ nhất.

  --- I/O evidence extractor ---

**I/O thực tế trong pipeline** (`src/pipeline.py:290-320`, wiring giữa phase 1 và phase 2):

- **Input** = chỉ `valid_news` (output phase 1 từ `TemporalRetriever`), **không** gồm
  `invalid_future_news` — đúng nguyên tắc temporal validity bất khả xâm phạm.
- **Output của `extract_batch()`** không phải một `evidence_list` phẳng, mà là list các
  **result dict theo từng news item** (`extractor_results`), mỗi dict có field `evidence`
  (list) lồng bên trong — xem cấu trúc ở dòng 29-30 phía trên.
- **`evidence_list` phẳng** dùng cho stage sau (`EvidenceSelector`/`ForecastModel`) là do
  `PipelineRunner` tự làm thêm: duyệt từng `result` trong `extractor_results`, lấy
  `result["evidence"]`, gắn `news_time`, rồi gộp evidence của mọi tin trong group thành 1 list
  duy nhất (`pipeline.py:314-320`) — bước flatten này **không** nằm trong `EvidenceExtractor`.

```
valid_news (phase 1)
    → EvidenceExtractor.extract_batch()
    → List[per-news result dict]      (evidence lồng bên trong mỗi dict)
    → PipelineRunner flatten thủ công
    → evidence_list phẳng             (input cho ForecastModel, rồi tới EvidenceSelector)
```

## 3. `EvidenceSelector` (src/evidence_selector.py) — phân loại pro/counter/neutral (+ B2 coverage)

**Input** (`select`): `{ticker, forecast_time, prediction, confidence, evidence_candidates}` —
**không đọc label thật** (chống leakage).

**Output**: `{..., pro_evidence, counterevidence, neutral_evidence, invalid_future_evidence,
summary, selection_method="rule_based"}`.

**I/O thực tế trong pipeline** (`src/pipeline.py:337-359`, wiring giữa phase 3 và 4 — lưu ý
`EvidenceSelector` chạy **sau** `ForecastModel`, không song song với nó):

- **Input** = ghép từ 2 nguồn:
  - `prediction`, `confidence` ← lấy từ output của **`ForecastModel.predict()`** (stage 3).
  - `evidence_candidates` ← từ **`evidence_list` phẳng** (kết quả flatten của stage 2
    `EvidenceExtractor`), map gần như 1-1 field, chỉ đổi tên `support_score` →
    `extractor_score`.
- **Output** dùng tiếp ở đâu (`pipeline.py:356-369`):
  - `pro_evidence` ∪ `counterevidence` (theo `news_id`) → `cited_ids` → input cho
    `SufficiencyEvaluator` (B1).
  - `pro_evidence` riêng → dùng làm evidence bị xoá trong ablation test của
    `FaithfulnessEvaluator` (A6, chiến lược mặc định `remove_cited_pro_evidence`).
  - `summary` (`counterevidence_ratio`, `has_counterevidence`) → phát hiện giải thích một
    chiều (cherry-picking), hiển thị dashboard.

```
evidence_list (stage 2) + prediction/confidence (stage 3 ForecastModel)
    → EvidenceSelector.select()
    → {pro_evidence, counterevidence, neutral_evidence, invalid_future_evidence, summary}
    → cited_ids → SufficiencyEvaluator (B1) / FaithfulnessEvaluator (A6)
```

**Thuật toán**:
1. Validate `prediction` ∈ {UP,DOWN,HOLD}, `evidence_candidates` là list.
2. Với mỗi candidate: nếu `expected_direction` không hợp lệ → `invalid_candidates`. Nếu
   `news_time > forecast_time` → `invalid_future_evidence` (defense-in-depth, không dùng để
   lọc chính).
3. Tra `CLASSIFICATION_TABLE[(prediction, expected_direction)]` — bảng cố định 9 ô (vd
   UP+UP=pro, UP+DOWN=counter, UP+HOLD=neutral, HOLD+UP/DOWN=counter...) → gán `selector_label`
   + `reason` giải thích.
4. Sort mỗi nhóm theo `selector_score` (=`extractor_score`) giảm dần, cắt `top_k` (mặc định 3).
5. `summary.counterevidence_ratio = counter_count/(pro_count+counter_count)`.

**B2 — `compute_coverage`**: so `expected_labels` (gán tay) với `counterevidence` đã detect →
`counterevidence_coverage = detected/available`, `counterevidence_detected_rate` (0/1).

## 4. `FaithfulnessEvaluator` + `FaithfulnessMetrics` (A6) — đo tính "faithful"

**Input** (`evaluate`): `original_input` (request gốc), `original_result` (ForecastResult),
`ablation_strategy` (mặc định `remove_cited_pro_evidence`).

**Output**: report dict gồm `temporal_validity`, `evidence_support`, `confidence_drop`,
`confidence_after_removal`, `prediction_after_removal`, `faithfulness_score`, `verdict`, các
danh sách warning, `per_evidence_results`.

**Thuật toán** (3 metric cốt lõi):
- **temporal_validity**: 1.0 nếu mọi cited evidence có `news_time ≤ forecast_time`, ngược lại
  0.0 (list rỗng → vacuous truth = 1.0).
- **evidence_support**: trung bình `evidence_support_score` từng item — 1.0 nếu direction khớp
  prediction, 0.5 nếu 1 bên là HOLD, 0.0 nếu ngược chiều.
- **confidence_drop** (ablation): chọn evidence cần xoá theo strategy (chỉ pro, hoặc cả
  pro+counter) → gọi lại `ForecastModel.predict_without_evidence()` để có prediction/confidence
  sau khi xoá → `drop = original_confidence − confidence_after_removal_of_original_class` (nếu
  prediction đổi hướng thì confidence lớp gốc coi như 0).
- **faithfulness_score** = `0.35*temporal_validity + 0.30*evidence_support +
  0.35*min(max(drop,0)/0.30, 1)`.
- **verdict**: cascade theo thứ tự cố định — cited rỗng→`decorative_explanation_risk`; tv<1→
  `invalid_temporal_leakage`; es<0.5→`unsupported_evidence`; prediction đổi hoặc drop≥0.20→
  `strong_faithful_candidate`; drop≥0.10→`moderate`; drop≥0.05→`weak`; còn lại→
  `decorative_explanation_risk`.
- Sinh thêm `temporal_warnings` (MALFORMED_NEWS_TIME/TEMPORAL_LEAKAGE), `support_warnings`
  (UNSUPPORTED), `ablation_warnings`.

**Mục đích của phase này**: trả lời câu hỏi trung tâm của đề tài — *model nói nó dựa vào
evidence X để dự đoán, nhưng evidence đó có thực sự quyết định kết quả, hay chỉ là lời giải
thích gắn vào sau (decorative)?* 3 metric nhắm 3 khía cạnh khác nhau của "faithful":
- `temporal_validity` — lớp phòng thủ thứ 3 cho leakage (sau Retriever và Selector); cited từ
  tương lai thì giải thích vô giá trị ngay từ đầu.
- `evidence_support` — kiểm tra evidence cite ra có **nhất quán logic** với prediction không.
- `confidence_drop` (ablation) — phép đo **nhân quả thực nghiệm** duy nhất: chủ động xoá
  evidence đã cite rồi chạy lại model, đo confidence tụt bao nhiêu, thay vì chỉ tin lời model
  nói. `faithfulness_score`/`verdict` gộp 3 con số này thành 1 nhãn để dashboard lọc nhanh
  prediction nào đáng tin, prediction nào chỉ "trang trí".

**Lưu ý kiến trúc — có 2 bộ phân loại pro/counter độc lập trong pipeline, không dùng chung
logic**:
- `ForecastModel._build_pro_and_counter` (`forecast_model.py:595-605`) — field
  `pro_evidence`/`counter_evidence` (có underscore); HOLD → **cả 2 nhóm đều rỗng**. Đây là field
  mà `FaithfulnessEvaluator._extract_cited_evidence` thực sự đọc (`original_result` truyền vào
  `evaluate()` là output của `ForecastModel.predict()`, **không phải** output của
  `EvidenceSelector`).
- `EvidenceSelector.CLASSIFICATION_TABLE` (mục 3 phía trên) — field `pro_evidence`/
  `counterevidence` (không underscore); HOLD-HOLD → `pro`.

Hai bộ này khác nhau ở case HOLD, nên `faithfulness_results.csv` (dựa trên bộ của
`ForecastModel`) và output của `EvidenceSelector` (dùng cho B1/B2/dashboard) có thể không khớp
nhau nếu so trực tiếp field `pro_evidence`.

## 5. `SufficiencyEvaluator` (B1) — sufficiency + counterfactual

**Input**: `original_input`, `original_result`, `cited_evidence_ids` (set news_id từ
pro+counter).

**Output**: `{sufficiency_confidence, sufficiency_score, prediction_on_only_cited,
counterfactual_confidence, counterfactual_delta}`.

**Thuật toán**:
- **Sufficiency**: lọc evidence chỉ giữ item có `news_id` trong `cited_evidence_ids`, chạy lại
  `ForecastModel.predict()` → `sufficiency_score = min(suff_confidence/original_confidence,
  1.0)` (0 nếu không có evidence nào được cite).
- **Counterfactual**: thay từng cited item bằng placeholder neutral (`expected_direction=HOLD,
  support_score=0.5`, giữ nguyên item không cited), chạy lại `predict()` →
  `counterfactual_delta = original_confidence − counterfactual_confidence`.

## 6. `MarketAnalyzer` (B3) — market consistency + regime

**Input**: `prediction`, `next_day_return: float`, `price_5d_return: float`.

**Output**: `{market_consistent, market_consistency_score, regime, next_day_return,
price_5d_return}`.

**Thuật toán**: hàm thuần túy, không I/O phức tạp —
- `market_consistent`: UP khớp nếu `next_day_return > 0.005`; DOWN nếu `< -0.005`; HOLD nếu
  `|return| ≤ 0.005`.
- `regime`: bull nếu `price_5d_return > 0.02`, bear nếu `< -0.02`, else sideways.

## 7. Pipeline tổng quan (ngôn ngữ tự nhiên, dùng để trình bày)

Toàn hệ thống chia làm **2 phần rõ rệt**: **Phần Dự đoán** (từ tin tức → ra UP/DOWN/HOLD) và
**Phần Đánh giá** (audit lại chính dự đoán đó — có đáng tin không). Phần Đánh giá không quay
lại thay đổi prediction; nó chỉ đo lường và gắn nhãn độ tin cậy của lời giải thích. Toàn bộ là
rule-based/deterministic, không ML/LLM.

### PHẦN 1 — DỰ ĐOÁN (Prediction Pipeline)

**Bước 1: Lọc thời gian (`TemporalRetriever`)**
Vấn đề: dùng tin tức xảy ra *sau* thời điểm dự báo là "look-ahead bias" — lỗi rò rỉ dữ liệu
tương lai khiến kết quả vô nghĩa. Thuật toán: so `news_time ≤ forecast_time` (UTC hoá thống
nhất qua `TimeUtils`); tin nào vi phạm bị loại thẳng, không đi tiếp. Chỉ số:
`temporal_validity` = tỉ lệ tin hợp lệ/tổng.

**Bước 2: Trích xuất bằng chứng (`EvidenceExtractor`)**
Vấn đề: chuyển văn bản tự do thành evidence có thể tính toán (hệ thống không "đọc hiểu", chỉ
nhận diện từ khóa). Thuật toán: quét 2 từ điển từ khóa cố định (`POSITIVE_KEYWORDS`/
`NEGATIVE_KEYWORDS`) theo 2 tầng — exact substring trước, token-level (cho phép chèn từ bổ
nghĩa, gap ≤ 15 ký tự) sau; resolve overlap giữ match dài nhất. Mỗi match → 1 evidence object
(`polarity`, `expected_direction`, `support_score`, toạ độ ký tự). Không match gì → 1 evidence
neutral mặc định (không tin nào bị bỏ trống).

**Bước 3: Ra quyết định (`ForecastModel`)**
Vấn đề: tổng hợp toàn bộ evidence thành 1 dự đoán + độ tin cậy. Thuật toán voting:
```
score = số evidence UP − số evidence DOWN
prediction = UP nếu score>0, DOWN nếu score<0, HOLD nếu score=0
confidence = 0.5 + min(|score|×0.1, 0.45)      (giới hạn [0.5, 0.95])
```
Chỉ số phụ: `evidence_strength = |score|/số_evidence_có_hướng` (mức đồng thuận),
`conflict_ratio = min(pos,neg)/max(pos+neg,1)` (mức mâu thuẫn). Model lọc lại
`news_time > forecast_time` lần 2 (phòng thủ kép).

→ **Kết quả Phần 1**: `prediction`, `confidence`, rationale (template, không phải AI sinh),
danh sách evidence đã dùng vote.

### PHẦN 2 — ĐÁNH GIÁ (Faithfulness Audit Pipeline)

Trả lời: *"Model nói nó dựa vào evidence X để quyết định — có thật không, hay chỉ là lời giải
thích trang trí?"*

**Bước 4: Phân loại bằng chứng (`EvidenceSelector`) + B2 Counterevidence Coverage**
Vấn đề: 1 tin có thể có cả evidence ủng hộ lẫn phản đối prediction — cần tách riêng để các bước
sau biết "evidence nào đang được dùng làm lý do". Thuật toán: tra bảng cố định 9 ô
`(prediction, expected_direction)` → `pro_evidence`/`counterevidence`/`neutral_evidence`.
`counterevidence_ratio` cao/thấp cho biết có cherry-picking (chỉ trưng evidence có lợi) hay
không. **B2**: `counterevidence_coverage = phát hiện được/đáng lẽ có` (so với nhãn tay) — đo hệ
thống có bỏ sót/giấu bằng chứng trái chiều không.

**Bước 5: Đo "Faithful" bằng ablation (`FaithfulnessEvaluator` + `FaithfulnessMetrics`, A6)**
Vấn đề: kiểm chứng bằng thực nghiệm xóa bỏ có kiểm soát (ablation, kỹ thuật chuẩn trong XAI) —
nếu xóa đúng evidence model bảo là "lý do" mà kết quả gần như không đổi, lý do đó không thật.
3 chỉ số độc lập:
- `temporal_validity` (0/1): cited evidence có hợp lệ thời gian không — lớp phòng thủ leakage
  thứ 3.
- `evidence_support` (0–1, trung bình): cited evidence có **nhất quán logic** với prediction
  không (1.0 khớp hướng, 0.5 có bên HOLD, 0.0 ngược hướng) — phép kiểm rẻ, chạy trước ablation.
- `confidence_drop` (ablation thật): xóa hẳn `pro_evidence` đã cite, chạy lại
  `predict_without_evidence()`, đo `confidence_gốc − confidence_sau_xóa`. Drop lớn → evidence
  thật sự quan trọng; drop ≈ 0 → chỉ trang trí.

Tổng hợp: `faithfulness_score = 0.35·tv + 0.30·es + 0.35·normalized(drop)`. Verdict theo cascade
6 nhãn cố định (`decorative_explanation_risk` → `invalid_temporal_leakage` →
`unsupported_evidence` → `strong/moderate/weak_faithful_candidate`), dừng ở điều kiện đầu tiên
khớp — xem chi tiết ngưỡng ở mục 4.

**Bước 6: Sufficiency + Counterfactual (`SufficiencyEvaluator`, B1)**
Vấn đề: bổ sung 2 góc nhìn khác ablation. Thuật toán — đều chạy lại `predict()` với input biến
đổi:
- **Sufficiency**: chỉ giữ evidence đã cite, bỏ hết phần còn lại →
  `sufficiency_score = min(confidence_chỉ_cited/confidence_gốc, 1.0)` — cited có tự đủ mạnh
  không, không cần "mượn" evidence không được nhắc tới.
- **Counterfactual**: **thay** (không xóa) evidence cited bằng placeholder trung lập
  (`expected_direction=HOLD`), giữ nguyên số lượng evidence — cô lập đúng 1 biến (hướng của
  cited) →
  `counterfactual_delta = confidence_gốc − confidence_sau_trung_hoà`.

**Bước 7: Đối chiếu thị trường thực (`MarketAnalyzer`, B3)**
Vấn đề: các bước trên chỉ đánh giá nội bộ (nhất quán với evidence của chính nó) — chưa so với
thực tế bên ngoài. Thuật toán — 2 ngưỡng cố định:
- `market_consistent`: so dấu `prediction` với `next_day_return` thật, ngưỡng ±0.5% (tránh
  nhiễu nhỏ quanh 0).
- `regime`: bull/bear/sideways từ `price_5d_return`, ngưỡng ±2% — phục vụ thống kê accuracy
  theo từng chế độ thị trường.

*(`next_day_return`/`price_5d_return` là dữ liệu mô phỏng có sẵn trong `data/sample_dataset.csv`,
không phải giá thị trường thật — đúng phạm vi prototype học thuật.)*

### Sơ đồ luồng dữ liệu tổng thể

```
Tin tức thô
   │
   ▼
[1] Temporal Retriever    → lọc tin tương lai
   │
   ▼
[2] Evidence Extractor    → sinh evidence (keyword-based)
   │
   ▼
[3] Forecast Model        → PREDICTION (UP/DOWN/HOLD) + confidence   ◄── PHẦN 1 kết thúc
   │
   ├──► [4] Evidence Selector      → pro/counter/neutral, counterevidence_ratio, B2 coverage
   ├──► [5] Faithfulness Evaluator → temporal_validity, evidence_support, confidence_drop
   │                                  (ablation) → faithfulness_score + verdict
   ├──► [6] Sufficiency Evaluator  → sufficiency_score, counterfactual_delta
   └──► [7] Market Analyzer        → market_consistent, regime
                                     ◄── PHẦN 2: 4 nhánh đều xuất phát từ [3], không quay lại
                                         ảnh hưởng prediction
```

### Bảng tổng hợp chỉ số

| Chỉ số | Thuộc bước | Ý nghĩa |
|---|---|---|
| `temporal_validity` (dataset-level) | 1 | % tin không rò rỉ thời gian |
| `polarity`, `expected_direction`, `support_score` | 2 | Đặc trưng của 1 evidence |
| `score`, `prediction`, `confidence` | 3 | Kết quả dự đoán chính |
| `evidence_strength`, `conflict_ratio` | 3 | Mức đồng thuận / mâu thuẫn giữa evidence |
| `pro_evidence`/`counterevidence`/`neutral_evidence`, `counterevidence_ratio` | 4 | Cấu trúc bằng chứng theo prediction |
| `counterevidence_coverage` (B2) | 4 | Độ phủ phát hiện phản chứng so với nhãn tay |
| `temporal_validity` (per-prediction), `evidence_support`, `confidence_drop` | 5 | 3 trụ cột đo faithful |
| `faithfulness_score`, `verdict` | 5 | Điểm & nhãn tổng hợp |
| `sufficiency_score` (B1) | 6 | Evidence cited có tự đủ không |
| `counterfactual_delta` (B1) | 6 | Ảnh hưởng khi trung hoà evidence cited |
| `market_consistent`, `regime` (B3) | 7 | Đối chiếu thực tế thị trường |

---

Tất cả đều rule-based/deterministic, dùng chung `TimeUtils` (retriever.py) để parse timestamp
và `EvidenceExtractor.POSITIVE_KEYWORDS/NEGATIVE_KEYWORDS` làm nguồn polarity duy nhất — đúng
theo invariant trong CLAUDE.md.
