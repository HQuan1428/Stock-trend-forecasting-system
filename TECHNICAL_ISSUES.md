# Vấn đề kỹ thuật đã giải quyết (theo từng stage)

Mỗi stage trong chuỗi 9 stage (`ingest → retriever → evidence_extractor → forecast_model → evidence_selector → faithfulness_evaluator → sufficiency_evaluator → market_analyzer → export_csv`) có bài toán kỹ thuật riêng — không phải vấn đề hạ tầng/triển khai (CLI, schema validator, dashboard cache...) mà là vấn đề **thiết kế thuật toán bên trong stage đó**: dữ liệu mơ hồ phải xử lý sao, công thức chọn thế nào, ranh giới trách nhiệm giữa các stage đặt ở đâu. Nguồn: `openspec/changes/<stage>/design.md` (mục Decisions/Risks), verify lại bằng cách chạy pipeline thật.

---

## Stage: Temporal Retriever (A3)

### Vấn đề 1 — Tin tương lai lọt vào dự báo làm hỏng toàn bộ phép đo faithfulness
Forecasting từ tin tức dễ dính temporal leakage: dùng tin phát hành *sau* forecast_time để dự báo tại forecast_time → accuracy/explainability giả, và với hệ thống đo faithfulness thì phép đo trở nên vô nghĩa.

**Giải pháp kỹ thuật**: phân loại nhị phân theo timestamp — `news_time <= forecast_time` → `valid_news`, ngược lại → `invalid_future_news`. Không drop tin tương lai, giữ lại để audit. `Forecast Model` (stage sau) lọc lại lần 2 độc lập (`TEMPORAL_LEAKAGE_BLOCKED` warning) — defense in depth cho trường hợp dữ liệu trung gian bị chỉnh sửa.

### Vấn đề 2 — `news_time` hỏng ở một dòng không được phép làm sập cả batch, nhưng `forecast_time` hỏng thì phải chặn
Hai loại lỗi input cần xử lý khác nhau: một dòng tin lỗi timestamp là chuyện thường (dữ liệu ngoài đời), nhưng nếu không biết `forecast_time` thì *không thể* xác định leakage — im lặng coi là "quá khứ xa" sẽ đưa evidence rác vào model.

**Giải pháp kỹ thuật**: bất đối xứng có chủ ý — `news_time` không parse được → đưa vào `errors`, tiếp tục xử lý phần còn lại của batch; `forecast_time` không parse được → raise `TemporalValidationError`, dừng hẳn sample đó. `temporal_validity = valid_count / total_count` tính trên **toàn bộ** `total_count` (kể cả item lỗi) để một `temporal_validity` thấp phản ánh đúng vấn đề chất lượng dữ liệu nói chung, không chỉ riêng leakage.

### Vấn đề 3 — Parse timestamp/timezone không nhất quán giữa các module
Nhiều stage (retriever, evidence extractor, market analyzer, dashboard) đều cần so sánh `news_time`/`forecast_time`. Mỗi nơi tự viết parse ISO-8601/UTC riêng dễ lệch quy ước (một chỗ coi naive timestamp là local time, chỗ khác coi là UTC).

**Giải pháp kỹ thuật**: chốt quy ước "naive timestamp = UTC" một lần, gom toàn bộ logic parse vào `TimeUtils` (`parse_datetime`/`normalize_to_utc`/`parse_utc`) trong `src/retriever.py`, các stage khác bắt buộc import từ đây. Không sort lại danh sách theo thời gian (giữ nguyên thứ tự input) vì sort thêm nondeterminism khi có timestamp bằng nhau và làm downstream bất ngờ khi kỳ vọng giữ thứ tự stream gốc.

---

## Stage: Evidence Extractor (A4)

### Vấn đề 1 — Keyword dictionary quá thưa kéo sập cả chuỗi phía sau
V1 dictionary chỉ match ~5% text mẫu → 79/79 evidence `polarity=neutral` → Forecast Model dự báo `HOLD` 100/100 lần → accuracy rơi xuống ~27% (đúng bằng tỉ lệ nhãn HOLD thật) → Faithfulness Evaluator đo `confidence_drop=0` mọi trường hợp (xóa evidence trung tính không đổi gì) → không quan sát được đối lập "faithful vs decorative" mà đề tài cần đo.

