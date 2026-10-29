"""``geometry_of`` refuses flexible pages, and every geometry call site is classified.

A flexible page has no grid. Reaching ``geometry_of`` would silently treat it as
a 6x22 flagship page (the missing ``device_type`` default), so the guard raises
instead. The ratchet below pins every call of a geometry helper in ``src/`` to
an entry in ``geometry_call_sites.json`` saying whether it receives a board, a
page or a bare geometry tuple. A page-receiving site must name the test that
covers its flexible routing.
"""

import ast
import json
from pathlib import Path

import pytest

from src.devices import (
    FlexiblePageGeometryError,
    dimensions_of,
    geometry_of,
    is_flexible_page,
    page_size_key,
    page_size_label,
)
from src.pages.models import Page

REPO = Path(__file__).resolve().parents[2]
MANIFEST = Path(__file__).with_name("geometry_call_sites.json")
GEOMETRY_CALLEES = frozenset({"geometry_of", "size_key", "dimensions_of", "pages_compatible_with_board"})
KINDS = frozenset({"board", "page", "tuple"})

FLEX = {
    "name": "Morning",
    "type": "flexible",
    "blocks": [{"id": "b1", "kind": "text", "text": "HI"}],
}


def _callee_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


class _CallSiteScanner(ast.NodeVisitor):
    def __init__(self, relpath: str) -> None:
        self.relpath = relpath
        self.enclosing: list[str] = []
        self.sites: set[str] = set()

    def _visit_def(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.enclosing.append(node.name)
        self.generic_visit(node)
        self.enclosing.pop()

    visit_FunctionDef = _visit_def
    visit_AsyncFunctionDef = _visit_def

    def visit_Call(self, node: ast.Call) -> None:
        callee = _callee_name(node.func)
        if callee in GEOMETRY_CALLEES:
            where = self.enclosing[-1] if self.enclosing else "<module>"
            self.sites.add(f"{self.relpath}::{where}::{callee}")
        self.generic_visit(node)


def scan_call_sites(root: Path) -> set[str]:
    """Every geometry helper call under *root*, keyed ``relpath::enclosing_def::callee``.

    Keyed on names, not line numbers, so unrelated edits do not churn the manifest.
    """
    base = root.resolve()
    found: set[str] = set()
    for path in sorted(base.rglob("*.py")):
        relpath = path.relative_to(REPO).as_posix()
        scanner = _CallSiteScanner(relpath)
        scanner.visit(ast.parse(path.read_text(encoding="utf-8"), filename=relpath))
        found |= scanner.sites
    return found


def test_exists(node_id: str) -> bool:
    """Whether ``tests/...py::test_name`` names a test function defined in that file."""
    relpath, _, name = node_id.partition("::")
    path = REPO / relpath
    if not name or not path.is_file():
        return False
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name for n in ast.walk(tree))


test_exists.__test__ = False  # a helper, not a pytest test


def _manifest() -> dict[str, dict]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_geometry_of_raises_for_flexible_page():
    with pytest.raises(FlexiblePageGeometryError):
        geometry_of(Page.model_validate(FLEX))


def test_geometry_of_raises_for_flexible_page_dict():
    with pytest.raises(FlexiblePageGeometryError):
        geometry_of({"type": "flexible", "name": "x"})


def test_flexible_geometry_error_escapes_value_error_handlers():
    assert not issubclass(FlexiblePageGeometryError, ValueError)


def test_dimensions_of_raises_too():
    with pytest.raises(FlexiblePageGeometryError):
        dimensions_of(Page.model_validate(FLEX))


def test_board_dicts_still_resolve():
    assert geometry_of({"device_type": "note"}).device_type == "note"


def test_grid_page_geometry_is_unchanged():
    assert geometry_of(Page(name="G", type="template", template=["X"])).device_type == "flagship"


def test_is_flexible_page():
    assert is_flexible_page(Page.model_validate(FLEX))
    assert is_flexible_page({"type": "flexible"})
    assert not is_flexible_page(Page(name="G", type="template", template=["X"]))
    assert not is_flexible_page({"device_type": "note"})


