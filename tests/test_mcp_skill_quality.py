"""Contract test: the MCP surface must describe itself accurately.

An MCP client sees this server only through what it advertises: tool names,
tool descriptions, parameter schemas, prompt text. A tool can be perfectly
correct and still unusable if its description points the model at a tool
that no longer exists, or documents a parameter it does not take.

That failure mode is invisible to every other test we have. ``tools/list``
still returns 200. The tool still works when called correctly. Nothing
raises. The model simply gets bad instructions and does the wrong thing —
and the only symptom is a user saying "the AI couldn't figure it out".

What is checked here
--------------------

- Every tool, prompt and resource has a non-empty description.
- Every ``Args:`` entry in a tool docstring names a real parameter, and
  every parameter appears in ``Args:``. A renamed parameter that leaves its
  docstring behind actively misleads the model.
- Every ``tool_name()`` cross-reference inside a description resolves to a
  registered tool. Descriptions routinely say things like
  "(from list_pages() or list_collections())"; a rename silently strands
  those.
- The hardcoded prompt roster in the server ``instructions`` matches the
  prompts actually registered.

What is deliberately NOT checked
--------------------------------

Whether a model *chooses* the right tool given these descriptions. That is
probabilistic and needs a real model in the loop — an eval, not a test. The
checks here cover the deterministic subset: the cases where selection could
not possibly work because the description is self-contradictory or points
into thin air.

Note on parameter schemas: FastMCP does not lift a docstring's ``Args:``
section into the JSON Schema, so ``parameters.properties[x].description`` is
absent for every tool in this server. The whole docstring is shipped as the
tool description instead, so the Args text does reach the model. Asserting on
schema-level descriptions would therefore fail all 28 tools while describing
no defect — hence the docstring-consistency check below instead.
"""

from __future__ import annotations

import re

import pytest

pytest.importorskip("mcp", reason="mcp package not installed")

from src.mcp_server import _build_mcp_server

# Floors. A scan that resolves nothing passes vacuously; these fail loudly if
# the registry shape changes such that the analyzer goes blind.
MIN_TOOLS = 28
MIN_PROMPTS = 5
MIN_RESOURCES = 6

# Words that look like `something()` in prose but are not tool references.
_NOT_TOOL_REFS = {
    "e.g",
    "i.e",
    "etc",
    "HH:MM",
}


@pytest.fixture(scope="module")
def mcp():
    instance = _build_mcp_server()
    assert instance is not None, "mcp installed but _build_mcp_server() returned None"
    return instance


@pytest.fixture(scope="module")
def tools(mcp):
    return mcp._tool_manager._tools


@pytest.fixture(scope="module")
def prompts(mcp):
    return mcp._prompt_manager._prompts


@pytest.fixture(scope="module")
def resources(mcp):
    # Static resources plus URI templates like fiestaboard://page/{id}/preview.html
    return {**mcp._resource_manager._resources, **mcp._resource_manager._templates}


# ---------------------------------------------------------------------------
# Floors — prove the analyzer is looking at a real registry
# ---------------------------------------------------------------------------


def test_tool_registry_floor(tools):
    assert len(tools) >= MIN_TOOLS


def test_prompt_registry_floor(prompts):
    assert len(prompts) >= MIN_PROMPTS


def test_resource_registry_floor(resources):
    assert len(resources) >= MIN_RESOURCES


# ---------------------------------------------------------------------------
# Descriptions exist
# ---------------------------------------------------------------------------


def test_every_tool_has_a_description(tools):
    missing = sorted(n for n, t in tools.items() if not (t.description or "").strip())
    assert not missing, f"tools with no description: {missing}"


def test_every_prompt_has_a_description(prompts):
    missing = sorted(n for n, p in prompts.items() if not (p.description or "").strip())
    assert not missing, f"prompts with no description: {missing}"


def test_every_resource_has_a_description(resources):
    missing = sorted(k for k, r in resources.items() if not (r.description or "").strip())
    assert not missing, f"resources with no description: {missing}"


