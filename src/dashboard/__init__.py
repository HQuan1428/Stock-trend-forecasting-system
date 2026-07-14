"""Read-only Streamlit dashboard over the final stage envelope.

Consumes ``outputs/08_market.json`` produced by the stage chain. Never
writes to ``outputs/``, never invokes a stage, never re-runs the model.
"""
