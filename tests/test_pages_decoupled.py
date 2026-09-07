"""The pages router must not depend on ``src.api_server`` (Phase 2 §2.3).

The #1756 extraction moved the sixteen pages/staff-picks handlers out of the
10k-line ``src/api_server.py`` but left **thirteen** call-time
``from src.api_server import ...`` statements behind — the second-heaviest of
any router — purely so the suite's ``patch("src.api_server.<name>")`` targets
kept resolving. That is not an extraction: importing the router was clean, but
*serving a request* pulled the whole module — its route table, its background
tasks, its MCP mount — back in, and the 2026-09 audit counted those seams going
up 4.2x across Phase 1.

This test pins the fix the honest way. In a fresh interpreter it imports the
router, drives **all fourteen** handlers end to end against patched canonical
seams (``src.pages.routes.<name>``), asserts the stubs really were driven — so
a handler that silently no-op'd could not pass — and then asserts
``src.api_server`` never entered ``sys.modules``.

Importing the module alone would be a much weaker claim: the seams were call
time, so a module-level import check passes with every one of them still in
place.

Where the collaborators went, for the reader chasing a patch target:

===========================================  ==================================
Was                                          Now
===========================================  ==================================
``api_server.get_page_service``              ``src.pages.service``
``api_server.get_settings_service``          ``src.settings.service``
``api_server.get_collection_service``        ``src.collections.service``
``api_server.get_schedule_service``          ``src.schedules.service``
``api_server.is_collection_id``              ``src.collections.models``
``api_server.resolve_dimensions``            ``src.devices``
``api_server.text_to_board_array``           ``src.text_to_board``
``api_server.get_service``                   ``src.display_runtime`` (new)
``api_server._require_board``                ``src.board_guards`` (new)
``api_server._board_dims``                   ``src.board_guards``
``api_server._board_is_paused``              ``src.board_guards``
``api_server._silence_active``               ``src.board_guards``
``api_server._reject_plugin_...beta_off``    ``src.pages.routes`` (sole caller)
===========================================  ==================================
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

import src.pages.routes as routes
from src.pages.models import (
    Page,
    PageCacheClearRequest,
    PageCreate,
    PageImportRequest,
    PagePreviewBatchRequest,
    PageSendRequest,
    PageUpdate,
)
from src.pages.share import encode_page

assert "src.api_server" not in sys.modules, "importing the pages router must not import api_server"


def call(coro):
    return asyncio.run(coro)


sample = Page(
    id="page:abc",
    name="Decoupled",
    type="template",
    device_type="flagship",
    template=["DECOUPLED", "", "", "", "", ""],
)
share_string = encode_page(sample)

rendered = MagicMock(available=True, formatted="DECOUPLED\n", display_type="page:template", raw={}, error=None)

delete_result = MagicMock(
    deleted=True,
    default_page_created=False,
    new_page_id=None,
    active_page_updated=False,
    new_active_page_id=None,
)

page_service = MagicMock()
page_service.list_pages.return_value = [sample]
page_service.get_page.return_value = sample
page_service.create_page.return_value = sample
page_service.update_page.return_value = sample
page_service.delete_page.return_value = delete_result
page_service.preview_page.return_value = rendered
page_service.preview_pages_batch.return_value = {"page:abc": rendered}
page_service.get_cache_stats.return_value = {"cache_size": 1, "cached_pages": ["page:abc"], "ttl_seconds": 30}

settings_service = MagicMock()
settings_service.is_schedule_enabled.return_value = False
settings_service.get_active_page_id.return_value = "page:abc"
settings_service.should_send_to_board.return_value = False
settings_service.get_primary_board_id.return_value = "board-1"
settings_service.get_output_settings.return_value = MagicMock(target="ui")
settings_service.get_transition_settings.return_value = MagicMock(strategy=None, step_interval_ms=None, step_size=None)
settings_service.get_beta_settings.return_value = MagicMock(transition_plugins_enabled=True)

collection_service = MagicMock()
collection_service.resolve_page_id.return_value = "page:abc"

schedule_service = MagicMock()
schedule_service.get_active_page_id.return_value = "page:abc"

board_client = MagicMock()
board_client.render.return_value = (True, True)
display_service = MagicMock()
display_service.vb_client = board_client
display_service.get_board_client.return_value = board_client

BOARD = {"id": "board-1", "name": "Kitchen", "device_type": "flagship"}

with (
    patch("src.pages.routes.get_page_service", return_value=page_service),
    patch("src.pages.routes.get_settings_service", return_value=settings_service),
    patch("src.pages.routes.get_collection_service", return_value=collection_service),
    patch("src.pages.routes.get_schedule_service", return_value=schedule_service),
    patch("src.pages.routes.get_service", return_value=display_service),
    patch("src.pages.routes._require_board", return_value=BOARD) as require_board,
    patch("src.pages.routes._silence_active", return_value=False) as silence_active,
    patch("src.pages.routes._board_is_paused", return_value=False) as board_is_paused,
):
    # 1. GET /pages
    listed = call(routes.list_pages())
    assert listed.total == 1, listed
    assert listed.pages[0].name == "Decoupled", listed

    # 2. GET /pages/current-display
    current = call(routes.get_current_display())
    assert current.page_id == "page:abc", current
    assert current.template == sample.template, current

    # 3. POST /pages
    created = call(routes.create_page(PageCreate(name="Decoupled", type="template", template=["DECOUPLED"])))
    assert created.id == "page:abc", created

    # 4. GET /pages/{page_id}
    fetched = call(routes.get_page("page:abc"))
    assert fetched.id == "page:abc", fetched

    # 5. PUT /pages/{page_id}
    updated = call(routes.update_page("page:abc", PageUpdate(name="Renamed")))
    assert updated.page.id == "page:abc", updated
    assert updated.incompatible_references == [], updated

    # 6. DELETE /pages/{page_id}
    deleted = call(routes.delete_page("page:abc"))
    assert deleted.id == "page:abc", deleted

    # 7. GET /pages/{page_id}/share
    shared = call(routes.get_page_share_string("page:abc"))
    assert shared.share_string == share_string, shared

    # 8. POST /pages/import/preview
    previewed = call(routes.preview_page_import(PageImportRequest(share_string=share_string)))
    assert previewed["name"] == "Decoupled", previewed

    # 9. POST /pages/import
    imported = call(routes.import_page(PageImportRequest(share_string=share_string)))
    assert imported.id == "page:abc", imported

    # The two staff-picks handlers moved to src/staff_picks/routes.py in
    # Phase 2 slice 8; tests/test_small_domains_decoupled.py drives them there.

    # 10. POST /pages/{page_id}/preview
    preview = call(routes.preview_page("page:abc", force_refresh=True))
    assert preview.lines == ["DECOUPLED", ""], preview

    # 11. POST /pages/preview/batch
    batch = call(routes.preview_pages_batch(PagePreviewBatchRequest(page_ids=["page:abc"])))
    assert batch.total == 1 and batch.successful == 1, batch

    # 12. GET /pages/cache/stats
    stats = call(routes.get_page_cache_stats())
    assert stats.cached_pages == ["page:abc"], stats

    # 13. POST /pages/cache/clear
    cleared = call(routes.clear_page_cache(PageCacheClearRequest(page_id="page:abc")))
    assert cleared.page_id == "page:abc", cleared

    # 14. POST /pages/{page_id}/send — the deepest handler: board lookup, the
    # silence and pause guards, dimension resolution and the board render.
    sent = call(routes.send_page("page:abc", payload=PageSendRequest(target="board", board_id="board-1")))
    assert sent.sent_to_board is True, sent
    assert sent.board_id == "board-1", sent

# Not vacuous: every handler really drove its collaborator. A handler that
# silently returned a canned value would fail here even though its assertion
# above passed.
page_service.list_pages.assert_called_once()
page_service.create_page.assert_called()
page_service.update_page.assert_called_once()
page_service.delete_page.assert_called_once_with("page:abc")
page_service.preview_page.assert_called()
page_service.preview_pages_batch.assert_called_once()
page_service.get_cache_stats.assert_called_once()
page_service.invalidate_preview_cache.assert_called_once_with("page:abc")
settings_service.get_active_page_id.assert_called()
settings_service.get_transition_settings.assert_called_once()
schedule_service.get_active_page_id.assert_not_called()  # schedule mode is off
require_board.assert_called_once_with("board-1")
silence_active.assert_called_once_with("board-1")
board_is_paused.assert_called_once_with("board-1")
board_client.render.assert_called_once()

assert "src.api_server" not in sys.modules, (
    "a pages handler imported src.api_server — the call-time seam regrew"
)
print("DECOUPLED")
"""


def test_pages_router_serves_every_route_without_importing_api_server():
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


def test_pages_router_source_declares_no_api_server_import():
    """A static backstop over every branch, not just the exercised ones.

    The subprocess test above can only catch a seam on a code path it drives.
    This walks the module's AST, so an ``import api_server`` hidden inside a
    rarely-taken ``except`` branch fails the build too.
    """
    import ast

    tree = ast.parse((REPO_ROOT / "src" / "pages" / "routes.py").read_text())
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            offenders += [a.name for a in node.names if "api_server" in a.name]
        elif isinstance(node, ast.ImportFrom) and "api_server" in (node.module or ""):
            offenders.append(node.module)

    assert offenders == [], f"src/pages/routes.py imports api_server: {offenders}"
