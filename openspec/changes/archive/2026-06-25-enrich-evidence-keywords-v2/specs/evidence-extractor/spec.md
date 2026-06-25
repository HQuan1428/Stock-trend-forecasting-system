# Evidence Extractor — Spec (Version 2 delta)

This delta spec **MODIFIES** `evidence-extractor` to add a Version 2 keyword dictionary. It inherits every Version 1 requirement from `openspec/specs/evidence-extractor/spec.md` (input/output schema, polarity-to-direction mapping, primary-evidence rule, case-insensitive matching, overlap resolution, neutral fallback, deterministic IDs, batch API, no-temporal-filtering, no-prediction, no-advice). The text below only documents the **additions and replacements**. Anything not explicitly replaced here continues to be governed by the V1 spec.

---

## MODIFIED Requirements

### Requirement: Keyword Dictionary (Version 2) — *replaces the V1 "Keyword Dictionary" section*

The Version 2 keyword set is a **superset** of Version 1: every V1 keyword is retained, and new multi-word phrases are appended. The dictionary is still fixed and auditable as a module-level constant.

**Positive keywords (polarity = `positive`, expected direction = `UP`)** — V1 entries are listed first, V2 additions are appended after:

- V1 (retained): `beats expectations`, `record profit`, `strong sales`, `raises guidance`, `launches new product`
- V2 additions: `stronger than expected`, `faster growth`, `positive analyst`, `wins a`, `signs a`, `accelerates`, `revenue record`, `approves expansion`, `approval to expand`, `expands`, `rises faster than expected`, `subscription growth`

**Negative keywords (polarity = `negative`, expected direction = `DOWN`)** — V1 entries are listed first, V2 additions are appended after:

- V1 (retained): `misses expectations`, `weak sales`, `recall`, `lawsuit`, `cuts guidance`, `decline`
- V2 additions: `antitrust complaint`, `softer orders`, `slower growth`, `warns of`, `warns that`, `faces a`, `is fined`, `fined for`, `delays production`, `lowers outlook`, `outage`, `probe into`, `regulatory costs`, `downgraded`, `strikes`, `vote to authorize a strike`, `privacy case`

**Neutral fallback** — unchanged: when no positive or negative keyword matches, the extractor MUST emit exactly one evidence object with `polarity = "neutral"`, `expected_direction = "HOLD"`, `support_score = 0.5`, `matched_keyword = null`.

#### Scenario: V1 keyword still matches under V2
- **GIVEN** an input news item with `news_text = "Microsoft MISSES EXPECTATIONS in cloud revenue"`
- **WHEN** the Evidence Extractor processes the item
- **THEN** the result contains an evidence object with `matched_keyword = "misses expectations"`, `polarity = "negative"`, and `expected_direction = "DOWN"`

#### Scenario: V2 keyword matches where V1 had none
- **GIVEN** an input news item with `news_text = "Apple reports stronger than expected iPhone demand in India"`
- **WHEN** the Evidence Extractor processes the item
- **THEN** the result contains at least one evidence object with `matched_keyword = "stronger than expected"`, `polarity = "positive"`, and `expected_direction = "UP"`

---

### Requirement: V2 keyword coverage on the project sample — *new*

The system SHALL emit at least one positive/negative evidence object (i.e. NOT the neutral fallback) for any sample sentence that obviously conveys direction — concretely, the four representative UP/DOWN sentences enumerated in the four normative scenarios below.

#### Scenario: UP sentence "stronger than expected"
- **GIVEN** an input news item with `news_text = "Apple reports stronger than expected iPhone demand in India"`
- **WHEN** the Evidence Extractor processes the item
- **THEN** the result contains at least one positive evidence object with `expected_direction = "UP"`
- **AND** `summary.positive_count >= 1`
- **AND** `summary.negative_count = 0`
- **AND** `summary.has_mixed_evidence = false`

