# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Context

Đây là đồ án cuối kì môn **Công nghệ mới** — prototype học thuật về **Faithful Evidence-Centric Financial News Forecasting**. Hệ thống dự báo xu hướng cổ phiếu (UP/DOWN/HOLD) từ tin tức và **kiểm chứng tính faithful của evidence** (bằng chứng mà mô hình dùng có thật sự quyết định prediction không?). Không phải hệ thống giao dịch thật.

Thang điểm: 7 điểm cơ bản (A1–A7) + 3 điểm nâng cao (B1–B4) + tối đa 2 điểm cộng.

## Commands

```bash
# Cài dependencies
pip install -r requirements.txt

# Chạy end-to-end (CSV → 8 envelope JSON + 6 CSV kết quả)
python -m src.runner --input data/sample_dataset.csv --output-dir outputs

# Dừng sớm sau một stage
python -m src.runner --input data/sample_dataset.csv --output-dir outputs --stop-after forecast_model

# Chạy từng stage rời (output stage này là input stage sau)
python -m src.stages.ingest --input data/sample_dataset.csv -o outputs/01_samples.json
python -m src.stages.retriever --input outputs/01_samples.json -o outputs/02_retrieved.json
python -m src.stages.evidence_extractor --input outputs/02_retrieved.json -o outputs/03_evidence.json
python -m src.stages.forecast_model --input outputs/03_evidence.json -o outputs/04_forecast.json
python -m src.stages.evidence_selector --input outputs/04_forecast.json -o outputs/05_selected.json
python -m src.stages.faithfulness_evaluator --input outputs/05_selected.json -o outputs/06_faithfulness.json
python -m src.stages.sufficiency_evaluator --input outputs/06_faithfulness.json -o outputs/07_sufficiency.json
python -m src.stages.market_analyzer --input outputs/07_sufficiency.json -o outputs/08_market.json
python -m src.export_csv --input outputs/08_market.json --output-dir outputs

# Chạy dashboard (đọc outputs/08_market.json, read-only)
streamlit run src/dashboard/app.py

# Chạy toàn bộ test
pytest tests/

# Chạy một file test cụ thể
pytest tests/test_temporal_retriever.py -v

# Chạy một test case cụ thể
pytest tests/test_forecast_model.py::test_predict_up -v
```

## Architecture

Chuỗi stage tương tác được — mỗi stage là một **class** (OOP, method public trả plain `dict`) kèm hai hàm adapter module-level: `process(envelope) -> envelope` (pure, không I/O) và `main(argv)` (CLI). CLI rời và runner cùng gọi `process()` — **một code path duy nhất**.

Dữ liệu trao đổi là **accumulating envelope**: JSON `{"stage": ..., "samples": [...]}`; mỗi stage chỉ **bổ sung** field vào sample (namespace riêng: `forecast`, `selection`, `faithfulness`, ...), không xóa/ghi đè field của stage trước. Schema được validate ở ranh giới mỗi stage (`src/core/schema.py::validate_sample` + `REQUIRED_SAMPLE_KEYS`, cumulative theo chuỗi); input hỏng → stderr + exit code 2.

Các module stage nằm trong `src/stages/`, plumbing dùng chung nằm trong `src/core/`; `runner.py`/`export_csv.py` (có CLI riêng) và `dashboard/` nằm ở gốc `src/`.

```
data/sample_dataset.csv
    │
    ▼
src/stages/ingest.py             → 01_samples.json
    │  CSV → envelope: group theo (ticker, forecast_time) giữ thứ tự, sinh sample_id
    │  stdlib csv, không pandas; cột giá thiếu → 0.0
    ▼
src/stages/retriever.py          → 02_retrieved.json     TemporalRetriever.retrieve()
    │  Phân loại tin: valid_news (news_time ≤ forecast_time) vs invalid_future_news
    │  TimeUtils = single source of truth UTC parsing
    ▼
src/stages/evidence_extractor.py → 03_evidence.json      EvidenceExtractor.extract_batch()
    │  V3: FinBERT (ProsusAI/finbert, frozen, lazy-load ~400MB) → polarity + sentiment_probs
    │  Mỗi evidence item có thêm `sentiment_probs = {positive, negative, neutral}`
    │  → single source of truth cho polarity model mới
    ▼
src/stages/forecast_model.py     → 04_forecast.json      ForecastModel.predict()
    │  V3: Attention Evidence Aggregator (PyTorch, trainable qua
    │  scripts/train_evidence_aggregator.py) — checkpoint commit ở
    │  models/evidence_aggregator_v1.pt. Forward: 7-dim evidence
    │  feature → proj → attention pooling → concat 2 price features
    │  → head MLP → softmax 3 class. Seed reproducibility (không strict
    │  byte-deterministic).
    │  confidence = 0.5 + min(abs(score)*0.1, 0.45)
    │  build_forecast_request() dùng chung cho faithfulness/sufficiency stage
    ▼
src/stages/evidence_selector.py  → 05_selected.json      EvidenceSelector.select_batch() + compute_coverage() (B2)
    │  Phân loại pro/counter/neutral theo CLASSIFICATION_TABLE; coverage vào sample["coverage"]
    ▼
src/stages/faithfulness_evaluator.py → 06_faithfulness.json  FaithfulnessEvaluator.evaluate()
    │  3 metrics (FaithfulnessMetrics): temporal_validity, evidence_support, confidence_drop
    ▼
src/stages/sufficiency_evaluator.py → 07_sufficiency.json    SufficiencyEvaluator.evaluate() (B1)
    │  cited_ids lấy từ sample["selection"] (pro ∪ counter)
    ▼
src/stages/market_analyzer.py    → 08_market.json        MarketAnalyzer.analyze() (B3)
    │  market_consistent (ngưỡng ±0.005), regime bull/bear/sideways (ngưỡng ±0.02)
    ▼
src/export_csv.py         → 6 CSV kết quả
    prediction_results.csv, evidence_results.csv,
    faithfulness_results.csv (gồm counterevidence_coverage B2, faithfulness_label HIGH/MEDIUM/LOW),
    sufficiency_results.csv (B1), market_consistency_results.csv (B3),
    temporal_leakage_results.csv
```

