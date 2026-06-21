# Repository Guidelines

## 1. Project Overview

This repository implements a learning prototype for **Faithful Evidence-Centric Financial News Forecasting**.

The project predicts stock movement from financial news and checks whether the cited evidence is actually relevant to the prediction. The focus is not only prediction accuracy, but also evidence faithfulness, temporal correctness, and explainability.

This is an academic prototype. It must not be presented as a real trading system or investment recommendation tool.

## 2. Baseline Scope

Build the baseline first before adding advanced features.

The baseline includes:

* Small or simulated financial news dataset
* Temporal filtering to prevent future-news leakage
* Simple evidence extraction
* Basic `UP`, `DOWN`, `HOLD` forecasting
* Faithfulness evaluation
* Streamlit dashboard
* pytest tests
* OpenSpec documentation
* CSV outputs for experiment results

Keep the first version simple, deterministic, and demo-ready. Advanced ML/NLP models should only be considered after the baseline works end-to-end.

## 3. Repository Structure

Use this target structure:

```text
.
├── AGENTS.md
├── README.md
├── requirements.txt
├── data/
├── src/
│   ├── __init__.py
│   ├── retriever.py
│   ├── evidence_extractor.py
│   ├── forecast_model.py
│   ├── faithfulness_metrics.py
│   ├── pipeline.py
│   └── dashboard.py
├── tests/
├── outputs/
└── openspec/
    └── changes/
        └── faithful-evidence-forecasting/
            ├── proposal.md
            ├── design.md
            ├── tasks.md
            └── specs/
                └── forecasting/
                    └── spec.md
```

Do not move files into a different architecture unless there is a clear project-level reason.

## 4. Tech Stack and Commands

Use Python as the main language.

Default stack:

* pandas
* numpy
* scikit-learn
* Streamlit
* Plotly
* pytest

Use matplotlib only when a static figure is explicitly needed.

Commands:

```bash
pip install -r requirements.txt
python -m src.pipeline
streamlit run src/dashboard.py
pytest tests/
```

## 5. Development Conventions

Use `snake_case` for Python files, functions, variables, and data columns.

Prefer readable pandas-based code over clever abstractions. Keep modules small and focused. Add comments only where the business logic may be misunderstood, especially around temporal filtering and evidence evaluation.

Commit message examples:

```text
feat: add temporal retriever
feat: add baseline forecast model
test: add leakage regression test
docs: add OpenSpec proposal
fix: correct pipeline output path
```

PRs should mention what changed, how to run it, test results, and known limitations.

## 6. OpenSpec Workflow

Before implementing a feature, read the relevant OpenSpec files.

Use OpenSpec as the source of truth for:

* Data schemas
* Output contracts
* Faithfulness metrics
* Acceptance criteria
* Dashboard requirements
* Testing requirements
* Implementation task checklist

If implementation and OpenSpec disagree, update the OpenSpec or ask for clarification before continuing.

## 7. Boundaries

Always preserve temporal validity: future news must not be used for prediction.

Ask first before adding real financial data, advanced ML models, external APIs, crawlers, databases, authentication, or major architectural changes.

Never add secrets, API keys, credentials, buy/sell recommendations, or claims that the system is reliable for real investment decisions.

Do not over-engineer the baseline. The priority is a working, explainable, testable prototype.
