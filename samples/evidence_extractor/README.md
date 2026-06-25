# Evidence Extractor — Sample Inputs and Expected Outputs

These JSON files document the five documented examples from the OpenSpec spec.
Each pair is `NN_*_input.json` (the news item fed to `extract_evidence`) and
`NN_*_expected.json` (the deterministic result the extractor MUST return).

The samples double as **golden fixtures**: a small script can load every
`NN_*_input.json`, run `extract_evidence`, and assert byte-equality with
`NN_*_expected.json` (after `json.dumps` normalization).

| # | File pair                          | Scenario                |
|---|------------------------------------|-------------------------|
| 1 | `01_positive_only_*.json`          | Two positive keywords   |
| 2 | `02_negative_only_*.json`          | Negative keyword (token-level match: "weak iPhone sales") |
| 3 | `03_neutral_*.json`                | No keyword → neutral fallback |
| 4 | `04_mixed_*.json`                  | Positive + negative, primary evidence = negative |
| 5 | `05_case_insensitive_*.json`       | All-uppercase input     |
