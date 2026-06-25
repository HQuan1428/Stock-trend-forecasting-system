# Evidence Extractor — Design (Version 1)

## Context

The Faithful Evidence-Centric Financial News Forecasting pipeline ingests news and price data, runs the Temporal Retriever, then needs a deterministic way to surface the exact phrases inside each news item that should drive a forecast. Faithfulness evaluation (a downstream concern) requires the model to point to specific, auditable evidence, which means the extractor must preserve character offsets, polarity, and the full evidence list — not collapse a news item into a single label.

Version 1 is intentionally minimal: a hard-coded keyword dictionary, case-insensitive substring search, deterministic IDs, and a summary block. No LLM, no FinBERT, no transformer, no NER, no learned scoring. This keeps the module testable, fast, free of large model dependencies, and easy to reason about in audits. The design below makes the keyword list and matching rules explicit so that the module can be extended later (e.g., to support Counterevidence Coverage metrics) without breaking the public contract.

## Goals / Non-Goals

**Goals**
- Provide a deterministic `extract_evidence(news_item)` function that returns every positive and negative keyword match plus a neutral fallback.
- Produce a stable per-news result object whose `evidence` list is in text order and includes character offsets, polarity, expected direction, matched keyword, and `support_score`.
- Generate deterministic evidence IDs in the form `<news_id>_E<index>` so downstream tests and audits can reference evidence by ID.
- Emit a per-news `summary` block (positive/negative/neutral counts and `has_mixed_evidence`) without dropping any evidence.
- Provide a `primary_evidence_id` field chosen by a fixed priority rule (negative > positive > neutral, then earliest in text) so the rest of the pipeline has a stable default anchor.
- Provide `extract_evidence_batch(news_items)` that returns one result per input item, preserving `forecast_time` and `news_time`.
- Be fully testable with unit tests that cover the eight acceptance scenarios in the proposal and spec.

**Non-Goals**
- LLM-based extraction, FinBERT, transformer models, or any external NLP model.
- Named entity recognition, dependency parsing, or part-of-speech tagging.
- Generating multi-sentence rationales or natural-language explanations.
- Producing the final forecast or price prediction.
- Temporal filtering (the Temporal Retriever owns this).
- Trading advice, buy/sell recommendations, or any portfolio action.
- Learned scoring, weighted sentiment, or confidence calibration beyond the binary `support_score` (`1.0` for keyword matches, `0.5` for neutral).

## Decisions

### Decision 1 — Hard-coded keyword dictionary, not a learned lexicon
- **Choice:** A Python constant mapping polarity to a list of lowercase phrases, plus an inverse lookup `keyword → polarity`.
- **Why:** Deterministic, auditable, and easy to extend. A learned lexicon would require training data, a model artifact, and version pinning that Version 1 does not need.
- **Alternatives considered:**
  - YAML/JSON dictionary file: rejected for V1 to keep the module a single self-contained file with no I/O on the hot path.
  - Regular-expression patterns: rejected because V1 keywords are simple substrings; regex power is unnecessary and makes offsets harder to reason about.

### Decision 2 — Case-insensitive token-level matching with longest-match-wins on overlap
- **Choice:** Lowercase `news_text` once. For each keyword, first try **exact substring matching** via `str.find`. If a multi-word keyword has no exact match, fall back to **token-level matching**: split the keyword into words, find each word's positions, and accept a window where the words appear in order with a **gap of at most 15 characters** between consecutive keyword words (about 2–3 English words). The match span is from the first word's start to the last word's end. This lets `"weak sales"` match `"weak iPhone sales"` and produce `evidence_text = "weak iPhone sales"`, satisfying acceptance criterion 1 without changing the keyword vocabulary.
- **Why:** Matches the spec's case-insensitive rule, the "all matches in text order" rule, the "longest match on overlap" rule, AND acceptance criterion 1's "evidence_text containing 'weak iPhone sales' or 'weak sales'". The 15-char gap is wide enough to absorb a single noun modifier (e.g., "iPhone", "cloud", "Q3") and narrow enough to avoid unrelated words bridging. The spec's evidence_text field explicitly allows "a short surrounding phrase if the implementation chooses to expand the slice", so this expansion is in-scope.
- **Overlap resolution:** When matches overlap, keep the **longest** match. Ties broken by **earliest start_char**. Implementation sorts by `(-length, start_char)` and walks, keeping a match only if it does not overlap any already-kept match. The final list is re-sorted by ascending `start_char` for stable text order.
- **Alternatives considered:**
  - Pure exact substring matching: rejected because it fails acceptance criterion 1 ("weak iPhone sales" does not contain "weak sales" as a contiguous substring).
  - Regex alternation `(kw1|kw2|...)` with longest-match preference: works for exact matches but obscures per-keyword offsets and complicates test assertions; the token-level fallback is clearer and keeps offsets simple.
  - Whole-word boundaries (`\b`): not required by the spec and would over-restrict phrases like "raises guidance" that have no boundary ambiguity; can be added later without breaking the public contract.
  - Lemmatization or stemming: out of scope for V1 (proposal: "no learned scoring, lemmatization, or stemming").

### Decision 3 — Preserve all evidence; choose `primary_evidence_id` separately
- **Choice:** The `evidence` list always contains every non-overlapping match plus the neutral fallback. `primary_evidence_id` is a convenience field that selects one evidence using a fixed priority (negative > positive > neutral; ties broken by earliest `start_char`).
- **Why:** Downstream modules (Evidence Selector, Counterevidence Coverage) need the full list to identify pro and counter evidence. The primary ID exists only as a stable default anchor — it never causes other evidence to be dropped.
- **Alternatives considered:**
  - Returning only the primary evidence: rejected, because it would hide counterevidence and break faithfulness.
  - Returning the primary evidence with a count of others: rejected, because downstream code needs the actual evidence objects, not just a count.

