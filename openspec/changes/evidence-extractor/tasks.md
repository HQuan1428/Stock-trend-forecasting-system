# Evidence Extractor — Implementation Tasks (Version 1)

Tasks are grouped by dependency order. Each task is small enough to complete in one session and produces a verifiable artifact.

## 1. Project structure & keyword dictionary

- [x] 1.1 Create the module file (`src/evidence_extractor.py`) and re-export the public API from `src/__init__.py`. *(Implemented as a single file per `AGENTS.md` §3, not a directory.)*
- [x] 1.2 Implement the Version 1 keyword dictionary as module-level constants: `EvidenceExtractor.POSITIVE_KEYWORDS`, `EvidenceExtractor.NEGATIVE_KEYWORDS`, and `EvidenceExtractor.KEYWORD_TO_POLARITY` (a flat dict mapping keyword → `"positive"` or `"negative"`).
- [x] 1.3 Implement the polarity-to-direction table `EvidenceExtractor.POLARITY_TO_DIRECTION` mapping `"positive" → "UP"`, `"negative" → "DOWN"`, `"neutral" → "HOLD"`.
- [x] 1.4 Add a `EvidenceExtractor.SUPPORT_SCORES` constant: `1.0` for keyword matches, `0.5` for the neutral fallback.
- [x] 1.5 Add a unit test asserting the dictionary contains exactly the Version 1 vocabulary and the polarity/direction tables match the spec.

## 2. Single-item extraction core

- [x] 2.1 Implement a private helper `_find_keyword_occurrences(news_text, keywords)` that lowercases `news_text` once, then for each keyword tries (a) exact substring matching via `str.find` and (b) token-level matching with a 15-char gap cap (so `"weak sales"` matches `"weak iPhone sales"`). Returns a list of `(start_char, end_char, keyword, polarity)` tuples.
- [x] 2.2 Implement a private helper `_resolve_overlaps(matches)` that sorts by `(-length, start_char)` (longest-match-wins, earliest on ties) and drops shorter matches that overlap a kept match.
- [x] 2.3 Implement `EvidenceExtractor.build_evidence_objects(news_id, news_text, matches)` that assigns deterministic `evidence_id` in the form `<news_id>_E<index>` (1-based, zero-padded to 3 digits, text-ordered) and builds the evidence dicts.
- [x] 2.4 Implement the neutral fallback: if the matches list is empty, return a single evidence dict with `polarity = "neutral"`, `expected_direction = "HOLD"`, `support_score = 0.5`, `matched_keyword = null`, and offsets `(0, 0)`.
- [x] 2.5 Implement `EvidenceExtractor.build_summary(evidence)` returning a summary dict with `positive_count`, `negative_count`, `neutral_count`, `total_evidence_count`, and `has_mixed_evidence` (true iff `positive_count >= 1` and `negative_count >= 1`).
- [x] 2.6 Implement `EvidenceExtractor.select_primary_evidence_id(evidence)` applying the Primary Evidence Rule (negative > positive > neutral; tie-break by smallest `start_char`).

## 3. Public API

- [x] 3.1 Implement `EvidenceExtractor.extract(news_item)` that returns a result dict with `news_id`, `ticker`, `forecast_time`, `news_time` preserved verbatim, `evidence`, `summary`, `extraction_method = "rule_based_keyword"`, and `primary_evidence_id`.
- [x] 3.2 Implement `EvidenceExtractor.extract_batch(news_items)` that returns a list of result dicts, one per input, in the same order. It MUST NOT filter or reorder items based on time.
- [x] 3.3 Implement a public `KEYWORDS` export combining the positive and negative lists, for downstream reuse.
- [x] 3.4 Add a small `result_to_dict(result)` helper so the public API is JSON-serializable without custom encoders.

## 4. Unit tests — acceptance criteria

- [x] 4.1 Test: positive-only news.
- [x] 4.2 Test: negative-only news (token-level match for `"weak iPhone sales"`).
- [x] 4.3 Test: neutral news.
- [x] 4.4 Test: mixed news — `has_mixed_evidence` and `primary_evidence_id`.
- [x] 4.5 Test: case-insensitive matching.
- [x] 4.6 Test: batch input of N items returns N result objects in the same order.
- [x] 4.7 Test: `forecast_time` and `news_time` are preserved verbatim.
- [x] 4.8 Test: future news is processed without error and timestamps are preserved.

## 5. Unit tests — edge cases

- [x] 5.1 Test: empty `news_text` returns exactly one neutral evidence object.
- [x] 5.2 Test: whitespace-only `news_text` returns exactly one neutral evidence object.
- [x] 5.3 Test: same keyword appearing at two non-overlapping positions returns two evidence objects in `start_char` order.
- [x] 5.4 Test: overlapping matches are resolved to the longest match.
- [x] 5.5 Test: determinism — byte-identical output on repeated calls.
- [x] 5.6 Test: each evidence object has all required fields.
- [x] 5.7 Test: result object has `extraction_method` and a `summary` with the five required keys.

## 6. Sample inputs/outputs and developer ergonomics

- [x] 6.1 Sample I/O fixtures for the five documented examples, created under `samples/evidence_extractor/`. Each pair (`_input.json` + `_expected.json`) is locked in by `test_golden_fixture_matches_extractor_output` in `tests/test_evidence_extractor.py`.
- [x] 6.2 Module docstring documents the public API, keyword dictionary, polarity-to-direction mapping, Primary Evidence Rule, the no-LLM/FinBERT scope, and cites the spec file.
- [x] 6.3 `README.md` has an "Evidence Extractor" section with single-item and batch examples, contract notes, the keyword-dictionary source-of-truth rule, and a pointer to the sample fixtures.

## 7. Integration hand-off (no implementation work in this change)

- [x] 7.1 Documented in `README.md` "Contract notes for downstream modules": the Evidence Selector consumes `result["evidence"]`, `result["summary"]`, and `result["primary_evidence_id"]` directly. No contract change required.
- [x] 7.2 Documented in `README.md` "Contract notes for downstream modules": the Temporal Retriever owns temporal validity; the Evidence Extractor MUST NOT be modified to filter by time. The same rule is enforced in the spec (Requirement: "No temporal filtering, no prediction, no advice") and in `src/evidence_extractor.py` (no time-parsing imports).
- [x] 7.3 Added a `# Single source of truth for polarity` docstring comment to `EvidenceExtractor.KEYWORD_TO_POLARITY` in `src/evidence_extractor.py`; future Counterevidence Coverage metrics MUST import from this module.