**Giải pháp kỹ thuật**: mở rộng dictionary qua 2 vòng thực nghiệm trên chính `data/sample_dataset.csv` — V2 thêm cụm nhiều từ xuất hiện thật trong sample; V3 rà tiếp 51/100 sample còn false-HOLD, bổ sung 21 từ positive + 16 negative, kiểm tra từng entry tránh false-positive chéo hướng. Giữ verbatim vocabulary cũ mỗi vòng — `POSITIVE_KEYWORDS`/`NEGATIVE_KEYWORDS` là hằng số module-level duy nhất, downstream import theo tên nên không cần sửa gì khi dictionary lớn thêm.

### Vấn đề 2 — Một keyword nhiều từ bị tách rời bởi từ chêm ở giữa (không match được substring liên tục)
Câu thật như `"weak iPhone sales"` không chứa `"weak sales"` như một substring liên tục — exact substring match thất bại dù về ngữ nghĩa là khớp.

**Giải pháp kỹ thuật**: fallback token-level matching — tách keyword nhiều từ thành các token, tìm vị trí từng token, chấp nhận khoảng cách tối đa **15 ký tự** giữa 2 token liên tiếp (đủ hấp thụ một danh từ chêm như "iPhone"/"cloud"/"Q3", đủ hẹp để không bắc cầu qua các từ không liên quan). Chỉ kích hoạt khi exact substring không tìm thấy.

### Vấn đề 3 — Nhiều keyword cùng khớp chồng lấn lên nhau tại một vị trí trong text
Ví dụ `"warns of"` (negative, 8 ký tự) và `"warns"` (negative, 5 ký tự) cùng khớp một đoạn text — giữ cả hai sẽ tạo evidence trùng lặp/nhiễu.

**Giải pháp kỹ thuật**: overlap resolution — sort tất cả match theo `(-length, start_char)`, giữ match dài nhất trước, bỏ qua match nào chồng lấn với match đã giữ; kết quả cuối re-sort theo `start_char` tăng dần để giữ đúng thứ tự xuất hiện trong text. Rule cố định, không heuristic — đảm bảo deterministic và audit được.

### Vấn đề 4 — Không có ground-truth confidence cho từng keyword, nhưng vẫn cần một con số `support_score`
Dictionary V1 không có dữ liệu huấn luyện để tính confidence riêng cho từng từ khóa.

**Giải pháp kỹ thuật**: `support_score` là hằng số nhị phân theo polarity (1.0 cho match, 0.5 cho neutral fallback) thay vì gán điểm riêng từng từ — giữ contract ổn định, downstream dễ suy luận; đây là điểm mở rộng có chủ ý cho phiên bản sau (thay số bằng điểm hiệu chỉnh mà không đổi tên field).

---

## Stage: Forecast Model (A5)

### Vấn đề 1 — Công thức confidence "score/total_evidence" thổi phồng confidence khi chỉ có 1 evidence
`abs(1)/1 = 1.0` sẽ cho confidence tuyệt đối chỉ từ một mẩu tin — quá mạnh cho một dự báo dựa trên đúng 1 bằng chứng.

**Giải pháp kỹ thuật**: `confidence = 0.5 + min(abs(score) * 0.1, 0.45)`, clamp `[0.5, 0.95]` — không chia cho `total_evidence`, chỉ phụ thuộc `abs(score)`. Hàm bão hòa tại `abs(score)=5` (giữ đường cong ổn định, dễ diễn giải bất kể số lượng evidence), sàn 0.5 (không bao giờ tự nhận kém tin cậy hơn tung đồng xu), trần 0.95 (không bao giờ tự nhận chắc chắn tuyệt đối).

### Vấn đề 2 — Ablation (bỏ evidence, dự báo lại) không được phép có 2 bản logic dự báo
Faithfulness Evaluator cần "dự báo lại sau khi bỏ evidence được cite" — nếu cho phép tự viết một bản rút gọn của thuật toán vote để làm việc này, rủi ro 2 bản logic lệch nhau theo thời gian.

**Giải pháp kỹ thuật**: tách `predict_without_evidence(input_data, removed_evidence_ids)` thành hàm riêng (không phải tham số optional của `predict()`) để call site tại Faithfulness Evaluator tự minh bạch ý định — nhưng cả hai hàm cùng gọi chung một helper nội bộ `_predict_core(..., exclude_ids=...)` nên **không thể lệch nhau**.

### Vấn đề 3 — Score dùng số nguyên làm mất sắc thái, nhưng đổi sang trọng số sẽ phá tính audit được
5 evidence yếu và 1 evidence mạnh cho cùng score nếu chỉ đếm số lượng.

