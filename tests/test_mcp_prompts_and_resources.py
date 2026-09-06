"""Every MCP prompt and resource must actually execute.

The MCP surface is not 28 tools — it is 28 tools, 5 prompts and 6 resources.
The prompts *are* the skill definitions: they are what a client invokes when a
user picks "Set up FiestaBoard" from a menu, and their text is what steers the
model through a multi-tool task.

Before this file, no test executed a single one of them. ``prompts/list``
returning them is not evidence they work — a prompt whose body raises, or
which renders empty, or which instructs the model to call a tool that has
since been renamed, fails silently and shows up only as a user saying the
assistant got confused.

Same for resources. ``fiestaboard://page/{page_id}/preview.html`` is a URI
template that takes a real page id and renders HTML; nothing checked that it
does.

This runs the prompt and resource functions directly against real services on
``tmp_path``, in the spirit of ``tests/test_mcp_state_effects.py``: no mocks,
so a call into thin air raises rather than being conjured.

Coverage floors below fail if a prompt or resource is added without a case
here, so the surface cannot grow untested.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

pytest.importorskip("mcp", reason="mcp package not installed")

from src.collections.service import CollectionService
from src.collections.storage import CollectionStorage
from src.config_manager import ConfigManager
from src.mcp_server import _build_mcp_server
from src.pages.service import PageService
from src.pages.storage import PageStorage
from src.schedules.service import ScheduleService
from src.schedules.storage import ScheduleStorage

EXPECTED_PROMPTS = {
    "setup_fiestaboard",
    "create_display_page",
    "schedule_my_day",
    "build_a_collection",
    "troubleshoot_display",
}

EXPECTED_RESOURCES = {
    "fiestaboard://plugins",
    "fiestaboard://pages",
    "fiestaboard://variables",
    "fiestaboard://schedules",
    "fiestaboard://collections",
}

EXPECTED_RESOURCE_TEMPLATES = {"fiestaboard://page/{page_id}/preview.html"}

FLAGSHIP_TEMPLATE = ["HELLO", "", "", "", "", ""]


@pytest.fixture(scope="module")
def mcp():
    instance = _build_mcp_server()
    assert instance is not None, "mcp installed but _build_mcp_server() returned None"
    return instance


@pytest.fixture
def services(tmp_path, monkeypatch):
    """Real services on throwaway storage — mirrors test_mcp_state_effects."""
    pages = PageService(PageStorage(str(tmp_path / "pages.json")))
    schedules = ScheduleService(ScheduleStorage(str(tmp_path / "schedules.json")))
    collections = CollectionService(CollectionStorage(str(tmp_path / "collections.json")))

    # conftest's autouse ``_isolated_data_dir`` (#1762) dropped the singleton
    # already; constructing installs this one, and conftest drops it again.
    config = ConfigManager(config_path=str(tmp_path / "config.json"))

    monkeypatch.setattr("src.pages.service._page_service", pages)
    monkeypatch.setattr("src.schedules.service._schedule_service", schedules)
    monkeypatch.setattr("src.collections.service._collection_service", collections)
    monkeypatch.setattr("src.config_manager.ConfigManager._instance", config, raising=False)

    yield {"pages": pages, "schedules": schedules, "collections": collections, "config": config}


def _run(value: Any) -> Any:
    return asyncio.run(value) if asyncio.iscoroutine(value) else value


# ---------------------------------------------------------------------------
# Registry floors
# ---------------------------------------------------------------------------


def test_all_expected_prompts_are_registered(mcp):
    assert set(mcp._prompt_manager._prompts) == EXPECTED_PROMPTS


def test_all_expected_resources_are_registered(mcp):
    assert set(mcp._resource_manager._resources) == EXPECTED_RESOURCES


def test_all_expected_resource_templates_are_registered(mcp):
    assert set(mcp._resource_manager._templates) == EXPECTED_RESOURCE_TEMPLATES


# ---------------------------------------------------------------------------
# Prompts must render
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("prompt_name", sorted(EXPECTED_PROMPTS))
def test_prompt_renders_non_empty_text(mcp, services, prompt_name):
    """A prompt that raises or renders empty is a dead menu entry."""
    prompt = mcp._prompt_manager._prompts[prompt_name]
    required = [a.name for a in (prompt.arguments or []) if a.required]
    assert not required, (
        f"{prompt_name} now has required arguments {required}; this test calls it with none, "
        "so it needs a case supplying them"
    )

    # Optional arguments are omitted deliberately: a prompt must render
    # usefully when a client invokes it straight off a menu with nothing filled in.
    rendered = _run(prompt.fn())

    text = rendered if isinstance(rendered, str) else json.dumps(rendered, default=str)
    assert text and text.strip(), f"{prompt_name} rendered empty"
    assert len(text.strip()) > 40, f"{prompt_name} rendered suspiciously little text: {text!r}"


def test_prompt_arguments_are_described(mcp):
    """A bare argument name is all the user sees in a client's prompt form.

    MCP clients render prompt arguments as an input form, labelled from
    ``description``. When that is None the user gets a naked field name and
    has to guess what belongs in it.
    """
    undescribed: list[str] = []
    for name, prompt in sorted(mcp._prompt_manager._prompts.items()):
        for arg in prompt.arguments or []:
            if not (arg.description or "").strip():
                undescribed.append(f"{name}.{arg.name}")
    assert not undescribed, f"prompt arguments with no description: {undescribed}"


@pytest.mark.parametrize("prompt_name", sorted(EXPECTED_PROMPTS))
def test_prompt_body_references_only_tools_that_exist(mcp, services, prompt_name):
    """A prompt naming a renamed tool sends the model somewhere that isn't there.

    Complements the description-level check in test_mcp_skill_quality.py —
    this one reads the *rendered body*, which is what actually reaches the
    model.
    """
    import re

    known = set(mcp._tool_manager._tools)
    # Prose that looks like a call but isn't a tool reference.
    ignore = {"e.g", "i.e", "etc"}

    rendered = _run(mcp._prompt_manager._prompts[prompt_name].fn())
    text = rendered if isinstance(rendered, str) else json.dumps(rendered, default=str)

    refs = {n for n in re.findall(r"\b([a-z_][a-z0-9_]{2,})\(\)", text) if n not in ignore}
    dangling = sorted(refs - known)
    assert not dangling, f"{prompt_name} tells the model to call tools that do not exist: {dangling}"


# ---------------------------------------------------------------------------
# Resources must read
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("uri", sorted(EXPECTED_RESOURCES))
def test_resource_reads_and_returns_declared_mime_type(mcp, services, uri):
    resource = mcp._resource_manager._resources[uri]
    content = _run(resource.fn())

    assert content is not None, f"{uri} returned None"
    assert isinstance(content, str), f"{uri} returned {type(content).__name__}, expected str"

    mime = (resource.mime_type or "").lower()
    if "json" in mime:
        json.loads(content)  # raises if the declared type is a lie


def test_page_preview_resource_template_renders_html_for_a_real_page(mcp, services):
    """The one URI template on the surface, exercised with a real page id."""
    create = mcp._tool_manager._tools["create_page"].fn(
        name="Preview Target", template_lines=FLAGSHIP_TEMPLATE, device_type="flagship"
    )
    page_id = create["page_id"]

    template = mcp._resource_manager._templates["fiestaboard://page/{page_id}/preview.html"]
    html = _run(template.fn(page_id=page_id))

    assert isinstance(html, str) and html.strip(), "page preview resource rendered nothing"
    assert "<" in html, "page preview resource is declared text/html but returned no markup"


def test_pages_resource_reflects_a_page_created_through_a_tool(mcp, services):
    """Resources must read live state, not a snapshot taken at registration."""
    mcp._tool_manager._tools["create_page"].fn(
        name="Visible In Resource", template_lines=FLAGSHIP_TEMPLATE, device_type="flagship"
    )
    content = _run(mcp._resource_manager._resources["fiestaboard://pages"].fn())
    assert "Visible In Resource" in content
