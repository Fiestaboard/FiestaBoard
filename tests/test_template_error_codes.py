"""Every ``TemplateError`` names a code the validate response can carry.

``TemplateValidationError.code`` is a ``Literal``: an error built without a
code, or with one outside it, would turn ``POST /templates/validate`` into a
500 instead of a verdict. So ``code`` has no default, and every place in
``src/`` that builds a ``TemplateError`` passes one of the published codes.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import get_args

import pytest

from src.templates.engine import TemplateError
from src.templates.models import TemplateValidationError

SRC = Path(__file__).resolve().parent.parent / "src"
CODES = set(get_args(TemplateValidationError.model_fields["code"].annotation))


def _template_error_calls() -> list[tuple[str, ast.Call]]:
    calls = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text("utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
                if name == "TemplateError":
                    calls.append((f"{path.relative_to(SRC.parent)}:{node.lineno}", node))
    return calls


def test_a_template_error_cannot_be_built_without_a_code():
    with pytest.raises(TypeError):
        TemplateError(line=1, column=0, message="Mismatched variable braces {{}}")  # type: ignore[call-arg]


def test_every_site_that_builds_a_template_error_passes_a_published_code():
    calls = _template_error_calls()
    assert len(calls) >= 6, "the six validate checks build TemplateErrors"
    for where, call in calls:
        code = next((kw.value for kw in call.keywords if kw.arg == "code"), None)
        assert isinstance(code, ast.Constant), f"{where}: TemplateError without a literal code="
        assert code.value in CODES, f"{where}: code {code.value!r} is not one of {sorted(CODES)}"