#### Scenario: DOWN sentence "antitrust complaint"
- **GIVEN** an input news item with `news_text = "Google faces a new antitrust complaint over search distribution deals"`
- **WHEN** the Evidence Extractor processes the item
- **THEN** the result contains at least one negative evidence object with `expected_direction = "DOWN"`
- **AND** `summary.negative_count >= 1`
- **AND** `summary.positive_count = 0`

#### Scenario: DOWN sentence "warns of softer … orders"
- **GIVEN** an input news item with `news_text = "Apple supplier warns of softer iPhone component orders for next quarter"`
- **WHEN** the Evidence Extractor processes the item
- **THEN** the result contains at least one negative evidence object (matched via either `warns of` or `softer orders`) with `expected_direction = "DOWN"`
- **AND** `summary.negative_count >= 1`

#### Scenario: DOWN sentence "is fined by a regulator"
- **GIVEN** an input news item with `news_text = "Google is fined by a regulator for data retention practices"`
- **WHEN** the Evidence Extractor processes the item
- **THEN** the result contains at least one negative evidence object with `expected_direction = "DOWN"`

---

### Requirement: V2 must NOT regress HOLD-style sentences — *new*

The system MUST continue to return the neutral fallback for genuinely directionless sentences. Adding V2 keywords SHALL NOT cause previously-neutral sentences to become falsely directional.

#### Scenario: HOLD sentence with "guidance" but no V1/V2 directional anchor
- **GIVEN** an input news item with `news_text = "Amazon keeps full year guidance unchanged after a mixed retail update"`
- **WHEN** the Evidence Extractor processes the item
- **THEN** the result contains exactly one evidence object with `polarity = "neutral"`, `expected_direction = "HOLD"`, `support_score = 0.5`, and `matched_keyword = null`
- **AND** `summary.neutral_count = 1`

---

## MODIFIED Acceptance Criteria

The Version 1 acceptance criteria (1, 3, 4, 5, 6, 7, 8) are unchanged. Version 2 adds the following criterion, which MUST be verified by a unit test:

9. **V2 coverage.** Given a sample sentence whose direction is unambiguous (any of the four UP/DOWN scenarios listed in the *V2 keyword coverage* requirement), the result MUST contain at least one positive or negative evidence object whose `expected_direction` matches the label direction.

---

## ADDED Test Scenarios

The Version 1 test scenario list (15 items) is unchanged. Version 2 adds the following tests, each pinned to a real sample sentence:

16. `stronger than expected` (UP) produces at least one positive evidence object.
17. `antitrust complaint` (DOWN) produces at least one negative evidence object.
18. `faster growth` (UP) produces at least one positive evidence object.
19. `warns of softer … orders` (DOWN) produces at least one negative evidence object (matched via either keyword).
20. `signs a … contract` (UP) produces at least one positive evidence object.
21. `is fined` (DOWN) produces at least one negative evidence object.
22. `keeps full year guidance unchanged` (HOLD) remains a single neutral evidence object — V2 keywords MUST NOT mis-classify this as directional.
23. A synthetic sentence with both `raises guidance` and `lawsuit` (one positive, one negative) yields `summary.has_mixed_evidence = true`.

---

## Out of Scope (Version 2)

Version 2 explicitly does **not** introduce:

- LLM-based extraction, FinBERT, transformer-based sentiment, or any external NLP model.
- Named entity recognition, dependency parsing, or part-of-speech tagging.
- Multi-sentence rationale generation or natural-language explanation.
- Final forecast prediction, price prediction, or movement direction (owned by the Forecast Model).
- Temporal filtering or temporal validity checks (owned by the Temporal Retriever).
- Trading advice, buy/sell recommendations, or any portfolio action.
- Learned scoring, calibrated confidence, or per-keyword weights beyond the binary `support_score`.
- Whole-word boundary enforcement, lemmatization, or stemming.
- Per-keyword domain adaptation or ticker-specific dictionaries.

The V1 keyword set is retained verbatim — V2 is a strict superset. The V1 acceptance criteria, test scenarios, edge cases, and primary-evidence rule remain normative.