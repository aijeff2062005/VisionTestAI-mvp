"""Regression tests for acuity result mapping in both hospital backends."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Callable

import pytest


HOSPITAL_ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATIONS = (
    HOSPITAL_ROOT / "hospital_api" / "main.py",
    HOSPITAL_ROOT / "smart-hospital" / "smart_hospital" / "api" / "vision.py",
)


def _load_acuity_score(path: Path) -> Callable[[dict[str, Any]], str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_acuity_score"
    )
    namespace: dict[str, Any] = {"Any": Any}
    module = ast.Module(body=[function], type_ignores=[])
    exec(compile(module, str(path), "exec"), namespace)
    return namespace["_acuity_score"]


@pytest.mark.parametrize("implementation", IMPLEMENTATIONS, ids=("lean-api", "frappe"))
@pytest.mark.parametrize(
    ("eye", "expected"),
    (
        ({"vn_over_10": "7/10", "row_passed": True}, "7/10"),
        ({"vn_over_10": "7/10", "row_passed": False}, "<7/10"),
        ({"vn_over_10": "2/10", "row_passed": False}, "<2/10"),
        ({"vn_over_10": "1/10", "row_passed": False}, "<1/10"),
        ({"vn_over_10": "<7/10", "row_passed": False}, "<7/10"),
        ({"row_passed": False}, ""),
    ),
)
def test_acuity_score_uses_the_tested_level(
    implementation: Path,
    eye: dict[str, Any],
    expected: str,
) -> None:
    assert _load_acuity_score(implementation)(eye) == expected
