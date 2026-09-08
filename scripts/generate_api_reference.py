#!/usr/bin/env python3
"""Generate ``docs/reference/api-endpoints.md`` from the published OpenAPI document.

Why this exists
---------------
``docs/reference/api-endpoints.md`` is what fiestaboard.app publishes as the API
reference, and until this script it was 324 hand-written lines describing ~51
operations as markdown tables. It had already drifted: it told consumers to call
``POST /send-message`` and ``POST /refresh``, the two endpoints the product's own
web UI never calls and which are now deprecated aliases, while saying nothing
about ``/v1`` — the surface a consumer should actually build against — and
nothing at all about how a script authenticates.

A hand-maintained API reference rots. This project already learned that once:
the MCP teaching text advertised two template filters that never existed and
froze a fifteen-function formula roster, and the fix was to generate it from the
modules that define the behaviour. This is the same fix, applied to the same
failure mode.

What it reads
-------------
The **published** document — ``app.openapi()``, 33 operations — not the internal
one at ``/api/internal/openapi.json``. The internal document is the web UI's
private RPC contract with no compatibility promise (see ``src/v1/visibility.py``);
publishing it as a consumer reference is the problem this whole surface removed.

The introduction is **not written here**. It is ``src.api_server.API_DESCRIPTION``,
the same text ``/api/docs`` renders as its front page, mechanically normalised for
markdownlint and MDX. Two hand-written introductions is exactly the drift this
script exists to remove, so there is only one, and it lives next to the app.

Usage
-----
::

    python scripts/generate_api_reference.py           # write the file
    python scripts/generate_api_reference.py --check    # fail if it is stale

``--check`` is what CI runs, the way a formatter's ``--check`` runs: it prints a
unified diff and exits 1 when the committed file differs from what the current
schema produces. Without it this script is something somebody ran once, and the
page starts rotting again the same day.
"""

from __future__ import annotations

import argparse
import difflib
import os
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

#: Where the generated page lands, relative to the repository root.
OUTPUT_PATH = Path("docs/reference/api-endpoints.md")

#: Frontmatter the Docusaurus site build depends on. ``sidebar_position`` and
#: ``description`` are load-bearing (``scripts/lint-docs-frontmatter.mjs``
#: fails a page with no non-empty ``description``); ``keywords`` feeds the
#: page's meta tags. Carried over verbatim from the hand-written page so the
#: published page's identity and search ranking do not move.
FRONTMATTER = {
    "sidebar_position": "1",
    "description": (
        '"The generated FiestaBoard REST API reference: every published '
        'operation, its parameters, request body, responses and errors."'
    ),
    "keywords": ("[FiestaBoard API, REST API, API endpoints, API reference, display API, split-flap API]"),
}

PAGE_TITLE = "API Endpoints"

#: The operation the page has to lead with. A consumer who reads nothing else
#: should still be able to put text on a board. Looked up in the schema rather
#: than described here, so this constant cannot outlive the route.
FRONT_DOOR = ("post", "/v1/boards/{board}/message")

#: The field the quick-start body sets. Asserted against the front door's own
#: request schema at generation time, so the worked example cannot drift into
#: naming a field the API does not accept.
FRONT_DOOR_BODY_FIELD = "text"

#: HTTP methods an OpenAPI path item may carry. Anything else in a path item
#: (``parameters``, ``summary``, vendor extensions) is not an operation.
HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")

#: Status classes, for splitting a responses map into "what you get" and
#: "what can go wrong".
SUCCESS_STATUSES = {"200", "201", "202", "204"}


# ---------------------------------------------------------------------------
# Text normalisation
#
# Three consumers have to be satisfied by every line this script emits, and
# each of them fails differently:
#
#   * markdownlint-cli2 — MD004 wants `-` list markers, and the reused
#     API description uses `*`;
#   * MDX — the site compiles .md as MDX, where a bare `{` opens a JS
#     expression and a bare `<` opens a tag. Schema descriptions are full of
#     `{red}`, `{board}` and `plugin:<id>`;
#   * markdown tables — a `|` in a cell ends the cell, and a newline ends
#     the row.
# ---------------------------------------------------------------------------

