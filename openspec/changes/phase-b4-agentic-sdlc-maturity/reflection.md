# Reflection: Agentic SDLC trong Dự Án Faithful Evidence-Centric Forecasting

## 3 Agent Roles và nhiệm vụ cụ thể

### 1. Research Agent
**Nhiệm vụ**: Phân tích bài toán, xác định gap trong hệ thống hiện có, viết OpenSpec (proposal.md + design.md + spec.md).

**Thực tế đã làm trong dự án**:
- Phân tích `src/faithfulness_evaluator.py` và xác định gap: chưa có counterevidence coverage (B2), chưa có sufficiency (B1), chưa có market consistency (B3).
- Viết proposal cho từng change, đề xuất interface (`SufficiencyEvaluator.evaluate()`, `MarketAnalyzer.analyze()`), xác định ngưỡng (`±0.005`, `±0.02`).
- Thiết kế schema output CSV (sufficiency_results.csv 10 cột, market_consistency_results.csv 9 cột).
- Quyết định dùng hash-based seed cho synthetic market data để đảm bảo determinism.

### 2. Coding Agent
**Nhiệm vụ**: Implement module theo spec đã được human approve, integrate vào pipeline, cập nhật dashboard.

**Thực tế đã làm trong dự án**:
- Implement `src/sufficiency_evaluator.py` (B1): `_only_cited_evidence()`, `_perturb_to_neutral()`, `_compute_sufficiency_score()`, `SufficiencyEvaluator`.
- Implement `src/market_analyzer.py` (B3): `_classify_regime()`, `_is_market_consistent()`, `MarketAnalyzer`.
- Integrate cả hai module vào `src/pipeline.py` (thêm bước 6b, 6c trong `_run_group()`).
- Update dashboard: thêm tabs "Sufficiency" và "Market Consistency" vào `components.py` và `app.py`.
- Enrich `data/sample_dataset.csv` với 3 cột synthetic market data.
- Phát hiện và fix edge case: khi `cited_evidence_ids` rỗng, `sufficiency_score` phải là `0.0` (không phải `0.5/original`).

### 3. Testing/Review Agent
**Nhiệm vụ**: Viết test cases từ spec scenarios, verify output, review code quality.

**Thực tế đã làm trong dự án**:
- Viết `tests/test_sufficiency_evaluator.py` (12 tests) bao phủ mọi scenario trong spec.
- Viết `tests/test_market_analyzer.py` (18 tests) với parametrize cho boundary conditions.
- Thêm pipeline integration tests: schema check, row count, missing-column fallback.
- Chạy `pytest` sau mỗi change để verify: 483 → 497 → 535 tests.
- Review và phát hiện 1 test fail (`sufficiency_score=0.0` edge case) → báo cáo → Coding Agent fix.

---

## Human Control Points (Quality Gates)

Quy trình Agentic SDLC trong dự án này không tự động hoàn toàn — con người kiểm soát tại các điểm chính:

| Quality Gate | Mô tả | Kết quả |
|---|---|---|
| **Spec Review** | User đọc proposal.md + design.md trước khi approve | Accepted (mọi change) |
| **pytest gate** | Toàn bộ test suite phải pass sau mỗi change | Passed (497 → 535 tests) |
| **Pipeline gate** | `python -m src.pipeline` chạy không lỗi, output CSV đúng schema | Passed |
| **Output review** | User xem `outputs/*.csv` để verify giá trị hợp lệ | Accepted |

**Con người không approve** thì AI agent không tiến hành implement. Quy trình: `/opsx:propose` → user review → user gõ "hãy bắt đầu" → `/opsx:apply`.

---

## Bài học rút ra từ Agentic SDLC

1. **Spec trước, code sau** — OpenSpec workflow buộc Research Agent phải viết spec rõ ràng trước. Điều này giúp Coding Agent không implement sai (boundary conditions `±0.005`, `±0.02` được quyết định trong design.md, không phải trong code).

2. **Human-in-the-loop tại spec level** — Con người review spec (proposal + design) hiệu quả hơn review code. Một quyết định sai ở design level (ví dụ: ngưỡng consistency) sẽ ảnh hưởng toàn bộ implementation; phát hiện sớm tiết kiệm chi phí.

3. **Testing Agent là quality gate** — Không phải chỉ chạy pytest, mà cần Testing Agent viết test từ spec scenarios. Test `test_empty_cited_ids_gives_sufficiency_zero...` đã phát hiện logic bug sau khi Coding Agent implement xong.

4. **Trace log = accountability** — `run_log.json` ghi lại chính xác ai làm gì, input là gì, output là gì, và kết quả quality gate. Điều này cho phép audit và reproducibility.

5. **AI không thay thế human judgment** — AI agent đề xuất threshold `±0.005` và `±0.02` dựa trên kiến thức domain financial NLP. Nhưng quyết định cuối cùng (có dùng giá trị đó không) vẫn là của con người (user approve spec).
