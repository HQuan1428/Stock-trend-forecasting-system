# Evidence Extractor — Spec (Version 3 delta)

This delta spec **MODIFIES** `evidence-extractor` to add a Version 3 keyword dictionary. It inherits every Version 1 and Version 2 requirement from the upstream specs (input/output schema, polarity-to-direction mapping, primary-evidence rule, case-insensitive matching, overlap resolution, neutral fallback, deterministic IDs, batch API, no-temporal-filtering, no-prediction, no-advice, V2 keyword coverage, V2 acceptance criterion 9). The text below only documents the **additions**. Anything not explicitly replaced here continues to be governed by the V1 and V2 specs.

---

## MODIFIED Requirements

### Requirement: Keyword Dictionary (Version 3) — *extends the V2 "Keyword Dictionary" section*

The Version 3 keyword set is a **superset** of Version 2: every V1 and V2 keyword is retained, and new entries are appended. The dictionary is still fixed and auditable as a module-level constant.

**Positive keywords (polarity = `positive`, expected direction = `UP`)** — V1 entries are listed first, V2 additions follow, V3 additions are appended last:

- V1 (retained): `beats expectations`, `record profit`, `strong sales`, `raises guidance`, `launches new product`
- V2 (retained): `stronger than expected`, `faster growth`, `positive analyst`, `wins a`, `signs a`, `accelerate`, `record level`, `raises shipment outlook`
- V3 additions: `launches`, `expands`, `improvement`, `stronger`, `secures`, `receives`, `praise`, `preorders`, `cost efficient`, `backlog expands`, `advertiser retention`, `adoption`, `introduces`, `accelerated`, `better conversion`, `carrier partnership`, `upgrade`, `automation`, `advertising marketplace`, `supply agreement`, `demand from`

**Negative keywords (polarity = `negative`, expected direction = `DOWN`)** — V1 entries are listed first, V2 additions follow, V3 additions are appended last:

- V1 (retained): `misses expectations`, `weak sales`, `recall`, `lawsuit`, `cuts guidance`, `decline`
- V2 (retained): `antitrust complaint`, `softer orders`, `slower growth`, `warns of`, `warns that`, `faces a`, `is fined`, `fined for`, `delays production`, `lowers outlook`, `outage`, `probe into`, `regulatory costs`, `downgraded`, `vote to authorize a strike`, `complaint`, `delays`, `cuts the price`, `budget cuts`, `complain about`, `losses widen`, `loses an appeal`, `overheating`, `lowers revenue guidance`
- V3 additions: `warns`, `slower`, `softer`, `weaker`, `lower`, `reduced`, `reduces`, `class action`, `criticism`, `pauses`, `delivery delays`, `fresh lawsuit`, `outage in`, `permitting`, `delays a planned`, `downgrade`

**Neutral fallback** — unchanged: when no positive or negative keyword matches, the extractor MUST emit exactly one evidence object with `polarity = "neutral"`, `expected_direction = "HOLD"`, `support_score = 0.5`, `matched_keyword = null`.

---

### Requirement: V3 keyword coverage on the project sample — *new*

The system SHALL emit at least one positive/negative evidence object (i.e. NOT the neutral fallback) for the five representative V3 sample sentences enumerated in the four normative scenarios below.

#### Scenario: UP sentence "expands … features"
- **GIVEN** an input news item with `news_text = "Google expands Gemini features for enterprise productivity customers"`
- **WHEN** the Evidence Extractor processes the item
- **THEN** the result contains at least one positive evidence object with `expected_direction = "UP"`

#### Scenario: UP sentence "stronger advertiser retention"
- **GIVEN** an input news item with `news_text = "Meta reports stronger advertiser retention among small businesses"`
- **WHEN** the Evidence Extractor processes the item
- **THEN** the result contains at least one positive evidence object via the V3 keyword `stronger` with `expected_direction = "UP"`

#### Scenario: DOWN sentence "weaker Mac shipments"
- **GIVEN** an input news item with `news_text = "Apple reports weaker Mac shipments in a supply chain channel check"`
- **WHEN** the Evidence Extractor processes the item
- **THEN** the result contains at least one negative evidence object via the V3 keyword `weaker` with `expected_direction = "DOWN"`

#### Scenario: DOWN sentence "permitting issues"
- **GIVEN** an input news item with `news_text = "Google delays a planned cloud region because of permitting issues"`
- **WHEN** the Evidence Extractor processes the item
- **THEN** the result contains at least one negative evidence object via the V3 keyword `permitting` with `expected_direction = "DOWN"`