**Giải pháp kỹ thuật**: chấp nhận đánh đổi có chủ ý — giữ `score` là hiệu số nguyên (không weighting theo từ khóa/độ mới), vì "thuật toán phải tái lập được byte-for-byte từ runtime khác, và số học nguyên là hợp đồng dễ audit nhất". Bù lại bằng 2 field phụ `evidence_strength` (`abs(score)/directional_evidence_count`) và `conflict_ratio` để lộ thông tin sắc thái mà không đổi cách tính score.

### Vấn đề 4 — Dữ liệu evidence đầu vào có thể trùng ID hoặc thiếu `expected_direction` hợp lệ
Một evidence_id trùng lặp hoặc direction không hợp lệ nếu lọt vào vote sẽ làm sai lệch score mà không ai biết.

**Giải pháp kỹ thuật**: dedupe theo `evidence_id` (giữ lần xuất hiện đầu, các lần sau vào `warnings` dạng `DUPLICATE_EVIDENCE_ID`); `expected_direction` thiếu/không hợp lệ → bỏ qua item + cảnh báo `INVALID_EVIDENCE` (mặc định `strict=False` để một item lỗi không làm sập cả batch, có cờ `strict=True` cho nơi cần raise ngay).

---

## Stage: Evidence Selector (A4 mở rộng, B2)

### Vấn đề 1 — Phân loại pro/counter/neutral phụ thuộc vào *prediction*, nhưng không có nhãn ground-truth để học
Không có model học được nào để quyết định một evidence là ủng hộ hay trái chiều với một prediction cụ thể, và dataset 30–100 dòng cũng không đủ để huấn luyện.

**Giải pháp kỹ thuật**: bảng tra cứu cố định `(prediction, expected_direction) → label` (9 ô) — nhỏ đủ để audit bằng mắt, dễ mở rộng sau (ví dụ thêm trọng số theo độ mới/độ mạnh từ khóa) mà không đổi contract. Mỗi cell có `reason` string cố định đi kèm để log giải thích được vì sao phân loại như vậy.

### Vấn đề 2 — Trường hợp HOLD/HOLD trông giống "không có ủng hộ" nhưng thực ra hợp lý
`prediction=HOLD` + `expected_direction=HOLD` → bảng phân loại xếp là `pro` — người đọc có thể hiểu nhầm "evidence trung tính sao lại tính là ủng hộ".

**Giải pháp kỹ thuật**: giữ nguyên quyết định (model "đúng" khi dự báo HOLD chỉ với evidence trung tính) nhưng ghi rõ trong `reason` ("matches prediction HOLD") và trong tài liệu spec để tránh hiểu nhầm khi đọc dashboard — xử lý bằng minh bạch hoá thay vì đổi logic.

### Vấn đề 3 (B2) — Đo được bao nhiêu % counterevidence bị phát hiện, nhưng không có nhãn thủ công để so sánh
Muốn tính `counterevidence_coverage = detected/available` cần biết "available" là bao nhiêu — nhưng dataset không có annotation tay cho việc này.

**Giải pháp kỹ thuật**: `expected_labels` được **suy ra** trực tiếp từ chính `CLASSIFICATION_TABLE` đã dùng để phân loại (không annotate thủ công) — nhất quán và deterministic. `summary` (pro/counter/neutral count) luôn tính trên nhóm **đầy đủ trước khi cắt** `top_k`, để coverage không bị bóp méo bởi giới hạn hiển thị trên dashboard.

### Vấn đề 4 — Retriever lẽ ra đã lọc sạch tin tương lai, nhưng nếu bị bypass thì sao?
Selector nằm sau Retriever trong chuỗi nhưng không được mặc định tin dữ liệu đầu vào luôn sạch.

**Giải pháp kỹ thuật**: defense in depth lần 2 — bất kỳ evidence nào có `news_time > forecast_time` đều bị tách vào `invalid_future_evidence` riêng (không lọt vào pro/counter/neutral), dashboard hiển thị banner cảnh báo nếu list này không rỗng — coi là "smoke alarm" cho lỗi toàn vẹn pipeline chứ không phải trường hợp nghiệp vụ bình thường.

---

## Stage: Faithfulness Evaluator (A6)

### Vấn đề 1 — Ablation phải phản ánh đúng model thật, không được tự suy diễn
Nếu evaluator tự tính lại kết quả sau khi bỏ evidence thay vì gọi lại model thật, `confidence_drop` sẽ là con số vô nghĩa (không phản ánh model thật đang làm gì).

