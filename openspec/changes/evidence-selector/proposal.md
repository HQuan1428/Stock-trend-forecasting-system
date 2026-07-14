## Why

The Faithful Evidence-Centric Financial News Forecasting pipeline produces a prediction (UP / DOWN / HOLD) and a list of evidence candidates from the Evidence Extractor, but Version 1 has no module that classifies each candidate as **pro**, **counter**, or **neutral** relative to the current prediction. Without this classification, the system can only show "all evidence" or "evidence supporting the prediction" — both produce one-sided explanations that hide conflicting signals and make faithfulness evaluation impossible. The Evidence Selector is the missing link that turns raw evidence candidates into a balanced, auditable evidence set and exposes a `counterevidence_ratio` metric that downstream Faithfulness Evaluator and Dashboard modules can use to detect one-sided explanations.

## What Changes

- Add a new module `src/evidence_selector.py` exposing `EvidenceSelector.select(prediction, evidence_candidates, ...)` (and an equivalent batch helper) that classifies each evidence candidate into one of three groups: `pro_evidence`, `counterevidence`, `neutral_evidence`.
- Define a deterministic, rule-based classification mapping keyed on `(prediction, expected_direction)`. Version 1 does **not** use LLM, FinBERT, or any learned model.
- Define a ranking strategy that sorts each group by `selector_score` descending. For V1, `selector_score = extractor_score` (an extension point is documented for `extractor_score * keyword_strength * recency_weight`).
- Define a per-prediction `summary` block with `pro_count`, `counter_count`, `neutral_count`, `has_counterevidence`, and `counterevidence_ratio`.
- Define a `invalid_future_evidence` list that flags (but does not silently drop) any evidence item whose `news_time > forecast_time`. The Temporal Retriever normally prevents this from happening, but the Evidence Selector MUST defend in depth and surface the violation rather than letting it pollute the pro/counter/neutral groups.
- Define a `top_k` configuration per group (defaults: `top_k_pro=3`, `top_k_counter=3`, `top_k_neutral=3`) so the dashboard can cap the size of each evidence table.
- Add acceptance criteria and unit tests covering all nine cells of the classification matrix, the HOLD edge case, empty input, ranking order, future-evidence flagging, and label-leakage protection.
- Add documentation and sample I/O fixtures for UP / DOWN / HOLD predictions.

## Capabilities

### New Capabilities

- `evidence-selector`: Rule-based classification of evidence candidates relative to a forecast prediction. Groups items into pro, counter, and neutral sets using a fixed `(prediction, expected_direction) → selector_label` table; ranks each group by `selector_score` descending; exposes summary counts, `counterevidence_ratio`, and an explicit `invalid_future_evidence` list. Version 1 does not use ML or external NLP.

### Modified Capabilities

_None._ This change introduces a new capability and does not modify the requirements of existing specs. (The Temporal Retriever and Evidence Extractor specs are unaffected; the Selector consumes their outputs and never re-implements their responsibilities.)

## Impact

- New code area: `src/evidence_selector.py` (single-file module), re-exported from `src/__init__.py`.
- New spec area: `openspec/changes/evidence-selector/specs/evidence-selector/spec.md`; once archived, `openspec/specs/evidence-selector/spec.md`.
- New tests: `tests/test_evidence_selector.py` covering the nine classification cells, ranking, summary metrics, empty input, future-evidence flagging, label-leakage protection, and field preservation.
- New sample data: `samples/evidence_selector/` with at least three `_input.json` / `_expected.json` pairs (UP, DOWN, HOLD predictions).
- Downstream consumers: Faithfulness Evaluator and Visualization Dashboard will consume the per-prediction result object defined here. They MUST import the selector's classification rules rather than redefining them.
- Pipeline contract: the Temporal Retriever owns temporal validity; the Evidence Extractor owns per-phrase evidence; the Evidence Selector owns (prediction, evidence) classification. The selector MUST NOT re-implement temporal filtering or re-extract evidence from raw news text.
- No external dependencies, no model downloads, no GPU, no network access required at runtime.