### Decision 4 — `support_score` as a binary constant per polarity
- **Choice:** `1.0` for positive/negative keyword matches, `0.5` for the neutral/no-match fallback.
- **Why:** Version 1 has no learned confidence. A binary score keeps the contract stable and makes downstream code trivial to reason about. Future versions can replace this with a calibrated score without changing the field name.
- **Alternatives considered:**
  - Keyword-specific scores (e.g., "lawsuit" = 0.9, "recall" = 0.95): rejected for V1 — adds hyperparameters without evidence in V1.
  - Per-match frequency scaling: rejected — would conflate coverage with confidence.

### Decision 5 — Output schema is a plain Python `dict` (or dataclass) per result
- **Choice:** Each result is a plain dict (or a frozen dataclass that `to_dict()`-s to the same shape) with the exact field names required by the spec: `news_id`, `ticker`, `forecast_time`, `news_time`, `evidence`, `summary`, `extraction_method`, plus optional `primary_evidence_id`.
- **Why:** Matches the JSON example in the spec exactly, which keeps the contract with downstream modules unambiguous. A dataclass gives type safety in tests; the dict form keeps JSON serialization trivial.
- **Alternatives considered:**
  - Pydantic models: useful but adds a runtime dependency; deferred until the rest of the pipeline adopts a shared schema library.
  - TypedDict: a fine option inside the implementation, but the public contract remains the JSON shape.

### Decision 6 — `extract_evidence_batch` is a thin loop, not a parallel map
- **Choice:** `extract_evidence_batch` iterates over input items and calls `extract_evidence` on each, returning a list of result dicts in input order.
- **Why:** The function is pure and CPU-light; parallelism adds complexity (pickling, error handling, ordering) without measurable benefit at expected batch sizes.
- **Alternatives considered:**
  - `concurrent.futures.ProcessPoolExecutor`: premature optimization for V1; can be layered in later if profiling shows a bottleneck.

### Decision 7 — No temporal filtering inside the extractor
- **Choice:** The extractor never inspects `forecast_time` vs `news_time` and never drops an item based on time. It preserves both fields verbatim in the output.
- **Why:** The Temporal Retriever is the single owner of temporal validity. Letting the extractor also filter would create two sources of truth and complicate audits.
- **Alternatives considered:**
  - A "soft warning" if `news_time > forecast_time`: rejected — even warnings would be a side effect; temporal correctness is a hard contract owned upstream.

## Risks / Trade-offs

- [Risk] The keyword dictionary is small and brittle to paraphrase (e.g., "topped estimates" is not in V1). → Mitigation: dictionary lives in a single constant with a docstring, and the spec explicitly lists the Version 1 vocabulary so coverage is auditable. Extension is a deliberate, versioned change.
- [Risk] Substring matching can yield false positives inside unrelated phrases (e.g., "decline" inside "decline in volatility"). → Mitigation: documented in the spec as a known V1 limitation; whole-word boundary support is listed as a future extension without changing the public contract. Token-level matching with a 15-char gap allowance introduces a second source of false positives (e.g., "weak quarterly sales" could match the keyword "weak sales" if "quarterly" happens to be short enough). → Mitigation: gap cap is bounded (15 chars), the token-level fallback only fires when the exact substring is absent, and a regression test pins the current behavior.
- [Risk] Determinism depends on the keyword list, the token-level fallback rule, and the longest-match-wins rule being applied consistently. → Mitigation: rules are codified in two helpers (`_find_keyword_occurrences`, `_resolve_overlaps`) and unit-tested with both exact-match and token-level-match fixtures.
- [Risk] Adding new keywords later could shift `evidence_id` values if the order changes. → Mitigation: IDs are assigned in the final text-ordered list, so adding a keyword that appears *later* in the same news item will not renumber earlier evidence; only items after the new match get a new suffix. This is documented behavior.
- [Risk] Two modules might disagree about polarity for the same phrase. → Mitigation: polarity is decided solely by the dictionary; the spec names polarity and direction mapping explicitly so other modules can import the same source of truth.

## Migration Plan

- Step 1: Land the keyword dictionary and `extract_evidence` function behind unit tests. No existing pipeline code consumes the module yet, so there is no migration risk.
- Step 2: Land `extract_evidence_batch` and example I/O fixtures in the project `samples/` directory (or equivalent) so the Temporal Retriever and the rest of the pipeline can be wired in incrementally.
- Step 3: When the Evidence Selector is implemented, it imports the dictionary and helper from this module rather than redefining polarity rules.
- Rollback: removing the module is a single git revert; no data migration, no schema migration in downstream storage.

## Open Questions

- Should `primary_evidence_id` always be emitted, or only when at least one keyword matches? Current plan: always emit (neutral evidence when no keywords match) so downstream code can assume the field is present.
- Should the keyword list be exposed as a module-level constant for reuse by the Evidence Selector and Counterevidence Coverage metric? Current plan: yes, expose `POSITIVE_KEYWORDS` and `NEGATIVE_KEYWORDS` lists and a `KEYWORD_TO_POLARITY` dict.
- Will future versions need per-keyword weights? Current plan: out of scope for V1; the `support_score` field is the extension point.
