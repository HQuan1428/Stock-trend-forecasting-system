# Tasks — enrich-evidence-keywords-v2

Ordered, single-session tasks. Each produces a verifiable artifact.

## 1. OpenSpec change scaffold

- [x] 1.1 Create `openspec/changes/enrich-evidence-keywords-v2/proposal.md` with Why / What Changes / Capabilities (MODIFIED `evidence-extractor`) / Impact.
- [x] 1.2 Create `openspec/changes/enrich-evidence-keywords-v2/tasks.md` (this file).
- [x] 1.3 Create the delta spec at `openspec/changes/enrich-evidence-keywords-v2/specs/evidence-extractor/spec.md` (copy of V1 spec with V2 keyword section, V2 coverage requirement, and V2 acceptance criterion added).

## 2. Source change

- [x] 2.1 Edit `src/evidence_extractor.py`: extend `EvidenceExtractor.POSITIVE_KEYWORDS` with V2 additions (V1 keywords retained).
- [x] 2.2 Edit `src/evidence_extractor.py`: extend `EvidenceExtractor.NEGATIVE_KEYWORDS` with V2 additions (V1 keywords retained).
- [x] 2.3 Verify `EvidenceExtractor.KEYWORD_TO_POLARITY` is rebuilt automatically (it already is — see lines 52-60 of `src/evidence_extractor.py`).
- [x] 2.4 Verify `KEYWORDS` is still `POSITIVE_KEYWORDS + NEGATIVE_KEYWORDS` (no edit needed).

## 3. Test updates

- [x] 3.1 Update `tests/test_evidence_extractor.py::test_positive_keywords_match_spec_vocabulary` to assert the V2 list.
- [x] 3.2 Update `tests/test_evidence_extractor.py::test_negative_keywords_match_spec_vocabulary` to assert the V2 list.
- [x] 3.3 Add `test_v2_extracts_positive_from_sample_up_sentence` (covers `Apple reports stronger than expected iPhone demand in India`).
- [x] 3.4 Add `test_v2_extracts_negative_from_sample_down_sentence_antitrust` (covers `Google faces a new antitrust complaint over search distribution deals`).
- [x] 3.5 Add `test_v2_extracts_positive_faster_growth` (covers `Meta announces faster growth in Reels advertising engagement`).
- [x] 3.6 Add `test_v2_extracts_negative_multi_keyword_warns_of` (covers `Apple supplier warns of softer iPhone component orders for next quarter`).
- [x] 3.7 Add `test_v2_extracts_positive_signs_a_contract` (covers `Google Cloud signs a large AI infrastructure contract with a bank`).
- [x] 3.8 Add `test_v2_extracts_negative_is_fined` (covers `Google is fined by a regulator for data retention practices`).
- [x] 3.9 Add `test_v2_hold_sentence_remains_neutral` (covers `Amazon keeps full year guidance unchanged after a mixed retail update`).
- [x] 3.10 Add `test_v2_has_mixed_evidence_when_both_polarities_match` (covers a synthetic sentence with both `raises guidance` and `lawsuit` to pin the mixed flag).

## 4. Verification

- [x] 4.1 Run `pytest tests/test_evidence_extractor.py -v` — all tests must pass.
- [x] 4.2 Run `pytest tests/ -q` — no regression in other modules (pipeline, forecast, faithfulness, selector, retriever, dashboard).
- [x] 4.3 Run `python -m src.pipeline --input data/sample_dataset.csv --output-dir outputs` to regenerate the four output CSVs.
- [x] 4.4 Verify `outputs/prediction_results.csv` no longer has 100% HOLD predictions — expected distribution roughly UP ≥ 30, DOWN ≥ 20, HOLD ≤ 50.
- [x] 4.5 Verify `outputs/faithfulness_results.csv` has at least one row with `faithfulness_label` in {`HIGH`, `MEDIUM`} (i.e. `confidence_drop ≥ 0.05` on at least one case).

## 5. Rollback

- [x] 5.1 Revert `src/evidence_extractor.py` to the V1 keyword lists (single edit).
- [x] 5.2 Revert the two updated test functions to their V1 assertions.
- [x] 5.3 Remove the 8 new tests.
- [x] 5.4 Re-run `python -m src.pipeline` to regenerate outputs in the V1 baseline.