def test_size_helpers():
    assert page_size_key(Page.model_validate(FLEX)) is None
    assert page_size_label(Page.model_validate(FLEX)) == "flexible"
    assert page_size_key(Page(name="G", type="template", template=["X"])) == "flagship:6x22"


def test_size_label_of_grid_page_is_its_size_key():
    assert page_size_label(Page(name="G", type="template", template=["X"])) == "flagship:6x22"


def test_every_geometry_call_site_is_classified():
    found = scan_call_sites(REPO / "src")
    manifest = _manifest()
    assert found - manifest.keys() == set(), "classify the new call site in geometry_call_sites.json"
    assert manifest.keys() - found == set(), "remove stale entries"


def test_every_manifest_entry_has_a_known_kind():
    for site, entry in _manifest().items():
        assert entry["kind"] in KINDS, site


def test_every_page_routed_site_names_an_existing_test():
    for site, entry in _manifest().items():
        if entry["kind"] == "page":
            assert entry.get("test") and test_exists(entry["test"]), site


# --- direct grid-field reads on pages in the Fiestabot surfaces ------------------

#: The grid fields a flexible page still carries as flagship defaults on its model object.
GRID_FIELDS = frozenset({"device_type", "notes_wide", "notes_tall", "grid_rows", "grid_cols"})
#: Where Fiestabot answers about pages: MCP tools and the ops layer.
FIESTABOT_SOURCES = ("src/mcp_server.py", "src/ops")
#: ``relpath::enclosing_def::receiver.field`` reads known not to be of a page
#: (a board, a request, a geometry tuple). Every other read must go through
#: ``page_geometry_fields``.
GRID_FIELD_READ_ALLOWLIST: frozenset[str] = frozenset()


class _GridFieldReadScanner(ast.NodeVisitor):
    def __init__(self, relpath: str) -> None:
        self.relpath = relpath
        self.enclosing: list[str] = []
        self.reads: set[str] = set()

    def _visit_def(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.enclosing.append(node.name)
        self.generic_visit(node)
        self.enclosing.pop()

    visit_FunctionDef = _visit_def
    visit_AsyncFunctionDef = _visit_def

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in GRID_FIELDS and isinstance(node.ctx, ast.Load):
            where = self.enclosing[-1] if self.enclosing else "<module>"
            self.reads.add(f"{self.relpath}::{where}::{ast.unparse(node)}")
        self.generic_visit(node)


def scan_grid_field_reads(paths: list[Path], root: Path = REPO) -> set[str]:
    """Every ``<expr>.device_type``-style read in *paths*, keyed ``relpath::enclosing_def::expr``."""
    found: set[str] = set()
    for path in paths:
        relpath = path.resolve().relative_to(root.resolve()).as_posix()
        scanner = _GridFieldReadScanner(relpath)
        scanner.visit(ast.parse(path.read_text(encoding="utf-8"), filename=relpath))
        found |= scanner.reads
    return found


def _fiestabot_files() -> list[Path]:
    files: list[Path] = []
    for source in FIESTABOT_SOURCES:
        path = REPO / source
        files.extend(sorted(path.rglob("*.py")) if path.is_dir() else [path])
    return files


def test_scanner_flags_a_direct_device_type_read(tmp_path):
    source = tmp_path / "probe.py"
    source.write_text("def f(page):\n    page.name = page.device_type\n    return page.grid_rows\n", encoding="utf-8")
    assert scan_grid_field_reads([source], root=tmp_path) == {
        "probe.py::f::page.device_type",
        "probe.py::f::page.grid_rows",
    }


def test_fiestabot_never_reads_a_pages_grid_fields_directly():
    reads = scan_grid_field_reads(_fiestabot_files())
    assert reads - GRID_FIELD_READ_ALLOWLIST == set(), (
        "report a page's geometry with src.devices.page_geometry_fields (a flexible page answers"
        " its layout board's), or allowlist a read that is not of a page"
    )
    assert GRID_FIELD_READ_ALLOWLIST - reads == set(), "remove stale allowlist entries"
