"""Streamlit dashboard — read-only view over the final stage envelope.

Run:
    streamlit run src/dashboard/app.py

Reads ``outputs/08_market.json`` only. Never writes to ``outputs/``,
never invokes a pipeline stage, never re-runs the model — the "Remove
cited evidence" toggle displays ablation numbers precomputed by the
faithfulness stage.
"""

from __future__ import annotations

import sys
from pathlib import Path

# ``streamlit run src/dashboard/app.py`` puts src/dashboard/ (not the repo
# root) on sys.path, so ``import src.*`` fails without this shim.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pandas as pd
import streamlit as st

from src.agent_trace import load_trace_log, summarize_trace
from src.dashboard import charts, components, metrics
from src.dashboard.data_loader import (
    DashboardData,
    DashboardDataError,
    load_dashboard_data,
)

# Anchor data paths to the repo root so the dashboard works no matter
# which directory ``streamlit run`` is invoked from.
ENVELOPE_PATH = str(_PROJECT_ROOT / "outputs" / "08_market.json")
TRACE_LOG_PATH = str(_PROJECT_ROOT / "outputs" / "run_log.json")

st.set_page_config(
    page_title="Faithful Evidence Forecasting",
    page_icon="📈",
    layout="wide",
)


@st.cache_data(show_spinner="Đang đọc envelope...")
def _load(path: str, mtime: float) -> DashboardData:
    # mtime participates in the cache key so a regenerated envelope
    # invalidates the cache without any manual clearing.
    del mtime
    return load_dashboard_data(path)


def _load_or_stop() -> DashboardData:
    path_obj = Path(ENVELOPE_PATH)
    mtime = path_obj.stat().st_mtime if path_obj.exists() else 0.0
    try:
        return _load(ENVELOPE_PATH, mtime)
    except DashboardDataError as exc:
        st.error(str(exc))
        st.stop()
        raise  # unreachable; keeps type-checkers happy


def render_live_demo(data: DashboardData) -> None:
    st.subheader("Live Demo — kịch bản 5 phút")
    samples = data.samples

    cols = st.columns(2)
    tickers = sorted(samples["ticker"].unique().tolist())
    ticker = cols[0].selectbox("1️⃣ Chọn ticker", tickers)
    times = metrics.sample_choices(samples, ticker)
    forecast_time = cols[1].selectbox("2️⃣ Chọn forecast date", times)

    sample = data.raw_sample(metrics.find_sample_id(samples, ticker, forecast_time))
    forecast = sample["forecast"]
    report = sample["faithfulness"]
    selection = sample["selection"]

    st.markdown("### 3️⃣ Tin hợp lệ trước thời điểm dự báo")
    if sample["valid_news"]:
        st.dataframe(
            pd.DataFrame(sample["valid_news"])[["news_id", "news_time", "news_text"]],
            width="stretch",
            hide_index=True,
        )
    else:
        st.warning(
            "Không còn tin hợp lệ nào — toàn bộ tin của sample này bị loại vì "
            "temporal leakage."
        )
    components.leakage_warning(sample["invalid_future_news"], sample["forecast_time"])

    st.markdown("### 4️⃣ Dự báo")
    components.metric_row(
        {
            "Prediction": forecast["prediction"],
            "Confidence": f"{float(forecast['confidence']):.2f}",
            "Label thực tế": sample.get("label") or "—",
        }
    )
    st.plotly_chart(
        charts.build_class_confidences_chart(forecast.get("class_confidences", {})),
        width="stretch",
    )

    st.markdown("### 5️⃣ Evidence và rationale")
    components.evidence_list("Pro evidence (ủng hộ prediction)", selection["pro_evidence"])
    components.evidence_list("Counterevidence (trái chiều)", selection["counterevidence"])
    st.info(f"**Rationale**: {forecast['rationale']}")

    st.markdown("### 6️⃣ Remove cited evidence")
    if st.toggle("Bỏ cited evidence khỏi input (số liệu ablation đã tính sẵn)"):
        components.confidence_comparison(report)
        st.markdown("### 7️⃣ Kết luận")
        components.verdict_banner(report["verdict"])
    else:
        st.caption("Bật toggle để so sánh confidence trước/sau ablation.")

    with st.expander("Limitation quan trọng"):
        st.markdown(
            "- Mô hình rule-based đếm keyword — không hiểu ngữ cảnh, phủ định, "
            "hay mỉa mai; confidence không phải xác suất hiệu chỉnh.\n"
            "- Confidence drop đo *necessity* của evidence với mô hình này, "
            "không chứng minh quan hệ nhân quả với thị trường thật.\n"
            "- Dataset mô phỏng, không đại diện cho thị trường; kết quả không "
            "phải khuyến nghị đầu tư."
        )