#: A ``{...}`` run with no whitespace inside: `{board}`, `{red}`, `{{var}}`.
#: Wrapped in backticks rather than escaped, because every one of them is a
#: path placeholder or a template marker and reads better as code anyway.
_BRACE_TOKEN = re.compile(r"\{+[^{}\s|]*\}+")

#: Splits text on inline code spans so the escaping below leaves them alone —
#: MDX does not interpret braces or angle brackets inside code.
_CODE_SPAN = re.compile(r"`[^`]*`")


def _map_outside_code(text: str, transform) -> str:
    """Apply ``transform`` to the parts of ``text`` that are not code spans."""
    out: list[str] = []
    cursor = 0
    for match in _CODE_SPAN.finditer(text):
        out.append(transform(text[cursor : match.start()]))
        out.append(match.group(0))
        cursor = match.end()
    out.append(transform(text[cursor:]))
    return "".join(out)


def _mdx_safe(text: str) -> str:
    """Make prose safe for the MDX compiler without mangling how it reads."""

    def harden(chunk: str) -> str:
        # Any brace or angle bracket left outside a code span is not a tidy
        # token (an unbalanced brace, an inline JSON fragment, `plugin:<id>`);
        # it still has to stop being JSX.
        return chunk.replace("{", "&#123;").replace("}", "&#125;").replace("<", "&lt;")

    def escape(chunk: str) -> str:
        # Wrap first, then re-split: the backticks this adds have to protect
        # what they wrap from the escaping below, or `{red}` renders as
        # `&#123;red&#125;`.
        wrapped = _BRACE_TOKEN.sub(lambda m: f"`{m.group(0)}`", chunk)
        return _map_outside_code(wrapped, harden)

    return _map_outside_code(text, escape)


#: ``*emphasis*``, but not ``**strong**``. markdownlint's MD049 wants
#: underscores in this repository, and Python docstrings do not.
_EMPHASIS = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")

#: A list item at the start of a line, in either marker style.
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+\.)\s")


def _house_style(text: str) -> str:
    """Bring a Python docstring in line with the repository's markdown rules.

    Every one of these is a markdownlint rule this repository already enforces
    on hand-written prose, and every one of them fired on the first generated
    draft. Fixing them at the source is what lets the generated page go through
    the same gate as the rest of the docs rather than being exempted from it.
    """
    lines: list[str] = []
    for raw in text.split("\n"):
        # MD004: `-` is the list marker here; docstrings use `*`.
        line = re.sub(r"^(\s*)\*(\s)", r"\1-\2", raw)
        # MD018: a line opening with an issue reference (`#1245 — ...`) reads
        # as a malformed ATX heading.
        line = re.sub(r"^(#+)(?![# ])", r"\\\1", line)
        # MD032: a list has to be separated from the paragraph above it.
        if _LIST_ITEM.match(line) and lines and lines[-1].strip() and not _LIST_ITEM.match(lines[-1]):
            lines.append("")
        lines.append(line)

    # MD049, outside code spans so `*` inside inline code survives.
    return _map_outside_code("\n".join(lines), lambda chunk: _EMPHASIS.sub(r"_\1_", chunk))


#: A fenced code block. Everything inside one is already exempt from MDX and
#: from markdownlint's list-marker rule, and rewriting it would corrupt the
#: worked example the API description carries.
_FENCE = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)