---

### Requirement: V3 must NOT regress HOLD-style sentences — *new*

The system MUST continue to return the neutral fallback for genuinely directionless sentences that contain the substring of a V3 short keyword but where the surrounding context is neutral. The two regression scenarios are normative.

#### Scenario: HOLD sentence with "regular security patch" (no V3 match)
- **GIVEN** an input news item with `news_text = "Apple issues a regular security patch for iOS devices"`
- **WHEN** the Evidence Extractor processes the item
- **THEN** the result contains exactly one evidence object with `polarity = "neutral"`, `expected_direction = "HOLD"`, `support_score = 0.5`, and `matched_keyword = null`

#### Scenario: HOLD sentence with "in line with plan" (substring of `receives` would false-match if widened; V3 must not flip)
- **GIVEN** an input news item with `news_text = "Google says Android licensing revenue remains in line with plan"`
- **WHEN** the Evidence Extractor processes the item
- **THEN** the result contains exactly one evidence object with `polarity = "neutral"`, `expected_direction = "HOLD"`, `support_score = 0.5`, and `matched_keyword = null`

---

## MODIFIED Acceptance Criteria

The V1 acceptance criteria (1, 3, 4, 5, 6, 7, 8) and the V2 acceptance criterion (9) are unchanged. Version 3 adds the following criterion, which MUST be verified by a unit test:

10. **V3 coverage.** Given a sample sentence whose direction is unambiguous (any of the V3 scenarios listed in the *V3 keyword coverage* requirement), the result MUST contain at least one positive or negative evidence object whose `expected_direction` matches the label direction.

11. **V3 no-regression on HOLD.** Given a HOLD sample sentence that contains the substring of a V3 short keyword in a non-directional context (any of the V3 HOLD regression scenarios), the result MUST remain a single neutral evidence object.

---

## ADDED Test Scenarios

The V1 test scenario list (15 items) and the V2 test scenario list (8 items) are unchanged. Version 3 adds the following tests, each pinned to a real sample sentence:

24. `expands … features` (UP) produces at least one positive evidence object.
25. `stronger advertiser retention` (UP) produces at least one positive evidence object via the short keyword `stronger`.
26. `improvement program` (UP) produces at least one positive evidence object via the keyword `improvement`.
27. `cost efficient AI chips` (UP) produces at least one positive evidence object via the multi-word keyword `cost efficient`.
28. `warns that … may limit` (DOWN) is classified DOWN via either V2's `warns that` or V3's `warns` keyword.
29. `slower conversion rates` (DOWN) produces at least one negative evidence object via the short keyword `slower`.
30. `weaker Mac shipments` (DOWN) produces at least one negative evidence object via the short keyword `weaker`.
31. `permitting issues` (DOWN) produces at least one negative evidence object via the keyword `permitting`.
32. `temporary outage in a major AWS region` (DOWN) produces at least one negative evidence object via the multi-word keyword `outage in`.
33. `regular security patch for iOS devices` (HOLD) remains a single neutral evidence object — V3 short keywords must not flip it.
34. `in line with plan` (HOLD) remains a single neutral evidence object — V3 keyword `receives` must not flip it.

---

## Out of Scope (Version 3)

Version 3 explicitly does **not** introduce:

- LLM-based extraction, FinBERT, transformer-based sentiment, or any external NLP model.
- Named entity recognition, dependency parsing, or part-of-speech tagging.
- Multi-sentence rationale generation or natural-language explanation.
- Final forecast prediction, price prediction, or movement direction (owned by the Forecast Model).
- Temporal filtering or temporal validity checks (owned by the Temporal Retriever).
- Trading advice, buy/sell recommendations, or any portfolio action.
- Learned scoring, calibrated confidence, or per-keyword weights beyond the binary `support_score`.
- Whole-word boundary enforcement, lemmatization, or stemming.
- Per-keyword domain adaptation or ticker-specific dictionaries.
- **Negation handling** (e.g. "did not raise guidance") — out of scope for V3; the V3 keyword `receives` deliberately does NOT match the HOLD sentence "in line with plan" because that is a substring of a longer word in a different sense; whole-word boundaries are still out of scope.
- **Sentiment polarity inversion** for `not + positive` or `fails to + positive` — out of scope for V3; the V1, V2, and V3 dictionary is a fixed polarity mapping only.

The V1 and V2 keyword sets are retained verbatim — V3 is a strict superset. The V1 and V2 acceptance criteria, test scenarios, edge cases, and primary-evidence rule remain normative.