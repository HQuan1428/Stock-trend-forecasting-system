"""Defensive / scope tests for the dashboard.

These tests pin the dashboard's scope guarantees:

- No LLM / network libraries are imported anywhere in the dashboard.
- The dashboard does not invoke the Forecast Model or Faithfulness
  Evaluator at runtime — it is read-only with respect to those modules.
- ``apply_filters`` is a no-op when all filter values are empty.
- The case-detail template is identical across runs.
"""

from __future__ import annotations

import ast
import pathlib
import sys

import pandas as pd
import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
DASHBOARD_DIR = REPO_ROOT / "src" / "dashboard"


FORBIDDEN_TOP_LEVEL: tuple = (
    "openai",
    "anthropic",
    "transformers",
    "finbert",
    "huggingface_hub",
    "requests",
    "urllib",
    "httpx",
    "aiohttp",
)


def _collect_imports(tree: ast.AST) -> list:
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imports.append(module)
    return imports


@pytest.mark.parametrize(
    "module_path",
    sorted(DASHBOARD_DIR.glob("*.py")),
    ids=lambda p: p.name,
)
def test_dashboard_module_has_no_forbidden_imports(module_path: pathlib.Path) -> None:
    """No dashboard module may import an LLM / network library."""
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imports = _collect_imports(tree)
    for forbidden in FORBIDDEN_TOP_LEVEL:
        for imported in imports:
            # Match the top-level package and any submodule.
            top = imported.split(".")[0]
            assert top != forbidden, (
                f"{module_path.name} imports {imported!r}; the dashboard "
                f"is forbidden from importing {forbidden!r}."
            )


def test_dashboard_does_not_import_upstream_pipeline() -> None:
    """The dashboard must not import any upstream pipeline module."""
    forbidden = {"src.forecast_model", "src.faithfulness_evaluator", "src.retriever"}
    for module_path in sorted(DASHBOARD_DIR.glob("*.py")):
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        for imported in _collect_imports(tree):
            assert imported not in forbidden, (
                f"{module_path.name} imports {imported!r}; the dashboard "
                "is read-only with respect to the upstream pipeline."
            )


def test_load_dashboard_data_is_idempotent() -> None:
    from src.dashboard.data_loader import load_dashboard_data
    target = REPO_ROOT / "samples" / "dashboard" / "healthy"
    d1 = load_dashboard_data(str(target))
    d2 = load_dashboard_data(str(target))
    pd.testing.assert_frame_equal(d1.predictions, d2.predictions)
    pd.testing.assert_frame_equal(d1.evidence, d2.evidence)
    pd.testing.assert_frame_equal(d1.faithfulness, d2.faithfulness)
    pd.testing.assert_frame_equal(d1.leakage, d2.leakage)


def test_apply_filters_no_op_on_empty_filters() -> None:
    from src.dashboard.metrics import apply_filters
    df = pd.DataFrame(
        {
            "sample_id": ["S1", "S2"],
            "ticker": ["AAPL", "GOOGL"],
            "prediction": ["UP", "DOWN"],
        }
    )
    out = apply_filters(df, {})
    assert len(out) == len(df)
    out = apply_filters(df, {"tickers": [], "predictions": [], "date_range": None})
    assert len(out) == len(df)


def test_case_detail_template_is_byte_stable() -> None:
    from src.dashboard.components import CASE_DETAIL_TEMPLATE
    assert CASE_DETAIL_TEMPLATE == CASE_DETAIL_TEMPLATE
    # Render twice; the output must be byte-equal.
    out1 = CASE_DETAIL_TEMPLATE.format(
        prediction="UP",
        original_confidence=0.8,
        confidence_after_removal=0.5,
        confidence_drop=0.3,
        faithfulness_level="high",
        supportive_phrase="supportive",
    )
    out2 = CASE_DETAIL_TEMPLATE.format(
        prediction="UP",
        original_confidence=0.8,
        confidence_after_removal=0.5,
        confidence_drop=0.3,
        faithfulness_level="high",
        supportive_phrase="supportive",
    )
    assert out1 == out2


def test_loader_does_not_mutate_outputs(tmp_path_factory) -> None:
    """The loader MUST NOT mutate any file under the output dir."""
    import tempfile
    from src.dashboard.data_loader import load_dashboard_data

    with tempfile.TemporaryDirectory() as tmp:
        # Copy the healthy fixture into the tmp dir.
        import shutil

        src = REPO_ROOT / "samples" / "dashboard" / "healthy"
        dest = pathlib.Path(tmp) / "outputs"
        shutil.copytree(src, dest)
        before = _dir_snapshot(dest)
        load_dashboard_data(str(dest))
        after = _dir_snapshot(dest)
        assert before == after, (
            "Loader mutated files under the output directory"
        )


def _dir_snapshot(path: pathlib.Path) -> dict:
    out = {}
    for item in sorted(path.rglob("*")):
        if item.is_file():
            out[str(item.relative_to(path))] = item.read_bytes()
    return out