# ---------------------------------------------------------------------------
# Docstring Args: must match the real signature
# ---------------------------------------------------------------------------


def _documented_args(description: str) -> set[str]:
    """Parse the ``Args:`` block of a Google-style docstring."""
    m = re.search(
        r"^\s*Args:\s*$(.*?)(?=^\s*(?:Returns|Raises|Examples?|Note):|\Z)", description, re.MULTILINE | re.DOTALL
    )
    if m is None:
        return set()
    return set(re.findall(r"^\s{4,}(\w+)\s*:", m.group(1), re.MULTILINE))


def test_documented_args_match_real_parameters(tools):
    problems: list[str] = []
    for name, tool in sorted(tools.items()):
        real = set((tool.parameters or {}).get("properties", {}))
        documented = _documented_args(tool.description or "")
        if not documented and not real:
            continue
        if not documented and real:
            problems.append(f"{name}: takes {sorted(real)} but documents no Args:")
            continue
        phantom = documented - real
        undocumented = real - documented
        if phantom:
            problems.append(f"{name}: documents non-existent params {sorted(phantom)}")
        if undocumented:
            problems.append(f"{name}: params not documented {sorted(undocumented)}")
    assert not problems, "tool docstrings disagree with their signatures:\n  " + "\n  ".join(problems)


def test_args_parser_flags_a_known_bad_input():
    """Meta-test: the Args parser must actually extract names."""
    doc = "Do a thing.\n\nArgs:\n    alpha: first\n    beta: second\n\nReturns:\n    stuff\n"
    assert _documented_args(doc) == {"alpha", "beta"}


def test_args_parser_returns_empty_when_absent():
    assert _documented_args("No args block here.") == set()


# ---------------------------------------------------------------------------
# Cross-references must resolve
# ---------------------------------------------------------------------------


def _tool_refs(text: str) -> set[str]:
    """Names written as ``something()`` in prose."""
    return {n for n in re.findall(r"\b([a-z_][a-z0-9_]{2,})\(\)", text) if n not in _NOT_TOOL_REFS}


def test_tool_cross_references_resolve(tools):
    known = set(tools)
    dangling: list[str] = []
    for name, tool in sorted(tools.items()):
        for ref in sorted(_tool_refs(tool.description or "")):
            if ref not in known:
                dangling.append(f"{name} -> {ref}()")
    assert not dangling, (
        "tool descriptions reference tools that do not exist, so a model "
        "following them will call into thin air:\n  " + "\n  ".join(dangling)
    )


def test_prompt_cross_references_resolve(prompts, tools):
    known = set(tools)
    dangling: list[str] = []
    for name, prompt in sorted(prompts.items()):
        for ref in sorted(_tool_refs(prompt.description or "")):
            if ref not in known:
                dangling.append(f"{name} -> {ref}()")
    assert not dangling, "prompt descriptions reference non-existent tools:\n  " + "\n  ".join(dangling)


def test_tool_ref_parser_flags_a_known_bad_input():
    assert _tool_refs("use list_pages() or get_page() first") == {"list_pages", "get_page"}


# ---------------------------------------------------------------------------
# The hardcoded prompt roster in `instructions` must match reality
# ---------------------------------------------------------------------------


def test_instructions_prompt_roster_matches_registered_prompts(mcp, prompts):
    """The connection instructions name the prompts by hand.

    That list is a string literal, so adding or renaming a prompt does not
    update it. A client told to invoke a prompt that no longer exists gets a
    dead end.
    """
    instructions = mcp.instructions or ""
    m = re.search(r"PROMPTS:(.*?)\.", instructions, re.DOTALL)
    assert m, "could not find the 'Available user-invokable PROMPTS:' roster in instructions"

    advertised = set(re.findall(r"[a-z_][a-z0-9_]+", m.group(1)))
    registered = set(prompts)
    assert advertised == registered, (
        "the prompt roster in the server instructions has drifted from the registry.\n"
        f"  advertised but not registered: {sorted(advertised - registered)}\n"
        f"  registered but not advertised: {sorted(registered - advertised)}"
    )
