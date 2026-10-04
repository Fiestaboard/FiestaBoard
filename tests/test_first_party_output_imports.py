"""The first-party output packages depend on FiestaBoard only through the author API.

Vestaboard and FiestaPanel live in their own repositories (plan D9) and
reach core through the output seed; this checks the copies core actually
loads (the seed's, or a dev override's). Code there may import the standard library, third-party
libraries, its own modules (relative imports), and FiestaBoard only as
``src.plugins`` — the output-plugin author API, versioned with
``output_api``. Never ``src.board_client``-style internals: a package that
reaches past the API cannot be released on its own, and a core refactor
would break it silently (D10: "no ``src.board_client`` import from any
plugin").

The packages' own tests may additionally import their own package by the
name core gives it (``plugins.<id>``) and use the conformance suite and the
manifest loader — what a plugin repository's CI runs against core. Each
repository is checked on its own (its directory is the scan's root).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.outputs.first_party import FIRST_PARTY_OUTPUTS, first_party_source

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


#: Never package code: git's data, and the ignored test scaffold a checkout
#: may hold (``run_tests.sh``).
_SKIPPED_DIRS = frozenset({".git", ".test-scaffold", "__pycache__"})


def violations(package: Path, plugin_id: str) -> list[str]:
    """Every import in *package* (one output's repository) that breaks the rule."""
    found: list[str] = []
    own = f"plugins.{plugin_id}"
    for path in sorted(package.rglob("*.py")):
        rel = path.relative_to(package)
        if _SKIPPED_DIRS & set(rel.parts):
            continue
        allowed = ALLOWED_FOR_TESTS if "tests" in rel.parts else ALLOWED_FOR_CODE
        depth = len(rel.parts)  # how far up a relative import may reach and stay inside the package
        for lineno, module, level in _imports(path):
            if level:
                if level > depth:
                    found.append(f"{rel}:{lineno} a relative import that leaves the package")
                continue
            top = module.split(".")[0]
            if "tests" in rel.parts and (module == own or module.startswith(f"{own}.")):
                continue
            if top in {"src", "plugins", "first_party_outputs", "tests"} and module not in allowed:
                found.append(f"{rel}:{lineno} imports {module}")
    return found


@pytest.mark.parametrize("output_id", FIRST_PARTY_OUTPUTS)
def test_the_package_imports_only_the_author_api(output_id):
    package = first_party_source(output_id).path
    assert (package / "manifest.json").is_file()
    found = violations(package, output_id)
    assert found == [], f"{output_id} reaches past src.plugins:\n  " + "\n  ".join(found)


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
    planted = tmp_path / "output.py"
    planted.write_text(source)
    found = violations(tmp_path, "acme")
    assert len(found) == 1 and expected in found[0]


def test_a_relative_import_inside_the_package_is_allowed(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "output.py").write_text("from .transport import send\n")
    (tmp_path / "tests" / "test_it.py").write_text("from .conftest import CLOUD\nfrom ..output import Acme\n")
    assert violations(tmp_path, "acme") == []


def test_tests_may_use_the_conformance_suite(tmp_path):
    planted = tmp_path / "tests" / "test_it.py"
    planted.parent.mkdir(parents=True)
    planted.write_text(
        "from src.outputs.conformance import OutputConformanceSuite\nfrom src.plugins.manifest import load_manifest\n"
        "from plugins.acme import Acme\n"
    )
    assert violations(tmp_path, "acme") == []


def test_package_code_may_not_import_itself_by_name(tmp_path):
    (tmp_path / "output.py").write_text("from plugins.acme.transport import send\n")
    assert len(violations(tmp_path, "acme")) == 1


def test_tests_may_not_import_another_package(tmp_path):
    planted = tmp_path / "tests" / "test_it.py"
    planted.parent.mkdir(parents=True)
    planted.write_text("from plugins.vestaboard import VestaboardOutput\n")
    assert len(violations(tmp_path, "acme")) == 1


def test_the_test_scaffold_and_git_data_are_not_scanned(tmp_path):
    for skipped in (".test-scaffold/plugins/acme", ".git/hooks"):
        (tmp_path / skipped).mkdir(parents=True)
        (tmp_path / skipped / "x.py").write_text("from src.board_client import BoardClient\n")
    assert violations(tmp_path, "acme") == []