**Giải pháp kỹ thuật**: evaluator chỉ được gọi `ForecastModel.predict_without_evidence` — không được tự implement lại thuật toán vote dưới bất kỳ hình thức nào ("MUST NOT duplicate the prediction algorithm"). Tách file `faithfulness_metrics.py` (pure, 7 hàm metric không IO) khỏi `faithfulness_evaluator.py` (orchestrator, nơi duy nhất import `forecast_model`) để reviewer audit công thức toán mà không phải soi cả logic gọi model.

### Vấn đề 2 — Xóa evidence nào để ablation cho tín hiệu ý nghĩa nhất?
Xóa toàn bộ cited evidence (cả pro lẫn counter) sẽ vô tình đẩy prediction lệch lên theo hướng còn lại, làm confidence_drop khó diễn giải.

**Giải pháp kỹ thuật**: chiến lược mặc định `remove_cited_pro_evidence` — chỉ xóa evidence *ủng hộ* prediction, đây là phép thử mạnh nhất (nếu prediction sụp khi bỏ đúng phần ủng hộ nó, evidence đó thực sự "load-bearing"). Chiến lược `remove_all_cited_evidence` vẫn hỗ trợ cho ai cần góc nhìn rộng hơn, nhưng không phải default.

### Vấn đề 3 — `confidence_drop` một mình không phân biệt được "giảm nhẹ" với "prediction đổi hẳn"
Một confidence_drop lớn mà không đổi prediction khác về bản chất với một drop nhỏ nhưng khiến prediction lật ngược hoàn toàn (UP→DOWN).

**Giải pháp kỹ thuật**: đưa `prediction_after_removal` vào report như một field độc lập, và verdict cascade ưu tiên kiểm tra "prediction có đổi không" trước khi xét ngưỡng `confidence_drop` (`prediction_after_removal != prediction` → `strong_faithful_candidate` ngay, không cần chờ ngưỡng số). Cascade 7 nhánh, dừng ở nhánh đầu tiên khớp — deterministic, dễ audit hơn một hàm scoring liên tục.

### Vấn đề 4 — `faithfulness_score` composite dễ bị hiểu nhầm là metric khoa học đã kiểm chứng
Một con số tổng hợp duy nhất trên dashboard rất dễ bị đọc như "điểm faithfulness chính thức" trong khi nó chỉ là heuristic hiển thị.

**Giải pháp kỹ thuật**: công thức cố định `0.35×temporal_validity + 0.30×evidence_support + 0.35×normalized_drop` (drop chuẩn hóa bão hòa ở 0.30), nhưng ghi rõ trong docstring/README/spec đây là "V1 dashboard heuristic, not a final scientific metric" — `confidence_drop` mới là tín hiệu chính, composite chỉ để hiển thị nhanh.

---

## Stage: Sufficiency Evaluator (B1)

### Vấn đề 1 — Module cần biết "evidence nào được cite" nhưng không được phụ thuộc trực tiếp vào Evidence Selector
Nếu `SufficiencyEvaluator` tự nhận `selector_result` và tự đọc cấu trúc pro/counter bên trong, nó bị khóa cứng vào định dạng output của Evidence Selector — đổi Selector sẽ kéo theo đổi Sufficiency.

**Giải pháp kỹ thuật**: `SufficiencyEvaluator.evaluate(original_input, original_result, cited_evidence_ids)` chỉ nhận một `set[str]` các `news_id` đã cite — lớp glue (tính hợp `pro_evidence ∪ counterevidence` từ `sample["selection"]`) nằm ở adapter `process(envelope)`, không nằm trong class nghiệp vụ. Giữ hai module độc lập, chỉ chạm nhau qua envelope.

### Vấn đề 2 — Sufficiency cần trả lời 2 câu hỏi khác nhau bằng cùng một cơ chế (reuse ForecastModel, không train model mới)
Câu hỏi "chỉ dùng cited evidence có đủ không" và "nếu thay cited evidence bằng trung tính thì đổi bao nhiêu" là hai phép thử khác nhau nhưng phải cùng deterministic, cùng không cần model mới.

**Giải pháp kỹ thuật**: cả hai đều tái sử dụng `ForecastModel.predict()` với input bị biến đổi — sufficiency lọc còn `cited_only_evidence`, counterfactual thay từng cited item bằng placeholder `{polarity: neutral, expected_direction: HOLD, support_score: 0.5}` rồi giữ nguyên phần uncited. `sufficiency_score = min(sufficiency_confidence/original_confidence, 1.0)`, ép về `0.0` khi `cited_evidence_ids` rỗng hoặc `original_confidence<=0` — edge case này bị bắt bởi test và fix sau khi phát hiện code ban đầu trả sai giá trị (0.5/original thay vì 0.0).

