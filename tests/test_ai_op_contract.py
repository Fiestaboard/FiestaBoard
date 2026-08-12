"""Contract test: the AI chat-op grammar must agree across every surface.

The streaming chat lets the model emit ``fiestaboard`` fenced JSON blocks,
each one an *operation* the frontend applies. Three places have to agree on
what ops exist:

1. ``src/ai/chat_ops.py`` — ``_OP_REGISTRY``, the server-side validator and
   the source of the list the system prompt advertises to the model.
2. ``web/src/lib/ai-chat-types.ts`` — the ``ToolCall`` discriminated union.
3. Every ``switch (call.op)`` in the web client that consumes a ``ToolCall``.

Nothing enforced that agreement, and it had already drifted. ``labelFor()``
in ``ai-chat-panel.tsx`` is declared ``: string`` and switches on ``call.op``
with no ``default``, but handled only 15 of the 19 ops. For
``navigate_to_schedule``, ``enable_plugin``, ``disable_plugin`` and
``uninstall_plugin`` — all of which the backend can emit — it fell off the
end and returned ``undefined`` from a function typed ``string``.

This is the same shape as #1559/#1561 on the MCP side: several surfaces that
must agree, only some of them do, and no test looks across the boundary.

Why a ``default`` clause matters
--------------------------------

An op-switch *with* a ``default`` is safe by construction — an unknown op
degrades to a generic branch. ``buildToolResultText()`` in
``global-ai-chat-drawer.tsx`` does exactly that and is fine. So the rule
enforced here is narrow and behavioral rather than stylistic:

    a switch over ``.op`` that has no ``default`` must cover every op.

Why regex and not a TS parser
-----------------------------

The Python test image has no TypeScript toolchain, and shelling out to one
would make this test depend on ``npm install`` having run. The patterns
matched here (``op: "name"`` in a union, ``case "name":`` in a switch) are
narrow enough to parse reliably, and the meta-tests below prove the parser
actually resolves symbols rather than silently finding nothing.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.ai.chat_ops import _OP_REGISTRY, supported_ops

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB = REPO_ROOT / "web"

TS_TYPES = WEB / "src/lib/ai-chat-types.ts"
CHAT_PANEL = WEB / "src/components/ai-chat-panel.tsx"
CHAT_DRAWER = WEB / "src/components/global-ai-chat-drawer.tsx"

# A parse that resolves nothing passes vacuously. These floors fail loudly if
# the source moves or the declaration style changes such that the analyzer
# stops recognizing it, rather than quietly reporting no drift.
MIN_UNION_OPS = 19
MIN_SWITCH_CASES = 15


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _match_braces(text: str, open_idx: int) -> int:
    """Return the index just past the ``}`` closing the brace at *open_idx*.

    Naive depth counting. Adequate here because the regions scanned are
    switch bodies over string literals — the only braces are structural or
    inside template strings, and template strings in these files are balanced.
    """
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    raise ValueError(f"unbalanced braces from index {open_idx}")


def _ts_union_ops(path: Path) -> set[str]:
    """Extract the op names declared in the ``ToolCall`` union.

    Scans line-wise rather than with a single regex: each union member is
    ``| { id: string; op: "name"; args: T }``, so a non-greedy match to the
    first ``;`` stops inside the *first member's* braces and silently returns
    nothing. The declaration ends at the first line whose content ends in
    ``;`` — that is the final member.
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = next(
        (i for i, ln in enumerate(lines) if re.match(r"\s*export type ToolCall\s*=", ln)),
        None,
    )
    if start is None:
        raise AssertionError(f"Could not find the `export type ToolCall` union in {path}")

    collected: list[str] = []
    for ln in lines[start:]:
        collected.append(ln)
        if ln.rstrip().endswith(";"):
            break
    else:
        raise AssertionError(f"`export type ToolCall` in {path} is never terminated by ';'")

    return set(re.findall(r'op:\s*"([a-z_]+)"', "\n".join(collected)))


