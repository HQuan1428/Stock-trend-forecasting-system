# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Context

Đây là đồ án cuối kì môn **Công nghệ mới** — prototype học thuật về **Faithful Evidence-Centric Financial News Forecasting**. Hệ thống dự báo xu hướng cổ phiếu (UP/DOWN/HOLD) từ tin tức và **kiểm chứng tính faithful của evidence** (bằng chứng mà mô hình dùng có thật sự quyết định prediction không?). Không phải hệ thống giao dịch thật.

Thang điểm: 7 điểm cơ bản (A1–A7) + 3 điểm nâng cao (B1–B4) + tối đa 2 điểm cộng.

## Commands

```bash
# Cài dependencies
pip install -r requirements.txt

# Chạy toàn bộ pipeline (input → 4 output CSV)
python -m src.pipeline --input data/sample_dataset.csv --output-dir outputs

# Chạy dashboard
streamlit run src/dashboard/app.py

# Chạy toàn bộ test
pytest tests/

# Chạy một file test cụ thể
pytest tests/test_temporal_retriever.py -v

# Chạy một test case cụ thể
pytest tests/test_forecast_model.py::test_predict_up -v
```

## Architecture

Pipeline 6 giai đoạn (mỗi giai đoạn là một module độc lập, dùng plain `dict`, không dùng dataclass runtime):

```
data/sample_dataset.csv
    │
    ▼
src/retriever.py          → retrieve_valid_news()
    │  Phân loại tin: valid_news (news_time ≤ forecast_time) vs invalid_future_news
    │  Trả về RetrievalResult (frozen dataclass)
    ▼
src/evidence_extractor.py → extract_evidence_batch()
    │  Keyword matching (rule-based, V1/V2/V3 dictionary) → polarity + expected_direction
    │  POSITIVE_KEYWORDS / NEGATIVE_KEYWORDS là single source of truth cho polarity
    ▼
src/evidence_selector.py  → select_evidence_batch()
    │  Phân loại: pro_evidence / counterevidence / neutral_evidence theo prediction
    ▼
src/forecast_model.py     → predict() / predict_without_evidence()
    │  Rule-based voting: score = positive_count - negative_count
    │  confidence = 0.5 + min(abs(score)*0.1, 0.45)
    │  predict_without_evidence() dùng để tính confidence_drop cho faithfulness
    ▼
src/faithfulness_evaluator.py → FaithfulnessEvaluator.evaluate()
    │  3 metrics: temporal_validity, evidence_support, confidence_drop
    │  faithfulness_label: HIGH (drop≥0.20) / MEDIUM (drop≥0.05) / LOW
    ▼
outputs/
    prediction_results.csv
    evidence_results.csv
    faithfulness_results.csv
    temporal_leakage_results.csv
    │
    ▼
src/dashboard/app.py      (Streamlit, read-only, không gọi pipeline)
```

**Orchestrator**: `src/pipeline.py::run_pipeline()` — glue code, không re-implement logic của các stage.

**Data schemas** (`src/schema.py`): `NewsRecord`, `EvidenceItem`, `ForecastResult`, `FaithfulnessResult`, `PipelineResult` — chỉ dùng để document cross-stage data flow, không enforce runtime.

**Dashboard** (`src/dashboard/`): tách thành `app.py`, `charts.py`, `components.py`, `data_loader.py`, `metrics.py`, `validators.py`.

**Samples** (`samples/`): fixture JSON cho từng stage để dùng trong tests.

## OpenSpec Workflow

Mọi feature mới phải có OpenSpec trước khi implement. Các change đang active nằm trong `openspec/changes/<tên-change>/`. Archived change nằm trong `openspec/changes/archive/`.

Mỗi change gồm: `proposal.md`, `design.md`, `tasks.md`, `specs/<domain>/spec.md`.

Nếu implementation và spec không khớp → cập nhật spec hoặc hỏi trước.

## Key Invariants

- **Temporal validity là bất khả xâm phạm**: `news_time > forecast_time` → loại. Retriever lọc trước, Forecast Model lọc thêm lần nữa (defense in depth).
- **Không có ML/LLM/external API** trong baseline. Toàn bộ V1 là deterministic, rule-based.
- `POSITIVE_KEYWORDS` và `NEGATIVE_KEYWORDS` trong `evidence_extractor.py` là single source of truth — downstream modules import từ đây, không tự định nghĩa lại polarity.
- Pipeline là **deterministic**: cùng input → cùng output byte-for-byte.
- Dashboard **không mutate** files trong `outputs/` và không gọi pipeline.

## Data Format

CSV đầu vào cần có các cột: `news_id`, `ticker`, `forecast_time`, `news_time`, `news_text`, `label`.

Timestamps: ISO 8601, naive = UTC. Pipeline group rows theo `(ticker, forecast_time)`.

## Boundaries

Hỏi trước khi: thêm real financial data, ML/NLP model nâng cao, external API, crawler, database, authentication, hoặc thay đổi kiến trúc lớn.

Tuyệt đối không: thêm secret/API key, khuyến nghị mua/bán thật, dùng tin tức tương lai trong thí nghiệm.