---

## Stage: Market Analyzer (B3)

### Vấn đề 1 — Không có dữ liệu thị trường thật, nhưng vẫn cần metric deterministic để test/demo được
Dataset học thuật không có `next_day_return`/`price_5d_return` thật, và việc gọi external price API nằm ngoài phạm vi đồ án.

**Giải pháp kỹ thuật**: sinh dữ liệu synthetic ngay trong CSV (không hard-code trong code) — seed bằng `hash(ticker + forecast_time) % 1000` để cùng input luôn ra cùng return, đảm bảo pipeline vẫn deterministic byte-for-byte dù dữ liệu giá là giả lập. Dashboard label rõ "synthetic" để không gây hiểu nhầm là dữ liệu thị trường thật.

### Vấn đề 2 — Chọn ngưỡng nào cho "market_consistent" và "regime" mà không có ground truth để tune
Không có cách nào validate ngưỡng bằng backtest thật trong phạm vi prototype.

**Giải pháp kỹ thuật**: chọn `±0.5%` cho consistency (loại nhiễu trong ngày, mức phổ biến trong tài liệu financial NLP) và `±2%` cho regime 5 ngày (tương đương một "significant trend"). Ngưỡng cố định, tài liệu hoá rõ lý do chọn trong design.md thay vì giấu trong code — để người review có thể tranh luận đúng chỗ.

### Vấn đề 3 — Module cần độc lập khỏi Evidence Selector/Forecast Model để dễ test
Nếu `MarketAnalyzer` nhận nguyên `selector_result` hay `forecast_result` dict phức tạp, nó bị coupling không cần thiết với 2 module khác.

**Giải pháp kỹ thuật**: `MarketAnalyzer.analyze(prediction, next_day_return, price_5d_return)` chỉ nhận scalar — hoàn toàn độc lập, dễ unit test bằng bộ 3 giá trị đơn giản, không cần dựng lại toàn bộ envelope.

---

## Stage: Agent Trace (B4)

### Vấn đề — Cần trace log có cấu trúc, audit được, không phải văn bản tự do
Yêu cầu B4 đòi hỏi bằng chứng ≥3 agent role, có quality gate, có human review — nếu ghi tự do (markdown log) thì không tổng hợp thống kê được (pass rate, phân bố role).

**Giải pháp kỹ thuật**: schema JSON cố định 6 field bắt buộc (`run_id`, `agent_role`, `task`, `output`, `human_review`, `quality_gate`) + field optional (`timestamp`, `input`, `notes`). `write_trace_entry` đọc toàn bộ file hiện tại rồi ghi lại (append-safe cho single-process prototype, không cần lock phức tạp). `load_trace_log` không bao giờ raise — file thiếu/hỏng trả `[]` để dashboard không crash khi trace log chưa tồn tại.

---

## Stage: Dashboard (A7)

### Vấn đề 1 — Cache phải tự làm mới khi pipeline chạy lại, nhưng không được gọi lại pipeline
Dashboard bắt buộc read-only tuyệt đối, nhưng cache mặc định theo path cố định sẽ hiển thị dữ liệu cũ sau khi `runner` ghi đè `08_market.json`.

**Giải pháp kỹ thuật**: đưa `mtime` của file vào cache key (`@st.cache_data` trên hàm nhận `(path, mtime)`) — file đổi thì mtime đổi thì cache tự invalidate, không cần thao tác thủ công, không cần dashboard biết gì về việc pipeline "vừa chạy xong".

### Vấn đề 2 — Toggle "Remove cited evidence" trông như cần tính toán lại, nhưng dashboard không được re-run model
Yêu cầu read-only tuyệt đối (A7 + kịch bản demo) mâu thuẫn bề mặt với tính năng "xem confidence đổi thế nào nếu bỏ evidence".

**Giải pháp kỹ thuật**: số liệu ablation (`confidence_after_removal`, `prediction_after_removal`) đã được `Faithfulness Evaluator` tính sẵn ở stage trước và ghi vào envelope — dashboard chỉ đọc field có sẵn để toggle hiển thị, không gọi `ForecastModel` hay bất kỳ stage nào tại runtime.
