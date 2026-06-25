# Tasks — enrich-evidence-keywords-v3

Ordered, single-session tasks. Each produces a verifiable artifact.

## 1. OpenSpec change scaffold

- [x] 1.1 Create `openspec/changes/enrich-evidence-keywords-v3/proposal.md` with Why / What Changes / Capabilities (MODIFIED `evidence-extractor`) / Impact.
- [x] 1.2 Create `openspec/changes/enrich-evidence-keywords-v3/tasks.md` (this file).
- [x] 1.3 Create the delta spec at `openspec/changes/enrich-evidence-keywords-v3/specs/evidence-extractor/spec.md` (delta of the V2 spec with V3 keyword section, V3 coverage requirement, and V3 acceptance criterion added).

## 2. Source change

- [x] 2.1 Edit `src/evidence_extractor.py`: extend `POSITIVE_KEYWORDS` with 21 V3 additions (V1 and V2 keywords retained).
- [x] 2.2 Edit `src/evidence_extractor.py`: extend `NEGATIVE_KEYWORDS` with 16 V3 additions (V1 and V2 keywords retained).
- [x] 2.3 Update the version-3 module docstring comment to point at the new change folder.
- [x] 2.4 Verify `KEYWORD_TO_POLARITY` is rebuilt automatically (it already is — see lines 98-110 of `src/evidence_extractor.py`).
- [x] 2.5 Verify `KEYWORDS` is still `POSITIVE_KEYWORDS + NEGATIVE_KEYWORDS` (no edit needed).

## 3. Test updates

- [x] 3.1 Update `tests/test_evidence_extractor.py::test_positive_keywords_match_spec_vocabulary` to assert the V3 list.
- [x] 3.2 Update `tests/test_evidence_extractor.py::test_negative_keywords_match_spec_vocabulary` to assert the V3 list.
- [x] 3.3 Add `test_v3_extracts_positive_from_softer_up_sentence_expands`.
- [x] 3.4 Add `test_v3_extracts_positive_from_softer_up_sentence_stronger`.
- [x] 3.5 Add `test_v3_extracts_positive_improvement_program`.
- [x] 3.6 Add `test_v3_extracts_positive_cost_efficient`.
- [x] 3.7 Add `test_v3_extracts_negative_warns_short_form`.
- [x] 3.8 Add `test_v3_extracts_negative_softer_shorter_form`.
- [x] 3.9 Add `test_v3_extracts_negative_weaker_mac`.
- [x] 3.10 Add `test_v3_extracts_negative_permitting_issues`.
- [x] 3.11 Add `test_v3_extracts_negative_outage_in`.
- [x] 3.12 Add `test_v3_hold_sentence_still_remains_neutral` (regression — V3 keywords must not flip a HOLD sentence to UP/DOWN).
- [x] 3.13 Add `test_v3_hold_sentence_in_line_with_plan_still_neutral` (regression — `receives` must not match this HOLD).

## 4. Verification

- [x] 4.1 Run `pytest tests/test_evidence_extractor.py -v` — all tests must pass.
- [x] 4.2 Run `pytest tests/ -q` — no regression in other modules (pipeline, forecast, faithfulness, selector, retriever, dashboard).
- [x] 4.3 Run `python -m src.pipeline --input data/sample_dataset.csv --output-dir outputs` to regenerate the four output CSVs.
- [x] 4.4 Verify `outputs/prediction_results.csv` HOLD count is significantly lower than the V2 baseline of 78 — target HOLD ≤ 45 (close to the true 27-HOLD floor, with some residual false-HOLDs).
- [x] 4.5 Verify `is_correct` accuracy improves over the V2 baseline of 49% — target ≥ 60%.
- [x] 4.6 Verify `outputs/faithfulness_results.csv` still has HIGH cases (V3 must not regress faithfulness).

## 5. Rollback

- [x] 5.1 Revert `src/evidence_extractor.py` keyword lists to V2 (single edit).
- [x] 5.2 Revert the two updated test functions to their V2 assertions.
- [x] 5.3 Remove the 9 new V3 tests.
- [x] 5.4 Re-run `python -m src.pipeline` to regenerate outputs in the V2 baseline.