**Orchestrator**: `src/runner.py` — thin glue (~100 dòng), chain các `process()` in-process, ghi envelope trung gian từng stage + gọi export_csv. KHÔNG re-implement logic stage.

**Shared plumbing**: `src/core/stage_io.py` — `load_envelope` (đọc + validate), `dump_envelope` (deterministic: sort_keys, indent=2, ensure_ascii=False, trailing newline), `run_stage_cli` (thân CLI chung).

**Dashboard** (`src/dashboard/`): Streamlit + Plotly, **read-only** — đọc duy nhất `outputs/08_market.json` (envelope cuối), không mutate `outputs/`, không gọi stage/pipeline, không re-run model (toggle "Remove cited evidence" dùng số liệu ablation đã tính sẵn trong `faithfulness`). Tách lớp: `data_loader.py`/`metrics.py`/`charts.py` là hàm thuần (pytest được không cần server), `app.py`/`components.py` chỉ render. 6 tab: Live Demo (kịch bản ChuDe1.md §11.1), Overview, Evidence, Faithfulness (+radar), Temporal Leakage, B-metrics (B1–B4).

**B4**: `src/core/agent_trace.py` nằm ngoài chuỗi runtime — SDLC trace log, không phải stage.

**Data schemas** (`src/core/schema.py`): dataclass (`NewsRecord`, `EvidenceItem`, ...) chỉ để document; phần runtime là `REQUIRED_SAMPLE_KEYS` + `validate_sample` cho envelope.

## OpenSpec Workflow

Mọi feature mới phải đi đủ chu trình OpenSpec bằng skills: `openspec-propose` (tạo change) → `openspec-apply-change` (implement theo tasks.md) → `openspec-archive-change` (archive + sync spec). Change active nằm trong `openspec/changes/<tên-change>/`, archived trong `openspec/changes/archive/`.

Mỗi change gồm: `proposal.md`, `design.md`, `tasks.md`, `specs/<domain>/spec.md`.

Nếu implementation và spec không khớp → cập nhật spec hoặc hỏi trước.

## Key Invariants

- **Temporal validity là bất khả xâm phạm**: `news_time > forecast_time` → loại. Retriever lọc trước, Forecast Model lọc thêm lần nữa (defense in depth).
- **Forecast Model V3 dùng Attention Evidence Aggregator (PyTorch)**:
      trọng số là hằng số đóng băng trong `models/evidence_aggregator_v1.pt`
      (commit vào repo), train qua `scripts/train_evidence_aggregator.py`
      trên Colab T4 hoặc local CPU. Runtime gọi `model.eval() + torch.no_grad()
      + torch.manual_seed(42)` → seed-reproducible trong tolerance `1e-6`
      float, KHÔNG strict byte-deterministic. Evidence Extractor dùng
      FinBERT (ProsusAI/finbert, frozen, lazy-load). Không có external API
      lúc runtime.
- `EvidenceExtractor.POSITIVE_KEYWORDS` và `NEGATIVE_KEYWORDS` là single source of truth — downstream đọc trực tiếp attr này, không tự định nghĩa lại polarity.
- Timestamp parsing dùng chung `src.stages.retriever.TimeUtils` (`parse_datetime` / `normalize_to_utc` / `parse_utc`) — không tự viết lại logic parse ISO-8601/UTC ở module khác.
- **Deterministic byte-for-byte**: cùng input → cùng output (JSON và CSV). `process()` phải pure — không I/O file, không phụ thuộc thời gian thực.
- **Envelope chỉ bổ sung, không phá**: stage không được xóa/ghi đè field của stage trước; kết quả stage nằm dưới key namespace riêng.
- Trong `process()` không gọi API tự ghi file (ví dụ `ForecastModel.predict_batch` mặc định ghi `outputs/*.csv` — dùng `predict()` per-sample).

## Data Format

CSV đầu vào cần có các cột: `news_id`, `ticker`, `forecast_time`, `news_time`, `news_text`, `label` (tùy chọn: `next_day_return`, `price_5d_return` cho B3 — thiếu thì mặc định `0.0`).

Timestamps: ISO 8601, naive = UTC. Ingest group rows theo `(ticker, forecast_time)`.

## Boundaries

Hỏi trước khi: thêm real financial data, ML/NLP model nâng cao, external API, crawler, database, authentication, hoặc thay đổi kiến trúc lớn.

Tuyệt đối không: thêm secret/API key, khuyến nghị mua/bán thật, dùng tin tức tương lai trong thí nghiệm.