def normalise(text: str | None) -> str:
    """A schema/docstring description, rendered as repository markdown.

    Pydantic and FastAPI descriptions come from Python docstrings, which this
    codebase writes in reStructuredText: ``like this`` for code. Left alone
    that renders as a literal pair of backticks on the site. Bullets come
    through as ``*``, which markdownlint's MD004 rejects here.
    """
    if not text:
        return ""

    def prose(chunk: str) -> str:
        return _mdx_safe(_house_style(chunk.replace("``", "`")))

    out: list[str] = []
    cursor = 0
    for fence in _FENCE.finditer(text):
        out.append(prose(text[cursor : fence.start()]))
        out.append(fence.group(0))
        cursor = fence.end()
    out.append(prose(text[cursor:]))
    return "".join(out).strip()


def cell(text: str | None) -> str:
    """``normalise`` for a table cell: one line, pipes escaped."""
    flattened = " ".join(normalise(text).split())
    return flattened.replace("|", "\\|")


def reseat_headings(markdown: str, top: int = 2) -> str:
    """Shift every ATX heading so the shallowest one sits at level ``top``.

    The API description is the whole document on ``/api/docs``, where its
    sections are ``###``. Here it sits under this page's single ``#``, so its
    sections have to become ``##`` — otherwise the page opens with an
    ``h1``/``h4`` jump, which is both a markdownlint MD001 failure and a real
    problem for anyone navigating by headings.
    """
    levels = [len(m) for m in re.findall(r"^(#{1,6}) ", markdown, flags=re.MULTILINE)]
    if not levels:
        return markdown
    shift = top - min(levels)
    if shift == 0:
        return markdown

    def move(match: re.Match[str]) -> str:
        return "#" * max(1, min(6, len(match.group(1)) + shift)) + " "

    return re.sub(r"^(#{1,6}) ", move, markdown, flags=re.MULTILINE)


def slug(text: str) -> str:
    """A stable, explicit Docusaurus heading id.

    Generated headings carry backticks, braces and slashes; leaving the site
    to slugify them would make every deep link into this page a hostage to how
    a path is punctuated.
    """
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")


# ---------------------------------------------------------------------------
# Schema rendering
# ---------------------------------------------------------------------------


def schema_display_name(ref_name: str) -> str:
    """``src__v1__models__MessageRequest`` -> ``MessageRequest (v1)``.

    FastAPI qualifies a component name only when two models collide, and it
    does it with the full dotted module path. Both colliding names here are
    ``MessageRequest``; the module tail is what actually distinguishes them.
    """
    if "__" not in ref_name:
        return ref_name
    parts = ref_name.split("__")
    return f"{parts[-1]} ({parts[-3]})" if len(parts) >= 3 else parts[-1]


def schema_anchor(ref_name: str) -> str:
    return f"schema-{slug(ref_name)}"


def schema_link(ref_name: str) -> str:
    return f"[`{schema_display_name(ref_name)}`](#{schema_anchor(ref_name)})"


def ref_name_of(schema: dict[str, Any] | None) -> str | None:
    """The component name a ``$ref`` points at, if this schema is one."""
    if isinstance(schema, dict) and "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    return None


def render_type(schema: dict[str, Any] | None) -> str:
    """A one-line, linked rendering of a JSON Schema type."""
    if not schema:
        return "`any`"

    ref = ref_name_of(schema)
    if ref:
        return schema_link(ref)

    for combinator in ("anyOf", "oneOf"):
        if combinator in schema:
            members = [m for m in schema[combinator] if m.get("type") != "null"]
            nullable = len(members) != len(schema[combinator])
            rendered = " \\| ".join(render_type(m) for m in members) or "`any`"
            return f"{rendered} \\| `null`" if nullable else rendered

    if "allOf" in schema and len(schema["allOf"]) == 1:
        return render_type(schema["allOf"][0])

    if "enum" in schema:
        return " \\| ".join(f"`{value!r}`".replace("'", '"') for value in schema["enum"])

    kind = schema.get("type")
    if kind == "array":
        return f"array of {render_type(schema.get('items'))}"
    if kind == "object":
        extra = schema.get("additionalProperties")
        if isinstance(extra, dict) and extra:
            return f"object of {render_type(extra)}"
        return "`object`"
    if kind:
        return f"`{schema.get('format') or kind}`"
    return "`any`"


