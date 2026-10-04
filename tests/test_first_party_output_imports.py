"""The first-party output packages depend on FiestaBoard only through the author API.

``first_party_outputs/<id>/`` is laid out as each output's own repository
will be (plan D9). Code there may import the standard library, third-party
libraries, its own modules (relative imports), and FiestaBoard only as
``src.plugins`` — the output-plugin author API, versioned with
``output_api``. Never ``src.board_client``-style internals: a package that
reaches past the API cannot be released on its own, and a core refactor
would break it silently (D10: "no ``src.board_client`` import from any
plugin").

The packages' own tests may additionally import their own package by name
and use the conformance suite and the manifest loader — what a plugin
repository's CI runs against core.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PACKAGES = REPO / "first_party_outputs"

#: What package code may import from FiestaBoard.
ALLOWED_FOR_CODE = frozenset({"src.plugins"})
#: What package tests may import from FiestaBoard besides the author API.
ALLOWED_FOR_TESTS = ALLOWED_FOR_CODE | {"src.plugins.manifest", "src.outputs.conformance"}


def _imports(path: Path) -> list[tuple[int, str, int]]:
    """``(line, module, level)`` for every import in *path*."""
    found: list[tuple[int, str, int]] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name, 0) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append((node.lineno, node.module or "", node.level))
    return found


def violations(root: Path) -> list[str]:
    """Every import under *root* (a directory of packages) that breaks the rule."""
    found: list[str] = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root)
        allowed = ALLOWED_FOR_TESTS if "tests" in rel.parts else ALLOWED_FOR_CODE
        depth = len(rel.parts) - 1  # how far up a relative import may reach and stay inside the package
        for lineno, module, level in _imports(path):
            if level:
                if level > depth:
                    found.append(f"{rel}:{lineno} a relative import that leaves the package")
                continue
            top = module.split(".")[0]
            own = f"first_party_outputs.{rel.parts[0]}"
            if "tests" in rel.parts and (module == own or module.startswith(f"{own}.")):
                continue
            if top in {"src", "plugins", "first_party_outputs", "tests"} and module not in allowed:
                found.append(f"{rel}:{lineno} imports {module}")
    return found


def test_there_are_packages_to_check():
    packages = sorted(p.name for p in PACKAGES.iterdir() if (p / "manifest.json").is_file())
    assert packages == ["fiestapanel", "vestaboard"]


def test_the_packages_import_only_the_author_api():
    found = violations(PACKAGES)
    assert found == [], "first-party output packages reach past src.plugins:\n  " + "\n  ".join(found)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("from src.board_client import BoardClient\n", "imports src.board_client"),
        ("import src.outputs.floor\n", "imports src.outputs.floor"),
        ("from src.plugins.manifest import load_manifest\n", "imports src.plugins.manifest"),
        ("from plugins.weather import WeatherPlugin\n", "imports plugins.weather"),
        ("from ... import something\n", "leaves the package"),
    ],
)
def test_the_scan_sees_a_planted_violation(tmp_path, source, expected):
    planted = tmp_path / "acme" / "output.py"
    planted.parent.mkdir()
    planted.write_text(source)
    found = violations(tmp_path)
    assert len(found) == 1 and expected in found[0]


def test_tests_may_use_the_conformance_suite(tmp_path):
    planted = tmp_path / "acme" / "tests" / "test_it.py"
    planted.parent.mkdir(parents=True)
    planted.write_text(
        "from src.outputs.conformance import OutputConformanceSuite\nfrom src.plugins.manifest import load_manifest\n"
        "from first_party_outputs.acme import Acme\n"
    )
    assert violations(tmp_path) == []


def test_tests_may_not_import_another_package(tmp_path):
    planted = tmp_path / "acme" / "tests" / "test_it.py"
    planted.parent.mkdir(parents=True)
    planted.write_text("from first_party_outputs.vestaboard import VestaboardOutput\n")
    assert len(violations(tmp_path)) == 1