def _op_switch(path: Path, func_name: str) -> tuple[set[str], bool]:
    """Return ``(case_ops, has_default)`` for the ``.op`` switch in *func_name*.

    Locates the function, brace-matches its body, then finds the ``switch``
    inside it that discriminates on something ending in ``.op``.
    """
    text = path.read_text(encoding="utf-8")
    m = re.search(rf"function\s+{re.escape(func_name)}\s*\(", text)
    if m is None:
        raise AssertionError(f"Could not find function {func_name}() in {path}")

    body_open = text.index("{", m.end())
    body = text[body_open : _match_braces(text, body_open)]

    sw = re.search(r"switch\s*\(\s*[A-Za-z_][\w.]*\.op\s*\)\s*\{", body)
    if sw is None:
        raise AssertionError(f"{func_name}() in {path} has no switch over `.op`")

    block_open = body.index("{", sw.end() - 1)
    block = body[block_open : _match_braces(body, block_open)]

    cases = set(re.findall(r'case\s+"([a-z_]+)"\s*:', block))
    has_default = re.search(r"\bdefault\s*:", block) is not None
    return cases, has_default


# ---------------------------------------------------------------------------
# Meta-tests — prove the analyzer can actually fail and is not scanning air
# ---------------------------------------------------------------------------


def test_union_parser_resolves_a_realistic_floor():
    assert len(_ts_union_ops(TS_TYPES)) >= MIN_UNION_OPS


def test_switch_parser_resolves_a_realistic_floor():
    cases, _ = _op_switch(CHAT_DRAWER, "buildToolResultText")
    assert len(cases) >= MIN_SWITCH_CASES


def test_union_parser_flags_a_known_bad_input(tmp_path):
    f = tmp_path / "types.ts"
    f.write_text(
        'export type ToolCall =\n'
        '  | { id: string; op: "alpha"; args: A }\n'
        '  | { id: string; op: "beta"; args: B };\n',
        encoding="utf-8",
    )
    assert _ts_union_ops(f) == {"alpha", "beta"}


def test_switch_parser_flags_a_known_bad_input(tmp_path):
    """A switch missing an op and missing a default must be reported as such."""
    f = tmp_path / "panel.tsx"
    f.write_text(
        "function labelFor(call: ToolCall): string {\n"
        "  switch (call.op) {\n"
        '    case "alpha":\n'
        '      return "A";\n'
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    cases, has_default = _op_switch(f, "labelFor")
    assert cases == {"alpha"}
    assert has_default is False


def test_switch_parser_detects_a_default_clause(tmp_path):
    f = tmp_path / "panel.tsx"
    f.write_text(
        "function labelFor(call: ToolCall): string {\n"
        "  switch (call.op) {\n"
        '    case "alpha":\n'
        '      return "A";\n'
        "    default:\n"
        '      return "?";\n'
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    _, has_default = _op_switch(f, "labelFor")
    assert has_default is True


def test_missing_function_is_an_error_not_an_empty_result(tmp_path):
    f = tmp_path / "panel.tsx"
    f.write_text("const x = 1;\n", encoding="utf-8")
    with pytest.raises(AssertionError):
        _op_switch(f, "labelFor")


# ---------------------------------------------------------------------------
# The actual contract
# ---------------------------------------------------------------------------


def test_python_registry_matches_the_typescript_union():
    py = set(_OP_REGISTRY)
    ts = _ts_union_ops(TS_TYPES)
    assert py == ts, (
        "chat-op grammar has drifted between Python and TypeScript.\n"
        f"  Python only: {sorted(py - ts)}\n"
        f"  TypeScript only: {sorted(ts - py)}"
    )


def test_supported_ops_matches_the_registry():
    """The list advertised to the model must be the list we can validate.

    ``supported_ops()`` feeds the system prompt. If it drifts from
    ``_OP_REGISTRY``, the model is either told about an op that
    ``parse_tool_call`` will reject, or never told about one it could use.
    """
    assert set(supported_ops()) == set(_OP_REGISTRY)


@pytest.mark.parametrize(
    ("path", "func"),
    [
        (CHAT_PANEL, "labelFor"),
        (CHAT_DRAWER, "buildToolResultText"),
    ],
    ids=["ai-chat-panel:labelFor", "global-ai-chat-drawer:buildToolResultText"],
)
def test_op_switches_are_exhaustive_or_have_a_default(path, func):
    ops = _ts_union_ops(TS_TYPES)
    cases, has_default = _op_switch(path, func)
    if has_default:
        pytest.skip(f"{func}() has a default clause — unknown ops degrade safely")
    missing = ops - cases
    assert not missing, (
        f"{path.relative_to(REPO_ROOT)}::{func}() switches on .op with no `default` "
        f"clause, so these ops fall through and return undefined: {sorted(missing)}"
    )
