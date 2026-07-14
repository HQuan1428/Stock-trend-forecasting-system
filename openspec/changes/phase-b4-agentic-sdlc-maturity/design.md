## Context

B4 yêu cầu minh chứng Agentic SDLC với ít nhất 3 agent role, trace log có cấu trúc, quality gate, và reflection. Toàn bộ Phase B (B1–B3) đã được thực hiện theo quy trình Agentic SDLC: Claude Code (AI agent) đảm nhận vai Research/Coding/Testing, con người (user) kiểm soát bằng cách review spec và approve. Cần capture lịch sử này vào một trace log có thể đọc được và render lên dashboard.

## Goals / Non-Goals

**Goals:**
- `src/agent_trace.py`: module đọc/ghi/tổng hợp `outputs/run_log.json`.
- `outputs/run_log.json`: seed data ghi lại ít nhất 6 trace entries bao phủ 3+ agent roles trong thực tế dự án.
- Dashboard tab "Agentic SDLC" hiển thị trace log table, quality gate pass rate, và reflection.
- `reflection.md` ghi lại AI đã làm gì và con người kiểm soát như thế nào.

**Non-Goals:**
- Không auto-append trace entry khi pipeline chạy (manual seed là đủ cho prototype).
- Không authentication/authorization cho trace log.
- Không thay đổi bất kỳ pipeline output CSV cũ.

## Decisions

**D1 — Trace log format: JSON array, append-safe**

```json
[
  {
    "run_id": "R001",
    "timestamp": "2026-06-27T00:00:00",
    "agent_role": "Research Agent",
    "task": "Analyze faithfulness metric gaps for B1/B2/B3",
    "input": "openspec/changes/, src/faithfulness_evaluator.py",
    "output": "proposal.md + design.md for each change",
    "human_review": "accepted",
    "quality_gate": "passed",
    "notes": ""
  }
]
```

6 required fields: `run_id`, `agent_role`, `task`, `output`, `human_review`, `quality_gate`. `timestamp`, `input`, `notes` optional.

**D2 — 3 agent roles (bắt buộc theo tiêu chí B4)**

1. **Research Agent** — phân tích bài toán, viết OpenSpec proposal + design (bước `/opsx:propose`)
2. **Coding Agent** — implement module theo spec (bước `/opsx:apply`)
3. **Testing/Review Agent** — viết test cases, verify output, review code quality

Mỗi Phase (B1/B2/B3/B4) sẽ có ít nhất 1 entry per agent role → minimum 9–12 entries trong seed.

**D3 — `write_trace_entry()` append-safe**

```python
def write_trace_entry(entry: dict, path: str = "outputs/run_log.json") -> None
```
Đọc file hiện tại (hoặc `[]` nếu missing), append entry, ghi lại. Thread-safe không cần thiết ở scale prototype.

**D4 — `summarize_trace()` trả về stats dict**

```python
{
    "total": int,
    "passed_quality_gates": int,
    "failed_quality_gates": int,
    "pass_rate": float,   # passed / total
    "roles": {"Research Agent": N, "Coding Agent": N, ...},
    "human_accepted": int,
    "human_rejected": int,
}
```

**D5 — Dashboard: đọc `run_log.json` từ output_dir, không fail khi thiếu**

`load_agent_trace(output_dir)` trả về `list[dict]` — `[]` khi file missing. `DashboardData` thêm field `agent_trace: list`.

**D6 — reflection.md là documentation artifact, không phải code**

Ghi trong thư mục change (`openspec/changes/phase-b4-agentic-sdlc-maturity/reflection.md`). Dashboard render nội dung dạng markdown (hardcoded text tóm tắt).

## Risks / Trade-offs

**[Risk] Trace log là seed manual, không reflect real-time** → Acceptable cho prototype. Label rõ "pre-seeded trace log" trong dashboard.

**[Risk] `write_trace_entry()` không atomic** → Acceptable ở scale prototype (single process).

**[Risk] Dashboard hiển thị reflection text cứng thay vì đọc từ file** → Chọn text cứng để tránh dependency vào path file MD; dễ maintain hơn cho prototype.