def render_overview(data: DashboardData) -> None:
    st.subheader("Overview")
    samples = data.samples
    components.metric_row(
        {
            "Số sample": str(len(samples)),
            "Accuracy": f"{metrics.accuracy(samples):.1%}",
            "Avg confidence": f"{metrics.average_confidence(samples):.2f}",
            "Avg confidence drop": f"{metrics.average_confidence_drop(samples):.2f}",
        }
    )
    cols = st.columns(2)
    cols[0].plotly_chart(
        charts.build_prediction_distribution_chart(
            metrics.prediction_distribution(samples)
        ),
        width="stretch",
    )
    with cols[1]:
        st.markdown("**Accuracy theo ticker**")
        st.dataframe(
            metrics.accuracy_by_ticker(samples), width="stretch", hide_index=True
        )


def render_evidence(data: DashboardData) -> None:
    st.subheader("Evidence")
    components.filterable_evidence_table(data.evidence)


def render_faithfulness(data: DashboardData) -> None:
    st.subheader("Faithfulness")
    samples = data.samples
    dist = metrics.faithfulness_label_distribution(samples)
    components.metric_row(
        {
            "HIGH": str(dist["HIGH"]),
            "MEDIUM": str(dist["MEDIUM"]),
            "LOW": str(dist["LOW"]),
        }
    )
    st.plotly_chart(charts.build_confidence_drop_chart(samples), width="stretch")
    st.plotly_chart(
        charts.build_faithfulness_radar_chart(
            metrics.RADAR_AXES, metrics.radar_values(samples)
        ),
        width="stretch",
    )


def render_leakage(data: DashboardData) -> None:
    st.subheader("Temporal Leakage")
    leakage = data.leakage
    kind, message = metrics.leakage_severity(len(leakage))
    components.banner(kind, message)
    if not leakage.empty:
        st.dataframe(leakage, width="stretch", hide_index=True)


def render_b_metrics(data: DashboardData) -> None:
    st.subheader("B-metrics")
    samples = data.samples

    st.markdown("#### B1 — Sufficiency + Counterfactual")
    suff = metrics.sufficiency_summary(samples)
    components.metric_row(
        {
            "Avg sufficiency": f"{suff['avg_sufficiency']:.2f}",
            "Avg counterfactual Δ": f"{suff['avg_counterfactual_delta']:.2f}",
        }
    )
    st.plotly_chart(charts.build_sufficiency_chart(samples), width="stretch")

    st.markdown("#### B2 — Counterevidence Coverage")
    cov = metrics.coverage_summary(samples)
    components.metric_row(
        {
            "Avg coverage": f"{cov['avg_coverage']:.2f}",
            "Tỉ lệ phát hiện counterevidence": f"{cov['detected_rate']:.1%}",
        }
    )
    st.plotly_chart(charts.build_coverage_chart(samples), width="stretch")

    st.markdown("#### B3 — Market Consistency + Regime")
    market = metrics.market_summary(samples)
    components.metric_row(
        {"Tỉ lệ market consistent": f"{market['consistency_rate']:.1%}"}
    )
    st.plotly_chart(charts.build_regime_chart(market["regimes"]), width="stretch")

    st.markdown("#### B4 — Agentic SDLC trace")
    entries = load_trace_log(TRACE_LOG_PATH)
    if not entries:
        st.info(
            f"Chưa có trace log tại `{TRACE_LOG_PATH}`. Tạo entry bằng "
            "`src.agent_trace.write_trace_entry` trong quá trình phát triển."
        )
        return
    summary = summarize_trace(entries)
    components.metric_row(
        {
            "Số entry": str(summary["total"]),
            "Quality gate pass": f"{summary['pass_rate']:.1%}",
            "Human accepted": str(summary.get("human_accepted", 0)),
        }
    )
    st.dataframe(pd.DataFrame(entries), width="stretch", hide_index=True)


def main() -> None:
    st.title("📈 Faithful Evidence-Centric Financial News Forecasting")
    st.caption(
        "Dashboard read-only trên envelope `outputs/08_market.json` — "
        "không gọi pipeline, không ghi file. Chỉ phục vụ học tập, "
        "không phải khuyến nghị đầu tư."
    )
    data = _load_or_stop()

    tabs = st.tabs(
        [
            "🎬 Live Demo",
            "📊 Overview",
            "📄 Evidence",
            "🔍 Faithfulness",
            "⏰ Temporal Leakage",
            "🧪 B-metrics",
        ]
    )
    with tabs[0]:
        render_live_demo(data)
    with tabs[1]:
        render_overview(data)
    with tabs[2]:
        render_evidence(data)
    with tabs[3]:
        render_faithfulness(data)
    with tabs[4]:
        render_leakage(data)
    with tabs[5]:
        render_b_metrics(data)


if __name__ == "__main__":  # streamlit run executes this file as __main__
    main()