def render_constraints(schema: dict[str, Any]) -> str:
    """Bounds, defaults and formats, as a trailing sentence for a table cell.

    These live in the schema because a Pydantic ``Field`` put them there, so a
    reference that drops them is telling the reader less than the API knows.
    """
    inner = schema
    for combinator in ("anyOf", "oneOf"):
        if combinator in schema:
            members = [m for m in schema[combinator] if m.get("type") != "null"]
            if len(members) == 1:
                inner = members[0]

    notes: list[str] = []
    low, high = inner.get("minimum"), inner.get("maximum")
    if low is not None and high is not None:
        notes.append(f"{_number(low)}–{_number(high)}")
    elif low is not None:
        notes.append(f"min {_number(low)}")
    elif high is not None:
        notes.append(f"max {_number(high)}")
    if inner.get("minLength") is not None:
        notes.append(f"min length {inner['minLength']}")
    if inner.get("maxLength") is not None:
        notes.append(f"max length {inner['maxLength']}")
    if "default" in schema and schema["default"] is not None:
        notes.append(f"default `{_json_literal(schema['default'])}`")
    return "; ".join(notes)


def _number(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _json_literal(value: Any) -> str:
    import json

    return json.dumps(value)


def render_field_table(schema: dict[str, Any]) -> list[str]:
    """The properties of an object schema, as a markdown table."""
    properties: dict[str, Any] = schema.get("properties") or {}
    if not properties:
        described = normalise(schema.get("description"))
        return [described] if described else ["_No fields._"]

    required = set(schema.get("required") or [])
    lines = [
        "| Field | Type | Required | Description |",
        "|-------|------|----------|-------------|",
    ]
    for name, field in properties.items():
        description = cell(field.get("description"))
        constraints = render_constraints(field)
        if constraints:
            description = f"{description} ({constraints})" if description else constraints
        lines.append(
            f"| `{name}` | {render_type(field)} | {'yes' if name in required else 'no'} | {description or '—'} |"
        )
    return lines


# ---------------------------------------------------------------------------
# Operation rendering
# ---------------------------------------------------------------------------


def response_schema_name(response: dict[str, Any]) -> str:
    """What a response body is, as a linked name or an inline type."""
    content = response.get("content") or {}
    media = content.get("application/json")
    if not media or not media.get("schema"):
        return "no body" if not content else "—"
    return render_type(media["schema"])


#: ``POST /send-message`` and ``POST /refresh`` stay published because earlier
#: documentation named them; both open their description with the line below,
#: which is where the successor comes from. Generated from the description
#: rather than a table here, so the two cannot disagree.
_SUCCESSOR = re.compile(r"^Deprecated:\s*use\s+`+(?P<successor>[^`]+)`+\s*instead\.?", re.MULTILINE)


def successor_of(operation: dict[str, Any]) -> str | None:
    match = _SUCCESSOR.search((operation.get("description") or "").replace("``", "`"))
    return match.group("successor").strip() if match else None


def strip_successor_line(description: str) -> str:
    """The description without its ``Deprecated: use X instead.`` opener.

    The opener is rendered as an admonition instead, so leaving it in the body
    says the same thing twice.
    """
    return _SUCCESSOR.sub("", description.replace("``", "`"), count=1).strip()


def render_operation(
    method: str,
    path: str,
    operation: dict[str, Any],
    *,
    schemas: dict[str, Any],
) -> list[str]:
    signature = f"{method.upper()} {path}"
    heading_id = slug(signature)
    summary = operation.get("summary") or signature
    lines = [f"### `{signature}` {{#{heading_id}}}", ""]

    if operation.get("deprecated"):
        successor = successor_of(operation)
        replacement = f" Use `{successor}` instead." if successor else ""
        lines += [
            ":::warning Deprecated",
            "",
            f"`{signature}` is deprecated and answers with `Deprecation`, `Sunset` and",
            f'`Link: rel="successor-version"` headers.{replacement}',
            "",
            ":::",
            "",
        ]

    lines += [f"**{cell(summary)}**", ""]

    description = operation.get("description") or ""
    if operation.get("deprecated"):
        description = strip_successor_line(description)
    body = normalise(description)
    if body:
        lines += [body, ""]

    parameters = operation.get("parameters") or []
    if parameters:
        lines += ["**Parameters**", ""]
        lines += [
            "| Name | In | Type | Required | Description |",
            "|------|----|------|----------|-------------|",
        ]
        for parameter in parameters:
            description_cell = cell(parameter.get("description"))
            constraints = render_constraints(parameter.get("schema") or {})
            if constraints:
                description_cell = f"{description_cell} ({constraints})" if description_cell else constraints
            lines.append(
                f"| `{parameter['name']}` | {parameter.get('in', '—')} | "
                f"{render_type(parameter.get('schema'))} | "
                f"{'yes' if parameter.get('required') else 'no'} | {description_cell or '—'} |"
            )
        lines.append("")

    request_body = operation.get("requestBody")
    if request_body:
        media = (request_body.get("content") or {}).get("application/json") or {}
        body_schema = media.get("schema") or {}
        ref = ref_name_of(body_schema)
        required = "required" if request_body.get("required") else "optional"
        label = schema_link(ref) if ref else render_type(body_schema)
        lines += [f"**Request body** ({required}) — {label}", ""]
        if ref and ref in schemas:
            lines += render_field_table(schemas[ref])
        else:
            lines += render_field_table(body_schema)
        lines.append("")

    responses = operation.get("responses") or {}
    successes = {code: r for code, r in responses.items() if code in SUCCESS_STATUSES}
    failures = {code: r for code, r in responses.items() if code not in SUCCESS_STATUSES}

    if successes:
        lines += ["**Responses**", ""]
        lines += ["| Status | Body | Description |", "|--------|------|-------------|"]
        for code in sorted(successes):
            response = successes[code]
            lines.append(
                f"| `{code}` | {response_schema_name(response)} | {cell(response.get('description')) or '—'} |"
            )
        lines.append("")

    if failures:
        lines += ["**Errors**", ""]
        lines += ["| Status | Body | Meaning |", "|--------|------|---------|"]
        for code in sorted(failures):
            response = failures[code]
            lines.append(
                f"| `{code}` | {response_schema_name(response)} | {cell(response.get('description')) or '—'} |"
            )
        lines.append("")

    return lines


# ---------------------------------------------------------------------------
# Page assembly
# ---------------------------------------------------------------------------


def iter_operations(schema: dict[str, Any]):
    """``(method, path, operation)`` for every operation, in document order."""
    for path, path_item in schema.get("paths", {}).items():
        for method, operation in path_item.items():
            if method in HTTP_METHODS and isinstance(operation, dict):
                yield method, path, operation


def render_front_matter() -> list[str]:
    return [
        "---",
        *(f"{key}: {value}" for key, value in FRONTMATTER.items()),
        "---",
        "",
        "<!--",
        "  GENERATED FILE — DO NOT EDIT BY HAND.",
        "",
        "  Produced by scripts/generate_api_reference.py from the published OpenAPI",
        "  document (`app.openapi()`), so it cannot drift from the API it describes.",
        "  Edit the route, the Pydantic model or src/api_server.py::API_DESCRIPTION,",
        "  then regenerate:",
        "",
        "      python scripts/generate_api_reference.py",
        "",
        "  CI (`Lint Markdown` -> `Check the generated API reference is current`)",
        "  fails when this file differs from what the generator produces.",
        "-->",
        "",
    ]


def render_authentication(schema: dict[str, Any]) -> list[str]:
    """The security schemes, from the document rather than from memory.

    A script could not authenticate against this API at all before ``/v1``
    landed, and the hand-written page never said so. It is declared in
    ``src/v1/openapi.py`` now, which makes it generatable.
    """
    schemes = ((schema.get("components") or {}).get("securitySchemes") or {}).items()
    if not schemes:
        return []
    lines = [
        "## Credentials",
        "",
        "Either credential satisfies any request; which one you hold depends on whether",
        "you are a script or the web UI. Both are declared in the OpenAPI document, so a",
        "client generator picks them up.",
        "",
        "| Scheme | How it is sent | Notes |",
        "|--------|----------------|-------|",
    ]
    for name, scheme in schemes:
        if scheme.get("type") == "http":
            how = f"`Authorization: {str(scheme.get('scheme', '')).title()} <token>`"
        elif scheme.get("type") == "apiKey":
            how = f"`{scheme.get('name')}` ({scheme.get('in')})"
        else:
            how = scheme.get("type", "—")
        lines.append(f"| `{name}` | {how} | {cell(scheme.get('description'))} |")
    lines.append("")
    return lines


def render_quick_start(schema: dict[str, Any]) -> list[str]:
    """One runnable, authenticated request against the front door.

    Raises rather than degrades if the front door moved: a quick start that
    silently drops to "here are some endpoints" is how the old page ended up
    recommending two deprecated aliases.
    """
    method, path = FRONT_DOOR
    operation = (schema.get("paths") or {}).get(path, {}).get(method)
    if operation is None:
        raise SystemExit(
            f"the front door {method.upper()} {path} is not in the published schema; "
            "update FRONT_DOOR in scripts/generate_api_reference.py"
        )

    body_ref = ref_name_of(
        ((operation.get("requestBody") or {}).get("content") or {}).get("application/json", {}).get("schema") or {}
    )
    body_schema = ((schema.get("components") or {}).get("schemas") or {}).get(body_ref or "", {})
    if FRONT_DOOR_BODY_FIELD not in (body_schema.get("properties") or {}):
        raise SystemExit(f"the quick-start body sets `{FRONT_DOOR_BODY_FIELD}`, which {body_ref} no longer accepts")

    example_path = path.replace("{board}", "primary")
    return [
        "## Quick start",
        "",
        f"`{method.upper()} {path}` is the front door. `primary` works as a board id on",
        "every `/v1/boards/...` path, so a single-board install never has to look one up.",
        "",
        "```bash",
        f"curl -X {method.upper()} http://fiestaboard.local:4420/api{example_path} \\",
        '  -H "Authorization: Bearer $FIESTABOARD_TOKEN" \\',
        '  -H "Content-Type: application/json" \\',
        f'  -d \'{{"{FRONT_DOOR_BODY_FIELD}": "HELLO WORLD"}}\'',
        "```",
        "",
        "Drop the `Authorization` header on an install that has not turned",
        "authentication on — it is off by default.",
        "",
    ]


def render_page(schema: dict[str, Any], *, description: str) -> str:
    schemas: dict[str, Any] = (schema.get("components") or {}).get("schemas") or {}

    lines = render_front_matter()
    lines += [f"# {PAGE_TITLE}", ""]
    lines += [normalise(reseat_headings(description)), ""]
    lines += render_authentication(schema)
    lines += render_quick_start(schema)

    # Tag order is the document's own — `src/v1/openapi.py` prepends `v1`
    # deliberately, so the consumer surface leads here for the same reason it
    # leads in Swagger.
    tag_descriptions = {tag["name"]: tag.get("description", "") for tag in schema.get("tags", [])}
    grouped: dict[str, list[tuple[str, str, dict[str, Any]]]] = {name: [] for name in tag_descriptions}
    untagged: list[tuple[str, str, dict[str, Any]]] = []
    for method, path, operation in iter_operations(schema):
        tags = operation.get("tags") or []
        if tags and tags[0] in grouped:
            grouped[tags[0]].append((method, path, operation))
        else:
            untagged.append((method, path, operation))

    total = 0
    for tag, operations in grouped.items():
        if not operations:
            continue
        total += len(operations)
        lines += [f"## `{tag}` {{#tag-{slug(tag)}}}", ""]
        tag_description = normalise(tag_descriptions.get(tag))
        if tag_description:
            lines += [tag_description, ""]
        for method, path, operation in operations:
            lines += render_operation(method, path, operation, schemas=schemas)
    if untagged:
        total += len(untagged)
        lines += ["## Other operations {#tag-other}", ""]
        for method, path, operation in untagged:
            lines += render_operation(method, path, operation, schemas=schemas)

    if schemas:
        lines += [
            "## Schemas",
            "",
            "Every model the operations above name, expanded once.",
            "",
        ]
        for name in sorted(schemas, key=lambda n: (schema_display_name(n).lower(), n)):
            model = schemas[name]
            lines += [f"### `{schema_display_name(name)}` {{#{schema_anchor(name)}}}", ""]
            model_description = normalise(model.get("description"))
            if model_description:
                lines += [model_description, ""]
            lines += render_field_table(model)
            lines.append("")

    lines += [
        "## Where the rest of the API went",
        "",
        f"This page documents the {total} operations the app publishes. The other",
        "~200 paths the app serves are the web UI's private RPC channel: they still",
        "answer exactly as they always have, but they are undocumented on purpose,",
        "carry no compatibility promise, and may change in any release. They are",
        "published separately at `/api/internal/openapi.json` so the UI keeps a",
        "contract to check itself against.",
        "",
        "## Next steps",
        "",
        "- [Docker Setup](/docs/setup/docker-setup) — how the API is served and proxied",
        "- [Plugin Configuration](/docs/plugins/configuration) — configuring plugins over the API",
        "- `/api/docs` — the same operations as a Swagger explorer you can send requests from",
        "",
    ]

    rendered = "\n".join(lines)
    # Collapse the runs of blank lines the section-by-section assembly leaves
    # behind (markdownlint MD012), and end with exactly one newline.
    rendered = re.sub(r"\n{3,}", "\n\n", rendered)
    return rendered.rstrip("\n") + "\n"


def build() -> str:
    """The page, rendered from the app the repository actually defines."""
    # The schema must not depend on how the generating machine is configured;
    # an auth-enabled run and an auth-disabled run have to produce the same
    # document, or `--check` fails for a reason that is not drift.
    os.environ.setdefault("BOARD_READ_WRITE_KEY", "generator")

    from src.api_server import API_DESCRIPTION, app

    return render_page(app.openapi(), description=API_DESCRIPTION)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; exit 1 with a diff if the committed page is stale",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / OUTPUT_PATH,
        help=f"where to write (default: {OUTPUT_PATH})",
    )
    args = parser.parse_args(argv)

    generated = build()

    if args.check:
        current = args.output.read_text(encoding="utf-8") if args.output.exists() else ""
        if current == generated:
            print(f"✅ {OUTPUT_PATH} is up to date")
            return 0
        diff = difflib.unified_diff(
            current.splitlines(keepends=True),
            generated.splitlines(keepends=True),
            fromfile=f"{OUTPUT_PATH} (committed)",
            tofile=f"{OUTPUT_PATH} (generated)",
        )
        sys.stdout.writelines(diff)
        print(
            f"\n❌ {OUTPUT_PATH} is stale — the API changed and the reference did not.\n"
            "   Regenerate it and commit the result:\n"
            "       python scripts/generate_api_reference.py",
            file=sys.stderr,
        )
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(generated, encoding="utf-8")
    print(f"✅ wrote {OUTPUT_PATH} ({generated.count(chr(10))} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
