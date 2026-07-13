# Báo cáo Đồ án Cuối kỳ

**Môn:** Công nghệ mới
**Đề tài:** Faithful Evidence-Centric Financial News Forecasting — Agentic AI trong SDLC cho hệ thống dự báo xu hướng cổ phiếu có kiểm chứng bằng chứng

Báo cáo trình bày theo cấu trúc gợi ý tại `ChuDe1.md` §9.1 (10 mục). Toàn bộ số liệu được lấy trực tiếp từ output thật của pipeline (`python -m src.pipeline --input data/sample_dataset.csv --output-dir outputs`, xác thực lại tại thời điểm viết báo cáo: 566/566 test pass, accuracy 74% trên `outputs/prediction_results.csv`).

## Mục lục

1. [Giới thiệu bài toán và động lực](#1-giới-thiệu-bài-toán-và-động-lực)
2. [Research gap: accuracy chưa đủ, cần faithful evidence](#2-research-gap-accuracy-chưa-đủ-cần-faithful-evidence)
3. [Thiết kế Agentic SDLC và OpenSpec](#3-thiết-kế-agentic-sdlc-và-openspec)
4. [Mô tả dữ liệu](#4-mô-tả-dữ-liệu)
5. [Mô tả pipeline kỹ thuật](#5-mô-tả-pipeline-kỹ-thuật)
6. [Metric và cách đánh giá](#6-metric-và-cách-đánh-giá)
7. [Kết quả thực nghiệm và visualization](#7-kết-quả-thực-nghiệm-và-visualization)
8. [Phân tích case đúng/sai](#8-phân-tích-case-đúngsai)
9. [Limitations và hướng phát triển](#9-limitations-và-hướng-phát-triển)
10. [Phụ lục: prompt, agent trace, test cases](#10-phụ-lục-prompt-agent-trace-test-cases)

---

## 1. Giới thiệu bài toán và động lực

**Câu hỏi trung tâm:** khi một hệ thống đọc tin tức tài chính và dự báo xu hướng cổ phiếu (UP/DOWN/HOLD), evidence mà nó trích dẫn có **thật sự quyết định** prediction, hay chỉ là lời giải thích gắn vào *sau khi* đã ra quyết định?

Trong tài chính, nhiều hệ thống AI có thể đọc tin tức và dự báo cổ phiếu tăng/giảm/đi ngang, kèm theo một đoạn giải thích nghe rất hợp lý. Nhưng lời giải thích "nghe hợp lý" không đồng nghĩa với việc nó phản ánh đúng nguyên nhân mô hình ra quyết định. Đồ án xây dựng một prototype nhỏ để **kiểm chứng tính faithful** của evidence trong bài toán dự báo xu hướng cổ phiếu từ tin tức — không xây hệ thống giao dịch thật, không khuyến nghị mua/bán.

**Mục tiêu kỹ thuật cụ thể:**
- Lọc tin theo thời gian, đảm bảo không có tin tương lai lọt vào input (temporal validity).
- Trích xuất evidence có cực (positive/negative/neutral) từ tin tức bằng rule-based keyword matching.
- Dự báo UP/DOWN/HOLD minh bạch, có thể truy vết 100% về evidence — không hộp đen.
- Đo tính faithful bằng ablation (xoá evidence, xem confidence đổi bao nhiêu), sufficiency test, counterfactual perturbation, và counterevidence coverage.
- Đối chiếu với diễn biến thị trường (market consistency, regime analysis).
- Trực quan hoá toàn bộ kết quả trên dashboard, và áp dụng Agentic AI có kiểm soát của con người trong toàn bộ SDLC.

**Trọng tâm không phải là "mô hình dự báo đúng bao nhiêu %"** mà là "mô hình dự báo dựa trên bằng chứng nào, bằng chứng đó có đúng thời điểm không, và nếu bỏ bằng chứng đó thì dự báo có đổi không" — đúng theo tinh thần "Ý tưởng lớn" của `ChuDe1.md` §1.

## 2. Research gap: accuracy chưa đủ, cần faithful evidence

**Khoảng cách giữa prediction accuracy và explanation faithfulness:** một hệ thống có thể đạt accuracy cao trong khi giải thích lại không đáng tin, theo 3 kiểu lỗi mà `ChuDe1.md` §2 nêu ra làm ví dụ minh hoạ và đồ án phải chủ động phát hiện được:

| Kiểu lỗi | Ví dụ minh hoạ (`ChuDe1.md`) | Cách đồ án phát hiện |
|---|---|---|
| **Temporal leakage** — dùng tin tương lai | `forecast_time=09:00`, `news_time=15:30` cùng ngày → phải loại | `TemporalRetriever` chặn 2 lớp (retriever + forecast model), metric `temporal_validity` |
| **Evidence trang trí (decorative)** — bỏ evidence, prediction/confidence gần như không đổi | NVDA: confidence 0.88 → 0.86 khi bỏ cited evidence (drop=0.02) | `FaithfulnessEvaluator.confidence_drop` qua ablation; nhãn `faithfulness_label=LOW` khi drop thấp |
| **Bỏ qua counterevidence** — chỉ cite tin ủng hộ, phớt lờ tin trái chiều | AAPL: có tin tích cực (ra mắt sản phẩm) và tin tiêu cực (doanh số TQ giảm) cùng lúc, nếu chỉ cite tin tích cực → Counterevidence Coverage thấp | `EvidenceSelector.compute_coverage()` (B2) |

Ngược lại, khi evidence thật sự "cần thiết" (necessity cao) — ví dụ TSLA: confidence giảm từ 0.81 xuống 0.55 (drop=0.26) khi bỏ cited evidence — đó là dấu hiệu evidence **faithful**, không chỉ là rationale hậu nghiệm.

**Research gap mà đồ án lấp:** phần lớn hệ thống dự báo tài chính từ tin tức chỉ báo cáo accuracy/confusion matrix. Đồ án bổ sung một tầng đánh giá thứ hai — **faithfulness evaluation** — độc lập với accuracy, gồm 3 metric bắt buộc (temporal validity, evidence support, confidence drop) và 3 kỹ thuật nâng cao (sufficiency + counterfactual perturbation ở B1, counterevidence coverage ở B2, market consistency + regime ở B3). Kết quả thực nghiệm (§7) cho thấy rõ gap này: accuracy tổng thể 74% nhưng recall riêng nhãn DOWN chỉ 34.4% — và nguyên nhân *chính đáng* (không phải lỗi thuật toán) chỉ lộ ra khi nhìn vào temporal validity, không nhìn thấy được nếu chỉ nhìn accuracy (phân tích chi tiết ở §8).

## 3. Thiết kế Agentic SDLC và OpenSpec

### 3.1. Khung triết lý: "AI-Assisted, Human-Controlled"

Dự án không để AI agent tự quyết định. Mọi bước đều có checkpoint để con người review và approve:

```
AI Agent đề xuất → Con người review → Approve/Reject → Implement → Test → Deploy
```

**3 vai trò cố định** xuyên suốt dự án (trích `openspec/changes/phase-b4-agentic-sdlc-maturity/reflection.md`):

| Role | Nhiệm vụ | Ví dụ cụ thể đã làm trong dự án |
|---|---|---|
| **Research Agent** | Phân tích gap, viết `proposal.md` + `design.md`, đề xuất interface/schema/ngưỡng | Phát hiện gap thiếu counterevidence coverage (B2)/sufficiency (B1)/market consistency (B3); đề xuất ngưỡng `±0.005`, `±0.02`; thiết kế schema CSV (10 cột `sufficiency_results.csv`, 9 cột `market_consistency_results.csv`) |
| **Coding Agent** | Implement theo spec đã approve, tích hợp pipeline & dashboard | Viết `sufficiency_evaluator.py`, `market_analyzer.py`, `agent_trace.py`; tích hợp vào `pipeline.py`; thêm tab dashboard |
| **Testing/Review Agent** | Sinh test theo spec scenario, chạy `pytest`, review edge case | Viết 12 test cho B1, 18 test parametrize cho B3; phát hiện bug `sufficiency_score` phải là `0.0` (không phải `0.5/original`) khi `cited_evidence_ids` rỗng → báo cáo → Coding Agent sửa |

**Quy trình lệnh cụ thể:** `/opsx:propose` → người dùng đọc và review spec → người dùng xác nhận ("hãy bắt đầu") → `/opsx:apply`. Trích nguyên văn `reflection.md`: *"Con người không approve thì AI agent không tiến hành implement."*

**4 Quality Gate** áp dụng cho mọi OpenSpec change: (1) Spec review bởi con người, (2) `pytest tests/ -q` phải 0 failure, (3) `python -m src.pipeline` chạy smoke-test không lỗi, (4) review thủ công output CSV.

### 3.2. Cấu trúc OpenSpec trong repo

```
openspec/changes/
  temporal-retriever/                          proposal, design, tasks, specs/…
  evidence-extractor/
  evidence-selector/
  forecast-model-basic/
  faithfulness-evaluator/
  visualization-dashboard/
  phase-b1-sufficiency-counterfactual/
  phase-b2-counterevidence-coverage/
  phase-b3-market-consistency-regime/
  phase-b4-agentic-sdlc-maturity/
  integrate-end-to-end-forecasting-pipeline/
  archive/
    2026-06-21-project-scaffold/
    2026-06-25-enrich-evidence-keywords-v2/
    2026-06-25-enrich-evidence-keywords-v3/
```

**11 change đang active**, mỗi change đủ 4 thành phần (`proposal.md`, `design.md`, `tasks.md`, `specs/<domain>/spec.md`); **3 change đã archive**. Mỗi spec nêu rõ input/output, chức năng, acceptance criteria theo định dạng Given/When/Then (ví dụ minh hoạ §10).

### 3.3. Hai giai đoạn dùng AI khác nhau, và lý do

**Giai đoạn "trước" (21/06 → 27/06):** mọi capability — kể cả B1–B4 nâng cao — đi trọn chu trình `proposal → design → tasks → apply` **trước khi** bắt đầu thay đổi kế tiếp, mỗi bước có commit riêng mô tả rõ ràng (`10c521e update spec temporal-retriever...`, `d6dd41f Create spec for evidence-extractor...`, v.v.). `outputs/run_log.json` có 12 entry, toàn bộ trong ngày 27/06, chạy tuần tự B2→B1→B3→B4, mỗi phase đúng 3 bước Research→Coding→Testing.

- *Ưu điểm:* truy vết gần như 1-1 giữa change và commit; quality gate mịn (pytest chạy sau mỗi thay đổi nhỏ, số test tăng dần 483→497→535→552); rủi ro sai kiến trúc gần như bằng 0 vì review spec trước khi có code.
- *Nhược điểm:* overhead cao cho thay đổi nhỏ; không tự nhiên cover thay đổi xuyên nhiều module cùng lúc.

**Giai đoạn "sau" (sau khi B-track hoàn tất):** các thay đổi có xu hướng gộp nhiều capability vào một bước, không còn OpenSpec change hay `run_log.json` entry tương ứng 1:1. Ví dụ rõ nhất: commit refactor OOP gần nhất (chạm toàn bộ 7 stage class + dashboard trong một lần) không có `proposal.md`/`design.md` riêng, không có entry mới trong `run_log.json`, nhưng **vẫn được** verify bằng toàn bộ 552 test trước khi chấp nhận.

- *Ưu điểm:* nhanh hơn nhiều cho thay đổi cross-cutting; giảm boilerplate cho thay đổi không đổi hành vi (refactor cấu trúc); tận dụng ngữ cảnh rộng của AI agent khi đã hiểu toàn bộ codebase.
- *Nhược điểm (quan trọng nhất — trả lời câu hỏi "kiểm soát lỗi AI như thế nào?" ở `ChuDe1.md` §11.3):* mất tính hạt mịn của quality gate (1 commit lớn = review 1 lần cho nhiều thay đổi); mất khả năng truy vết chi tiết; `run_log.json` **ngừng cập nhật** sau B4 dù dự án tiếp tục phát triển — accountability trace không bao phủ giai đoạn này; an toàn của giai đoạn này phụ thuộc hoàn toàn vào lưới test tích luỹ được từ giai đoạn trước.

**Kết luận:** đây không phải AI "tự tin hơn" theo thời gian, mà là sự chuyển đổi hợp lý theo mức độ ổn định của codebase — mức độ kiểm soát cần thiết tỉ lệ nghịch với độ phủ test/độ ổn định của codebase, với điều kiện con người vẫn giữ gate cuối cùng (đọc diff, chạy test đầy đủ trước khi chấp nhận).

### 3.4. Ranh giới kiểm soát cứng (Boundaries)

`AGENTS.md`/`CLAUDE.md` mục "Boundaries": AI **phải hỏi trước** khi thêm dữ liệu tài chính thật, model ML/NLP nâng cao, external API, crawler, database, authentication, hoặc thay đổi kiến trúc lớn — control mang tính quy tắc cứng, áp dụng cho toàn bộ dự án, không chỉ giai đoạn đầu.

## 4. Mô tả dữ liệu

**Nguồn:** `data/sample_dataset.csv` — dữ liệu **mô phỏng** (không phải dữ liệu thị trường thật), đúng tinh thần A2 của `ChuDe1.md`.

| Thuộc tính | Giá trị |
|---|---|
| Số dòng | **144** (145 dòng file gồm header) |
| Số group `(ticker, forecast_time)` | **100** |
| Cột bắt buộc | `news_id`, `ticker`, `forecast_time`, `news_time`, `news_text`, `label` (UP/DOWN/HOLD) |
| Cột bổ sung cho B3 | `next_day_return`, `price_5d_return` (synthetic, sinh bằng `hash(ticker + forecast_time) % 1000` để đảm bảo determinism) |
| Số dòng vi phạm temporal (news_time > forecast_time) | **21/144** — cố tình đưa vào để test temporal leakage detection |
| Timestamp format | ISO-8601, naive = UTC (quy ước tài chính) |

**Vì sao có cột synthetic market data:** `openspec/changes/phase-b3-market-consistency-regime/design.md` ghi rõ: *"đây là academic prototype, dữ liệu next_day_return/price_5d_return không tương quan thật với prediction — label rõ 'synthetic' trong dashboard"* để tránh gây hiểu nhầm là dữ liệu thị trường thật.

Dataset được thiết kế có chủ ý để bao phủ cả 4 tình huống minh hoạ trong `ChuDe1.md` §2: evidence faithful, evidence trang trí, temporal leakage, và counterevidence — phục vụ trực tiếp cho việc đo faithfulness ở các mục sau.

## 5. Mô tả pipeline kỹ thuật

### 5.1. Kiến trúc tổng quan

```
data/sample_dataset.csv (144 rows)
        │
        ▼
[Group by (ticker, forecast_time)] → 100 groups
        │
        ▼
Stage 1  TemporalRetriever.retrieve()          src/retriever.py
        │  valid_news / invalid_future_news / temporal_validity
        ▼
Stage 2  EvidenceExtractor.extract_batch()     src/evidence_extractor.py
        │  evidence: evidence_text, polarity, expected_direction
        ▼
Stage 3  ForecastModel.predict()               src/forecast_model.py
        │  prediction, confidence, score, rationale
        ▼
Stage 4  EvidenceSelector.select_batch()       src/evidence_selector.py
        │  pro_evidence / counterevidence / neutral_evidence
        ├──► compute_coverage()  → counterevidence_coverage      (B2)
        ▼
Stage 5  FaithfulnessEvaluator.evaluate()      src/faithfulness_evaluator.py
        │  temporal_validity, evidence_support, confidence_drop
        ├──► SufficiencyEvaluator.evaluate()   → sufficiency_score, counterfactual_delta   (B1)
        ├──► MarketAnalyzer.analyze()          → market_consistent, regime                (B3)
        ▼
outputs/  prediction_results.csv · evidence_results.csv · faithfulness_results.csv
          sufficiency_results.csv · market_consistency_results.csv · temporal_leakage_results.csv
        │
        ▼
src/dashboard/app.py  (Streamlit, read-only, 9 tab: Live Demo + 8 Analytics — §7.3)
```

**Orchestrator:** `PipelineRunner.run()` (`src/pipeline.py`) compose instance của từng stage class, group theo `(ticker, forecast_time)`, tính `faithfulness_label` (HIGH/MEDIUM/LOW) tại **một điểm duy nhất** ở biên pipeline. B4 (agent trace) nằm ngoài `PipelineRunner`, chỉ được dashboard đọc trực tiếp.

**Entry point:** `python -m src.pipeline --input data/sample_dataset.csv --output-dir outputs`

### 5.2. Từng stage — thuật toán và lý do thiết kế

**(1) Temporal Retriever — `src/retriever.py`.** Chặn temporal leakage bằng so sánh timestamp thuần túy:
```
news_time ≤ forecast_time  → valid_news
news_time >  forecast_time → invalid_future_news   (strict inequality — bằng nhau vẫn hợp lệ)
news_time không parse được → errors (không abort batch)
forecast_time không parse được → raise TemporalValidationError (abort)
temporal_validity = valid_count / total_count
```
Rule-based thay vì heuristic phức tạp vì *"a binary classification by timestamp... a simple `datetime.parse` + comparison is provably correct"* (design.md). `news_time` hỏng → đẩy vào `errors` (không abort cả batch), nhưng `forecast_time` hỏng → phải raise — bất đối xứng có chủ ý để tránh *"silently misleading, could feed the model with bogus evidence."* Naive timestamp = UTC, không sort lại vì *"sorting adds nondeterminism across equal timestamps."*

**(2) Evidence Extractor — `src/evidence_extractor.py`.** Trích evidence phrase có cực bằng keyword matching (3 lớp: V1 baseline, V2 mở rộng, V3 tín hiệu nhẹ — tổng 34 positive + 46 negative keyword). Thuật toán: exact substring match ưu tiên → token-level fallback (gap ≤15 ký tự giữa các từ trong keyword đa từ, cho phép chèn 1 từ bổ nghĩa như "iPhone") → resolve overlap bằng cách giữ match dài nhất. Dictionary cứng thay vì lexicon học được vì *"deterministic, auditable... a learned lexicon would require training data, a model artifact, and version pinning."*

**(3) Forecast Model — `src/forecast_model.py`.** Vote rule-based, minh bạch 100%:
```
score = positive_count − negative_count
prediction = UP (score>0) / DOWN (score<0) / HOLD (score=0, kể cả không có evidence)
confidence = 0.5                                          nếu không có directional evidence
           = clamp(0.5 + min(|score|×0.1, 0.45), 0.5, 0.95) ngược lại
```
Không dùng `|score|/total_evidence` vì sẽ overstate confidence khi chỉ có 1 evidence (`abs(1)/1=1.0`). `predict_without_evidence()` tách riêng khỏi `predict()` nhưng cùng gọi `_predict_core` để không drift — hàm này chính là cơ chế ablation dùng ở Faithfulness Evaluator.

**(4) Evidence Selector — `src/evidence_selector.py` (B2).** Phân loại pro/counter/neutral bằng bảng tra cứu cố định `CLASSIFICATION_TABLE` (9 ô, ví dụ UP+UP=pro, UP+DOWN=counter, HOLD+UP/DOWN=counter). `compute_coverage()`: `expected_labels` suy ra trực tiếp từ chính bảng phân loại (không annotate tay, vì dataset nhỏ không có ground-truth), `counterevidence_coverage = detected/available`.

**(5) Faithfulness Evaluator — `src/faithfulness_evaluator.py` (A6).** Công thức chi tiết ở §6.

**(6) Sufficiency Evaluator — `src/sufficiency_evaluator.py` (B1).** Nhận `cited_evidence_ids` (không nhận trực tiếp `selector_result`) để giữ độc lập khỏi `EvidenceSelector` — tránh coupling hai module.

**(7) Market Analyzer — `src/market_analyzer.py` (B3).** Hàm thuần túy, không I/O, so `next_day_return`/`price_5d_return` với threshold cố định.

**(8) Agentic SDLC Trace — `src/agent_trace.py` (B4).** Module độc lập với pipeline dự báo, đọc/ghi `outputs/run_log.json`, phục vụ audit quy trình phát triển (chi tiết ở §3, §10).

## 6. Metric và cách đánh giá

### 6.1. Faithfulness metrics cơ bản (A6)

```
temporal_validity  = 1.0 nếu mọi cited evidence có news_time ≤ forecast_time (rỗng → 1.0 vacuous)
                    = 0.0 nếu có ít nhất 1 cited evidence future

evidence_support    = mean(support_score mỗi cited item)
  support_score:  1.0 nếu expected_direction == prediction
                  0.5 nếu 1 trong 2 bên là HOLD
                  0.0 nếu trái ngược hoàn toàn

confidence_drop     = original_confidence − confidence_after_removal
  (confidence_after_removal lấy từ ForecastModel.predict_without_evidence — KHÔNG re-implement voting logic,
   để tránh drift giữa evaluator và model)
```

**Nhãn faithfulness_label** (tính tại `PipelineRunner._faithfulness_label()`, một nguồn sự thật duy nhất):
```
HIGH   nếu temporal_validity ≥ 1.0  và  confidence_drop ≥ 0.20
MEDIUM nếu temporal_validity ≥ 1.0  và  confidence_drop ≥ 0.05
LOW    trường hợp còn lại   (temporal validity fail luôn override, kể cả drop cao)
```

Mặc định chỉ xoá `pro_evidence` (không xoá cả counter) vì *"removing only the supporting evidence is the strongest test... removing all cited evidence would also remove counter-evidence, which would skew the post-removal prediction upward by default."*

Composite `faithfulness_score` chỉ dùng cho dashboard (tự ghi rõ trong design.md là *"a V1 dashboard heuristic, not a final scientific metric"*, `confidence_drop` mới là *"the primary signal"*):
```
faithfulness_score = 0.35 × temporal_validity + 0.30 × evidence_support + 0.35 × min(max(confidence_drop,0)/0.30, 1.0)
```

### 6.2. Sufficiency + Counterfactual Perturbation (B1)

```
sufficiency_score = min(sufficiency_confidence / original_confidence, 1.0)   nếu original_confidence > 0
                   = 0.0   nếu cited_evidence_ids rỗng hoặc original_confidence ≤ 0

counterfactual_delta = original_confidence − counterfactual_confidence
  (counterfactual: thay cited evidence bằng placeholder neutral, expected_direction=HOLD, support_score=0.5)
```

### 6.3. Counterevidence Coverage (B2)

```
counterevidence_coverage = counterevidence_detected / counterevidence_available
```
`coverage < 1.0` xảy ra khi `top_k_counter` (mặc định 3) giới hạn số evidence hiển thị nhưng số counter candidate thật sự nhiều hơn 3 — *"đây là signal đúng: có nhiều bằng chứng trái chiều nhưng chỉ một phần được đưa vào report."*

### 6.4. Market Consistency + Regime (B3)

```
RETURN_THRESHOLD = 0.005 (0.5%)     UP consistent  ↔ next_day_return > +0.5%
                                     DOWN consistent ↔ next_day_return < -0.5%
                                     HOLD consistent ↔ |next_day_return| ≤ 0.5%
REGIME_THRESHOLD = 0.02  (2%)       bull ↔ price_5d_return > +2%
                                     bear ↔ price_5d_return < -2%
                                     sideways ↔ còn lại
```
0.5% được chọn để *"loại bỏ noise nhỏ trong ngày — mức thực tiễn phổ biến trong financial NLP"*; 2% cho regime tương đương *"significant trend trong 5 ngày"* (design.md).

## 7. Kết quả thực nghiệm và visualization

### 7.1. Forecast Model — Accuracy & Confusion Matrix

**Accuracy tổng thể: 74%** (74/100 group đúng label, xác nhận trực tiếp từ `outputs/prediction_results.csv`).

```
              Predicted: DOWN  HOLD   UP
Actual UP  :             0     4    37   → recall 90.2%
Actual DOWN:            11    21     0   → recall 34.4%  ← điểm yếu lớn nhất
Actual HOLD:             1    26     0   → recall 96.3%
```

Mô hình mạnh với UP và HOLD nhưng yếu với DOWN — nguyên nhân được phân tích ở §8.

### 7.2. Faithfulness & các metric nâng cao

| Metric | Kết quả |
|---|---|
| `temporal_validity` (mean) | **1.00** — Retriever đã lọc sạch tin tương lai từ trước khi tới Faithfulness Evaluator |
| `evidence_support` (mean) | **0.932** |
| `confidence_drop` (mean / max) | **0.189 / 0.500** |
| Phân bố `faithfulness_label` | **49 group HIGH / 51 group LOW** (0 MEDIUM trong lần chạy này) |
| `sufficiency_score` (mean) | **0.790** — 79/100 group đạt 1.0 (cited evidence đủ và cần thiết), 21/100 = 0.0 (trùng với 21 group bị lọc sạch do leakage) |
| `counterfactual_delta` (mean) | **0.056** |
| Pro / Counter evidence | **107 / 23** — 22/100 group phát hiện được counterevidence |
| `counterevidence_coverage` (mean) | **0.22** |
| Market consistent rate | **27%** — phản ánh đúng bản chất dữ liệu mô phỏng ngẫu nhiên, không tương quan thật |
| Regime | sideways 52 / bull 26 / bear 22 group |

**Ghi chú cập nhật (`dashboard-live-demo-flow`)**: `confidence_drop` mean giảm từ 0.301 xuống **0.189** (max từ 0.700 xuống **0.500**) sau khi thêm `class_confidences` (vote breakdown UP/DOWN/HOLD) vào `ForecastModel`. Đây không phải regression — `FaithfulnessMetrics.confidence_after_removal_for_original_class` vốn đã được thiết kế để ưu tiên đọc `reduced_class_confidences[original_prediction]` khi có, thay vì phạt cứng confidence = 0.0 mỗi khi ablation làm đổi hướng dự đoán; trước đây field này chưa từng tồn tại nên nhánh chính xác hơn không bao giờ chạy. Số liệu mới phản ánh đúng hơn confidence thật của lớp gốc sau khi bỏ evidence, nên nhìn chung `confidence_drop` giảm (điểm phạt cứng 0.0 trước đây thổi phồng drop). Đáng chú ý: **phân bố `faithfulness_label` không đổi (vẫn 49 HIGH / 51 LOW)** — ngưỡng HIGH (`drop ≥ 0.20`) vẫn đúng cho đúng 49 group dù giá trị drop trung bình giảm, cho thấy các group HIGH ban đầu có drop đủ lớn để không bị ảnh hưởng bởi việc tính lại.

### 7.3. Dashboard Visualization (A7)

`streamlit run src/dashboard/app.py` — đọc trực tiếp 6 CSV + `run_log.json`, **không mutate** `outputs/` (có test snapshot xác nhận), **không gọi lại pipeline**. Yêu cầu A7 chỉ đòi ≥4 bảng/hình — dashboard triển khai **9 tab** (1 Live Demo + 8 Analytics, `dashboard-live-demo-flow` change):

| # | Tab | Nội dung |
|---|---|---|
| 0 | 🎬 Live Demo | Chọn 1 ticker + 1 forecast date (single-select, độc lập sidebar) → tin hợp lệ → prediction kèm vote breakdown UP/DOWN/HOLD (`class_confidences`) → cited evidence/rationale → toggle "Remove cited evidence" so confidence trước/sau → kết luận faithful. Đúng luồng 10 bước ở `ChuDe1.md` §11.1. Case không có tin hợp lệ hiện banner giải thích thay vì bảng trống. |
| 1 | 📊 Analytics · Overview | Metric card (accuracy, avg confidence, avg confidence_drop, temporal validity, HOLD share); biểu đồ prediction distribution; accuracy theo từng ticker |
| 2 | 📊 Analytics · Evidence | Bảng 130 evidence row, filter theo polarity/direction/role/cited, tải CSV |
| 3 | 📊 Analytics · Confidence Drop | Scatter `confidence_drop` theo sample, tô màu theo faithfulness level; bucket count HIGH/MEDIUM/LOW |
| 4 | 📊 Analytics · Temporal Leakage | Banner mức độ nghiêm trọng; bảng 21 leakage case theo `leakage_minutes` |
| 5 | 📊 Analytics · Case Detail | Chọn 1 `sample_id`: prediction, confidence trước/sau khi bỏ evidence, cited evidence, diễn giải bằng ngôn ngữ tự nhiên |
| 6 | 📊 Analytics · Sufficiency | Avg sufficiency_score, avg counterfactual_delta, bảng đầy đủ (B1) |
| 7 | 📊 Analytics · Market Consistency | Consistency rate tổng, accuracy theo regime, bảng per-sample (B3) |
| 8 | 📊 Analytics · Agentic SDLC | Tổng số run, quality-gate pass rate, human-acceptance rate, bảng trace log đầy đủ, reflection (B4) |

8 tab Analytics gated sau bộ lọc sidebar (bấm "Apply filters"); tab Live Demo luôn hoạt động ngay khi mở dashboard, không phụ thuộc sidebar.

`charts.py` là các hàm Plotly thuần (không import Streamlit) — test được độc lập, deterministic với color map cố định (`FAITHFULNESS_COLOR_MAP`, `PREDICTION_COLOR_MAP`, `LEAKAGE_SEVERITY_COLOR_MAP`).

## 8. Phân tích case đúng/sai

**Case đúng — evidence faithful, có phát hiện counterevidence (AAPL 2025-03-19):**
```
Valid news: "Apple services revenue reaches a record level"                → UP  (pro)
            "Apple reports stronger than expected unit deliveries"        → UP  (pro)
            "Apple cuts guidance on wearables segment..."                 → DOWN (counter)
score = 2 − 1 = 1 → prediction UP ✓ (đúng label)
counterevidence_detected = True, counterevidence_coverage = 1.00
```

**Case sai — do rule-based extraction bỏ sót keyword (AAPL 2025-04-04, label=DOWN, prediction=HOLD):**
```
News: "Apple says supply chain conditions are normal after latest audit"
→ không khớp keyword nào trong dictionary → evidence rỗng → score=0 → HOLD ✗
```
Đây là limitation của keyword matching (L1, §9), không phải lỗi logic.

**Case sai — do temporal leakage lọc mất evidence quan trọng (AAPL 2025-03-25, label=DOWN, prediction=HOLD):**
```
News gốc: "Apple supplier warns of softer iPhone component orders"
  news_time = 11:15 > forecast_time = 09:00 → LEAKAGE → bị lọc bởi Retriever
News còn hợp lệ: 1 DOWN + 1 UP (counter) → score = 0 → HOLD ✗ (label=DOWN)
```
Prediction sai **vì đúng nguyên tắc** — hệ thống thà bỏ evidence tương lai còn hơn leak dữ liệu, đánh đổi accuracy lấy temporal validity. Đây chính là lý do recall của nhãn DOWN thấp (34.4%, §7.1): nhiều group có label=DOWN nhưng tin tức tiêu cực duy nhất lại rơi vào `invalid_future_news`, bị Retriever lọc sạch trước khi tới Forecast Model.

## 9. Limitations và hướng phát triển

### 9.1. Limitations kỹ thuật

| # | Limitation | Ghi chú |
|---|---|---|
| L1 | Keyword matching đơn giản | False positive/negative với tin mỉa mai, đa nghĩa, paraphrase ngoài dictionary (vd. "topped estimates" không khớp) |
| L2 | Vote model trọng số đều | Không phân biệt keyword mạnh/yếu, không có recency weighting; confidence bão hoà ở `\|score\|=5` |
| L3 | Dữ liệu thị trường mô phỏng | `next_day_return`/`price_5d_return` sinh bằng hash — không tương quan thật, market consistency 27% chỉ có ý nghĩa calibration khi dùng với dữ liệu thật |
| L4 | Counterevidence coverage thấp (22%) | 78% group chỉ có evidence một chiều — do đặc điểm dataset, không phải bug |
| L5 | Không NLP nâng cao | Không FinBERT/GPT/transformer — toàn bộ deterministic, rule-based, không học từ dữ liệu |

### 9.2. Limitation quy trình phát triển AI

`run_log.json` chỉ ghi 12 entry cho B1–B4, không có entry nào cho A-track (dù A-track vẫn có kỷ luật commit tương đương qua OpenSpec) và không có entry nào cho giai đoạn refactor cuối kỳ (§3.3) — accountability trace hiện tại **không bao phủ toàn bộ lịch sử dự án**.

### 9.3. Hướng phát triển

- Mở rộng trace log (`run_log.json`) bao phủ toàn bộ lịch sử, không chỉ giai đoạn B-track, để accountability nhất quán qua mọi giai đoạn.
- Thay dictionary keyword cứng bằng lexicon có trọng số/calibrated confidence (đã được `support_score` chuẩn bị sẵn làm điểm mở rộng — *"future versions can replace this with a calibrated score without changing the field name"*).
- Thêm recency weighting và trọng số keyword thay vì vote đều (giải quyết L2).
- Nếu dùng dữ liệu thị trường thật (C1) thì market consistency (B3) mới có ý nghĩa thống kê thật sự, không còn là synthetic-only.
- Cân nhắc dùng model NLP nâng cao (FinBERT) cho C2 để so sánh với baseline rule-based hiện tại, đúng tinh thần "Điểm cộng" của `ChuDe1.md` §7 — hiện đồ án **không claim** phần này vì toàn bộ dữ liệu là mô phỏng và toàn bộ mô hình là rule-based.

## 10. Phụ lục: prompt, agent trace, test cases

### 10.1. Đối chiếu rubric (`ChuDe1.md` §10) với triển khai

| Mục | Yêu cầu | Minh chứng |
|---|---|---|
| A1 (1.0đ) | OpenSpec đủ 4 file, mô tả agent role | 11 change active + 3 archive trong `openspec/changes/`; vai trò agent ở §3 |
| A2 (1.0đ) | Dataset ≥30 dòng, đủ cột, có tin vi phạm thời gian | `data/sample_dataset.csv`: 144 dòng, 100 group, 21 dòng leakage (§4) |
| A3 (1.0đ) | Temporal Retriever + test leakage | `src/retriever.py`, `tests/test_temporal_retriever.py` (22 test) |
| A4 (1.0đ) | Evidence extraction + phân loại | `src/evidence_extractor.py`, `samples/evidence_extractor/` |
| A5 (1.0đ) | Prediction + confidence + accuracy/confusion matrix | `src/forecast_model.py`: accuracy 74% (§7.1) |
| A6 (1.0đ) | 3 metric faithfulness + bảng kết quả | `src/faithfulness_evaluator.py`, `outputs/faithfulness_results.csv` (100 dòng) |
| A7 (1.0đ) | Dashboard ≥4 bảng/hình + báo cáo | `src/dashboard/app.py` — 9 tab: Live Demo + 8 Analytics (§7.3) |
| B1 (0.75đ) | Sufficiency + Counterfactual | `src/sufficiency_evaluator.py` (§6.2) |
| B2 (0.75đ) | Counterevidence coverage | `src/evidence_selector.py::compute_coverage` (§6.3) |
| B3 (0.75đ) | Market consistency + regime | `src/market_analyzer.py` (§6.4) |
| B4 (0.75đ) | ≥3 agent role, trace log, quality gate, reflection | `src/agent_trace.py`, `outputs/run_log.json` (12 entry), `reflection.md` (§3, §10.3) |

**Tự đánh giá theo khung `ChuDe1.md` §10.1:** dự án có đủ sufficiency test (B1), counterevidence coverage (B2), cảnh báo temporal leakage rõ ràng, dashboard 9 tab (Live Demo + Analytics), agent trace log — nằm ở khung **8.0–9.0**. Dự án **không claim** phần điểm cộng C1/C2 vì toàn bộ dữ liệu là mô phỏng, toàn bộ mô hình là rule-based, không dùng GPU/dữ liệu thật.

### 10.2. Ví dụ user story / acceptance criteria (theo mẫu `ChuDe1.md` §4.2)

```
User story:
Là một nhà phân tích tài chính,
tôi muốn xem evidence nào khiến mô hình dự báo cổ phiếu giảm,
để biết dự báo đó có đáng tin hay không.

Acceptance criteria:
Given một prediction DOWN,
When người dùng mở dashboard (tab Case Detail),
Then hệ thống phải hiển thị ít nhất 1 evidence ủng hộ DOWN,
And hiển thị thời gian xuất bản của evidence,
And cảnh báo nếu evidence xuất hiện sau thời điểm dự báo (tab Temporal Leakage).
```

### 10.3. Agent trace log — ví dụ entry thật từ `outputs/run_log.json`

```json
{
  "run_id": "R001",
  "timestamp": "2026-06-27T08:00:00",
  "agent_role": "Research Agent",
  "task": "Analyze faithfulness metric gaps; propose B2 counterevidence coverage",
  "input": "src/evidence_selector.py, src/faithfulness_evaluator.py, openspec/",
  "output": "openspec/changes/phase-b2-counterevidence-coverage/proposal.md + design.md",
  "human_review": "accepted",
  "quality_gate": "passed",
  "notes": "User reviewed spec and approved before implementation"
}
```
File có 12 entry tổng cộng, phủ B1–B4, mỗi entry đều có cả `human_review` và `quality_gate` — hai trường tách biệt có chủ ý, nhấn mạnh: AI có thể pass test nhưng vẫn cần con người approve riêng, hai gate không thể thay thế nhau. `summarize_trace()` (`src/agent_trace.py`) tính `pass_rate`, đếm theo role, `human_accepted/rejected` — hiển thị trực tiếp ở dashboard tab "Agentic SDLC".

**Minh chứng con người sửa quyết định của AI:** case `sufficiency_score` khi `cited_evidence_ids` rỗng — Testing Agent phát hiện kết quả AI implement lần đầu chưa khớp spec; giá trị đúng phải là `0.0` (chứ không phải `0.5/original_confidence`) là domain judgment do con người/spec quyết định, không phải AI tự chọn (trích `reflection.md`, bài học #3).

### 10.4. Test cases — tổng quan

**566/566 test pass** (`pytest tests/ -q`), trải trên 18 file test:

```
test_agent_trace.py            test_dashboard_app.py          test_dashboard_charts.py
test_dashboard_components.py   test_dashboard_data_loader.py  test_dashboard_defensive.py
test_dashboard_metrics.py      test_dashboard_validators.py   test_evidence_extractor.py
test_evidence_selector.py      test_faithfulness_evaluator.py test_faithfulness_metrics.py
test_forecast_model.py         test_market_analyzer.py        test_pipeline.py
test_scaffold.py               test_sufficiency_evaluator.py  test_temporal_retriever.py
test_temporal_leakage.py
```

Ví dụ test case minh hoạ temporal leakage (`tests/test_temporal_retriever.py`):

```python
def test_news_at_exactly_forecast_time_is_valid() -> None: ...   # boundary: bằng nhau vẫn hợp lệ
def test_news_one_second_in_the_future_is_invalid() -> None: ... # boundary: 1 giây cũng bị loại
def test_news_six_hours_in_the_future_is_invalid() -> None: ...
def test_malformed_news_time_populates_errors_list() -> None: ...   # lỗi parse → errors, không abort batch
def test_malformed_forecast_time_raises_temporal_validation_error() -> None: ...  # lỗi forecast_time → abort
def test_identical_requests_produce_identical_responses() -> None: ...  # determinism
```

Testing Agent viết test **từ spec scenario** (không chỉ test cú pháp) — ví dụ test bẫy lỗi domain-logic thật sự đã phát hiện bug: `sufficiency_score` phải bằng `0.0` khi `cited_evidence_ids` rỗng, không phải `0.5/original_confidence` như implementation đầu tiên của Coding Agent (`tests/test_sufficiency_evaluator.py`).

### 10.5. Trả lời nhanh các câu hỏi phản biện dự kiến (`ChuDe1.md` §11.3)

| Câu hỏi phản biện | Trả lời ngắn |
|---|---|
| "AI agent đã giúp nhóm ở bước nào?" | Cả 6 giai đoạn SDLC (spec → design → code → test → eval → visualize) — 3 role cụ thể ở §3.1 |
| "Nhóm đã kiểm soát lỗi của AI agent như thế nào?" | 4 quality gate cố định (§3.1) + ví dụ AI làm sai bị Testing Agent bắt lỗi (§10.3, case `sufficiency_score`) |
| "Nếu bỏ evidence mà prediction không đổi thì kết luận gì?" | `confidence_drop` thấp/không đổi → `faithfulness_label=LOW` → evidence được cite chỉ mang tính trang trí (§6.1, §2) |
| "Làm sao biết hệ thống không dùng tin tương lai?" | `temporal_validity` bất khả xâm phạm, kiểm tra 2 lớp (Retriever + Forecast Model) — mean 1.00 trên toàn dataset (§5.2, §7.2) |
| "Counterevidence là gì? Nhóm có phát hiện được không?" | Có — `EvidenceSelector` (B2): 22/100 group phát hiện, coverage trung bình 0.22 (§6.3, §7.2) |
| "Accuracy cao nhưng faithfulness thấp thì có nên tin mô hình không?" | Không — đây chính là research gap của đồ án (§2); 49/100 group HIGH nhưng 51/100 group LOW dù accuracy tổng thể 74% |
