"""The collections router must not depend on ``src.api_server`` (Phase 2 §2.3).

The #1756 extraction moved the five collection handlers out of the 10k-line
``src/api_server.py`` but left six call-time ``from src.api_server import ...``
statements behind, purely so the suite's ``patch("src.api_server.<name>")``
targets kept resolving. That is not an extraction: importing the router was
clean, but *serving a request* pulled the whole module — its route table, its
background tasks, its MCP mount — back in, and the 2026-09 audit counted those
seams going up 4.2x across Phase 1.

This test pins the fix the honest way. In a fresh interpreter it imports the
router, drives all five handlers end to end against patched canonical seams
(``src.collections.routes.<name>``), asserts the stubs really were driven — so
a handler that silently no-op'd could not pass — and then asserts
``src.api_server`` never entered ``sys.modules``.

Importing the module alone would be a much weaker claim: the seams were call
time, so a module-level import check passes even with every one of them still
in place.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

SCRIPT = r"""
import asyncio
import sys
from unittest.mock import MagicMock, patch

import src.collections.routes as routes
from src.collections.models import Collection, CollectionCreate, CollectionUpdate

assert "src.api_server" not in sys.modules, "importing the collections router must not import api_server"


def call(coro):
    return asyncio.run(coro)


sample = Collection(id="collection:abc", name="Decoupled", page_ids=["p1"])

collection_service = MagicMock()
collection_service.list_collections.return_value = [sample]
collection_service.get_collection.return_value = sample
collection_service.create_collection.return_value = sample
collection_service.update_collection.return_value = sample
collection_service.delete_collection.return_value = True

page_service = MagicMock()
page_service.get_page.return_value = object()

with (
    patch("src.collections.routes.get_collection_service", return_value=collection_service),
    patch("src.collections.routes.get_page_service", return_value=page_service),
):
    listed = call(routes.list_collections())
    assert listed.total == 1, listed
    assert listed.collections[0].name == "Decoupled"

    created = call(routes.create_collection(CollectionCreate(name="Decoupled", page_ids=["p1"])))
    assert created.id == "collection:abc", created

    fetched = call(routes.get_collection("collection:abc"))
    assert fetched.id == "collection:abc", fetched

    updated = call(routes.update_collection("collection:abc", CollectionUpdate(name="Renamed")))
    assert updated.id == "collection:abc", updated

    deleted = call(routes.delete_collection("collection:abc"))
    assert deleted.id == "collection:abc", deleted

# Not vacuous: the handlers really drove the service, and really validated the
# page ids through the page service.
collection_service.list_collections.assert_called_once()
collection_service.create_collection.assert_called_once()
collection_service.get_collection.assert_called_once_with("collection:abc")
collection_service.update_collection.assert_called_once()
collection_service.delete_collection.assert_called_once_with("collection:abc")
page_service.get_page.assert_called_with("p1")

assert "src.api_server" not in sys.modules, (
    "a collections handler imported src.api_server — the call-time seam regrew"
)
print("DECOUPLED")
"""


def test_collections_router_serves_every_route_without_importing_api_server():
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "DECOUPLED" in result.stdout


def test_collections_router_source_declares_no_api_server_import():
    """A static backstop over every branch, not just the exercised ones.

    The subprocess test above can only catch a seam on a code path it drives.
    This walks the module's AST, so an ``import api_server`` hidden inside a
    rarely-taken ``except`` branch fails the build too.
    """
    import ast

    tree = ast.parse((REPO_ROOT / "src" / "collections" / "routes.py").read_text())
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            offenders += [a.name for a in node.names if "api_server" in a.name]
        elif isinstance(node, ast.ImportFrom) and "api_server" in (node.module or ""):
            offenders.append(node.module)

    assert offenders == [], f"src/collections/routes.py imports api_server: {offenders}"
