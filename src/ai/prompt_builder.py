"""Build the LLM prompt for the "Gen AI" page-generation feature.

Pure functions, no I/O. Easy to unit-test.

The output is a list of OpenAI-compatible chat messages
(``[{role: "system", ...}, {role: "user", ...}]``) along with
metadata describing what was sent (used for the
``GET /pages/ai/context`` debug endpoint).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from ..devices import DeviceType, get_dimensions
from ..templates.expressions import function_signatures


# Which caller is building the prompt. The shared core (device limits,
# character set, syntax, available variables, exemplars) is identical
# for both; only the output contract and the off-topic refusal shape
# differ — see ``_scope_rules`` and ``_output_rules`` below.
PromptMode = Literal["generate", "chat"]


# Hand-curated fallback exemplars. Used when no enabled plugin manifest
# provides a ``demo`` block matching the requested device_type. Kept
# small to keep the prompt cheap; the model only needs a couple of
# examples to learn the JSON shape.
_FALLBACK_EXEMPLARS: List[Dict[str, Any]] = [
    {
        "name": "Weather + time (flagship)",
        "device_type": "flagship",
        "template": [
            "",
            "{{date_time.day_of_week}}",
            "{{date_time.month}} {{date_time.day}}",
            "{{date_time.time_12h}}",
            "{{weather.temperature}}F  {{weather.condition}}",
            "",
        ],
        "line_metadata": [
            {"alignment": "center", "wrap": False},
            {"alignment": "center", "wrap": False},
            {"alignment": "center", "wrap": False},
            {"alignment": "center", "wrap": False},
            {"alignment": "center", "wrap": False},
            {"alignment": "center", "wrap": False},
        ],
        "duration_seconds": 300,
    },
    {
        "name": "Plain announcement (note)",
        "device_type": "note",
        "template": [
            "{{red}}HELLO{{red}}",
            "{{date_time.time_12h}}",
            "Have a great day",
        ],
        "line_metadata": [
            {"alignment": "center", "wrap": False},
            {"alignment": "center", "wrap": False},
            {"alignment": "center", "wrap": False},
        ],
        "duration_seconds": 300,
    },
]


# OpenAI/JSON-schema description of the page payload we want the model
# to return. Embedded verbatim in the system prompt so the model knows
# the exact expected shape.
_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["name", "type", "device_type", "template"],
    "properties": {
        "name": {
            "type": "string",
            "description": "Short, human-readable page name (1-100 chars).",
            "maxLength": 100,
        },
        "type": {
            "type": "string",
            "enum": ["template"],
            "description": "Always 'template' for AI-generated pages.",
        },
        "device_type": {
            "type": "string",
            "enum": ["flagship", "note"],
        },
        "template": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Lines of template content. Number of items must equal "
                "the device's row count. Use {{plugin.field}} variable "
                "syntax and {color} tokens. Empty strings are allowed."
            ),
        },
        "line_metadata": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "alignment": {
                        "type": "string",
                        "enum": ["left", "center", "right"],
                    },
                    "wrap": {"type": "boolean"},
                },
                "required": ["alignment", "wrap"],
            },
            "description": (
                "Per-line formatting; same length as template. "
                "Set wrap=true only when the line is longer than the "
                "device's column count and you want it to flow onto "
                "later rows."
            ),
        },
        "duration_seconds": {
            "type": "integer",
            "minimum": 10,
            "maximum": 3600,
            "description": "How long to display this page (10-3600).",
        },
    },
}


@dataclass
class PromptContext:
    """Captures everything that was sent to the model.

    Exposed via ``GET /pages/ai/context`` so users can inspect what
    context the AI receives. Never includes API keys.
    """

    device_type: str
    rows: int
    cols: int
    user_prompt: str
    variables: Dict[str, Dict[str, Dict[str, Any]]] = field(default_factory=dict)
    exemplars: List[Dict[str, Any]] = field(default_factory=list)
    current_page: Optional[Dict[str, Any]] = None
    system_prompt: str = ""

    def to_messages(self) -> List[Dict[str, str]]:
        """Render as an OpenAI-compatible messages list."""
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": self.system_prompt},
        ]
        if self.current_page is not None:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "The user is refining an existing page. Current page "
                        "JSON:\n"
                        + json.dumps(self.current_page, indent=2)
                    ),
                }
            )
        messages.append({"role": "user", "content": self.user_prompt})
        return messages

    def to_dict(self) -> Dict[str, Any]:
        """Serializable copy used by the debug endpoint."""
        return {
            "device_type": self.device_type,
            "rows": self.rows,
            "cols": self.cols,
            "user_prompt": self.user_prompt,
            "variables": self.variables,
            "exemplars": self.exemplars,
            "current_page": self.current_page,
            "system_prompt": self.system_prompt,
        }


def _format_builtins() -> str:
    """Render the formula function registry as a compact reference list.

    Pulled live from ``expressions.function_signatures()`` so the prompt
    stays in sync if functions are added or renamed.
    """
    sigs = function_signatures()
    by_cat: Dict[str, List[str]] = {}
    for name, info in sigs.items():
        by_cat.setdefault(info["category"], []).append(
            f"  {info['signature']:<40} — {info['summary']}"
        )
    order = ["logic", "math", "text", "convert", "color"]
    lines: List[str] = []
    for cat in order:
        rows = by_cat.get(cat)
        if not rows:
            continue
        lines.append(f"  [{cat}]")
        lines.extend(sorted(rows))
    # Catch any categories not in the explicit order list.
    for cat, rows in by_cat.items():
        if cat in order:
            continue
        lines.append(f"  [{cat}]")
        lines.extend(sorted(rows))
    return "\n".join(lines)


def _format_variables(
    variables: Dict[str, Dict[str, Dict[str, Any]]],
) -> str:
    """Render the variable registry as a compact, model-friendly listing."""
    if not variables:
        return "(no variables available — only static text and color tokens may be used)"
    lines: List[str] = []
    for plugin_id in sorted(variables.keys()):
        var_dict = variables[plugin_id]
        lines.append(f"\n[{plugin_id}]")
        for var_name in sorted(var_dict.keys()):
            meta = var_dict[var_name] or {}
            desc = meta.get("description") or ""
            example = meta.get("example") or meta.get("preview") or ""
            max_len = meta.get("max_length")
            parts = [f"  {{{{{plugin_id}.{var_name}}}}}"]
            if desc:
                parts.append(f"— {desc}")
            extras: List[str] = []
            if example:
                extras.append(f"example: {example}")
            if max_len:
                extras.append(f"max {max_len} chars")
            if extras:
                parts.append(f"({'; '.join(extras)})")
            lines.append(" ".join(parts))
    return "\n".join(lines).strip()


def _select_exemplars(
    device_type: str,
    plugin_demos: List[Dict[str, Any]],
    max_examples: int = 3,
) -> List[Dict[str, Any]]:
    """Pick a small set of example pages matching ``device_type``.

    Prefers plugin-supplied demos over the hand-curated fallback. Always
    returns at least one example so the model sees the expected shape.
    """
    matching = [d for d in plugin_demos if d.get("device_type") == device_type]
    selected = matching[:max_examples]
    if len(selected) < max_examples:
        for fallback in _FALLBACK_EXEMPLARS:
            if fallback.get("device_type") != device_type:
                continue
            if len(selected) >= max_examples:
                break
            selected.append(fallback)
    if not selected:
        # Last resort: return any fallback; better something than nothing.
        selected = _FALLBACK_EXEMPLARS[:1]
    return selected


def _format_available_pages(pages: List[Dict[str, Any]]) -> str:
    """Render a compact list of pages the user can navigate to."""
    if not pages:
        return "(no pages yet)"
    return "\n".join(
        f'  - "{p.get("name", "Untitled")}" (id: {p.get("id", "?")})'
        for p in pages
    )


def _format_installed_plugins(plugins: List[Dict[str, Any]]) -> str:
    """Render a compact list of installed plugins and their status."""
    if not plugins:
        return "(no plugins installed)"
    lines = []
    for p in plugins:
        status = "enabled" if p.get("enabled") else "disabled"
        lines.append(f'  - {p.get("id", "?")} ({p.get("name", "?")}) — {status}')
    return "\n".join(lines)


def _format_registry_plugins(plugins: List[Dict[str, Any]]) -> str:
    """Render the plugin registry so the AI knows what's available to install."""
    if not plugins:
        return "(registry is empty or unavailable)"
    lines = []
    for p in plugins:
        installed = " [already installed]" if p.get("installed") else ""
        desc = p.get("description", "")
        desc_part = f" — {desc}" if desc else ""
        lines.append(f'  - {p.get("id", "?")} ({p.get("name", "?")!r}){desc_part}{installed}')
    return "\n".join(lines)


def _format_available_schedules(schedules: List[Dict[str, Any]]) -> str:
    """Render a compact list of schedule entries the AI can reference."""
    if not schedules:
        return "(no schedules yet)"
    lines = []
    for s in schedules:
        start = s.get("start_time", "?")
        end = s.get("end_time") or "open"
        pattern = s.get("day_pattern", "all")
        enabled = "enabled" if s.get("enabled", True) else "disabled"
        page_id = s.get("page_id", "?")
        sid = s.get("id", "?")
        lines.append(
            f"  - id: {sid} | page: {page_id} | {start}-{end} | {pattern} | {enabled}"
        )
    return "\n".join(lines)


def _format_available_carousels(carousels: List[Dict[str, Any]]) -> str:
    """Render a compact list of carousels the AI can reference."""
    if not carousels:
        return "(no carousels yet)"
    lines = []
    for c in carousels:
        name = c.get("name", "Untitled")
        cid = c.get("id", "?")
        pages = c.get("page_ids", [])
        interval = c.get("interval_seconds", 30)
        lines.append(
            f'  - "{name}" (id: {cid}) | {len(pages)} pages | {interval}s interval'
        )
    return "\n".join(lines)


def build_prompt(
    user_prompt: str,
    device_type: DeviceType,
    variables: Optional[Dict[str, Dict[str, Dict[str, Any]]]] = None,
    plugin_demos: Optional[List[Dict[str, Any]]] = None,
    current_page: Optional[Dict[str, Any]] = None,
    available_pages: Optional[List[Dict[str, Any]]] = None,
    installed_plugins: Optional[List[Dict[str, Any]]] = None,
    available_schedules: Optional[List[Dict[str, Any]]] = None,
    available_carousels: Optional[List[Dict[str, Any]]] = None,
    registry_plugins: Optional[List[Dict[str, Any]]] = None,
    mode: PromptMode = "generate",
) -> PromptContext:
    """Build the system + user messages for the LLM.

    Args:
        user_prompt: The user's natural-language request.
        device_type: ``"flagship"`` (22 cols x 6 rows) or ``"note"``
            (15 cols x 3 rows). Determines layout constraints in the
            prompt.
        variables: Variable registry as returned by
            ``PluginRegistry.get_all_variables_with_metadata()``. Keyed
            by plugin id. Optional; if missing, the model is told no
            dynamic variables are available.
        plugin_demos: Optional list of plugin-supplied demo pages
            (each shaped like ``DemoPageSchema``) to use as exemplars.
        current_page: Optional existing page (as a ``Page``-shaped
            dict) to send for refinement. The model is told the user is
            iterating on this page.
        mode: ``"generate"`` (default) for ``POST /pages/ai/generate``
            — instructs the model to emit a single JSON page object and,
            on off-topic input, a ``{"refusal": ...}`` object.
            ``"chat"`` for ``POST /pages/ai/chat`` — instructs the model
            to reply in prose and use the tool grammar appended by
            ``src.ai.chat`` for any structured actions. The two modes
            share every other section (variables, examples, layout
            rules) so the model sees consistent constraints.

    Returns:
        A ``PromptContext`` with the rendered system prompt and the
        captured inputs.
    """
    dims = get_dimensions(device_type)
    rows, cols = dims.rows, dims.cols
    vars_dict = variables or {}
    demos = plugin_demos or []

    exemplars = _select_exemplars(device_type, demos)

    char_rules = (
        "CHARACTER SET\n"
        "- Vestaboards display only A-Z, 0-9, and a small set of\n"
        "  punctuation: space, period, comma, apostrophe, dash,\n"
        "  exclamation, question mark, pound (#), dollar ($), percent,\n"
        "  parentheses, slash, colon, semicolon, ampersand, plus,\n"
        "  equals, at-sign.\n"
        "- The board uppercases all letters; do not rely on case.\n"
        "- Avoid emoji and non-ASCII characters.\n"
        "- Color tokens use DOUBLE braces (each consumes one tile):\n"
        "  {{red}}, {{orange}}, {{yellow}}, {{green}}, {{blue}},\n"
        "  {{violet}} (alias {{purple}}), {{white}}, {{black}}.\n"
        "  Numeric forms {{63}}-{{70}} also work.\n"
        "  Wrap a phrase to put colored tiles on either side, e.g.\n"
        "  `{{red}}HELLO{{red}}`. Single-brace `{red}` does NOT\n"
        "  colorize anything \u2014 it will render literally.\n"
        "- Symbol tokens use SINGLE braces (each consumes one tile):\n"
        "  {sun}, {star}, {cloud}, {rain}, {snow}, {storm}, {fog},\n"
        "  {partly}, {heart}, {check}, {x}.\n"
        "  `{heart}` renders as the literal characters `<3` on every\n"
        "  device. There is NO `{degree}` token \u2014 write temperatures\n"
        "  without one (e.g. `72F`) since the `\u00b0` character is not in\n"
        "  the Vestaboard character set.\n"
    )

    layout_rules = (
        f"DEVICE: {device_type} ({cols} columns x {rows} rows).\n"
        f"- Output exactly {rows} entries in `template` (use empty\n"
        f"  strings to leave a row blank).\n"
        f"- Each line's rendered width must be <= {cols} columns. If a\n"
        f"  line would exceed {cols} chars, either shorten it or set\n"
        f"  `wrap: true` for that line in `line_metadata` to let it\n"
        f"  flow across rows (this consumes additional rows; reduce\n"
        f"  the number of other rows accordingly).\n"
        f"- `line_metadata` must have the same length as `template`.\n"
        f"  Each entry is `{{alignment, wrap}}`:\n"
        f"    - `alignment`: \"left\" | \"center\" | \"right\" (no\n"
        f"      \"justify\"). Drives how the line is positioned within\n"
        f"      the {cols}-column row.\n"
        f"    - `wrap`: boolean. When true, content longer than {cols}\n"
        f"      columns flows onto subsequent rows; the wrapped lines\n"
        f"      consume the next blank rows in `template`.\n"
        f"  Prefer setting `alignment` over manually padding with spaces.\n"
        f"  Use `{{{{fill_space}}}}` for left/right edges on the SAME\n"
        f"  line (e.g. `Left{{{{fill_space}}}}Right`); use\n"
        f"  `{{{{filled:X}}}}` to fill with a repeated char or color\n"
        f"  (e.g. `Title{{{{filled:.}}}}99` or `{{{{filled:red}}}}`).\n"
        f"- Variable substitutions ({{{{plugin.field}}}}) expand at\n"
        f"  render time; their character widths are listed below so you\n"
        f"  can budget for them.\n"
    )

    template_syntax = (
        "TEMPLATE SYNTAX\n"
        "- Variable substitution: `{{plugin_id.field}}`, e.g.\n"
        "  `{{weather.temperature}}` or `{{date_time.time_12h}}`.\n"
        "- Array indexing (zero-based) for plugins that expose arrays:\n"
        "  `{{plugin_id.array.0.field}}`, e.g. `{{transit.stops.0.eta}}`.\n"
        "- Color suffix: `{{plugin_id.field_color}}` returns just the\n"
        "  color tile that the plugin's color rules selected for that\n"
        "  field (no value text). Use it as a status dot in front of a\n"
        "  value, e.g.\n"
        "  `{{weather.temperature_color}} {{weather.temperature}}F`.\n"
        "- Filters (chain with `|`):\n"
        "    `{{var|pad:N}}`      right-pad value to N chars (space-fill)\n"
        "    `{{var|truncate:N}}` cut value to N chars\n"
        "- Spacing helpers:\n"
        "    `{{fill_space}}` expands to fill the rest of the line; use\n"
        "      for left/right alignment: `Left{{fill_space}}Right`.\n"
        "    `{{filled:X}}` fills remaining space with X repeated:\n"
        "      - character: `{{filled:-}}` -> `Title-----99`\n"
        "      - color name: `{{filled:green}}` fills with green tiles\n"
        "      e.g. `Title{{filled:-}}99` or `{{filled:red}}`.\n"
        "      Do NOT write `{{filled.}}` or `{{filled:{color}}}` —\n"
        "      always use a colon: `{{filled:X}}`.\n"
        "      When X is a color name, write ONLY the bare name with no\n"
        "      extra characters: `{{filled:blue}}` not `{{filled:blue.}}`.\n"
    )

    expression_syntax = (
        "EXPRESSIONS / FORMULAS\n"
        "- Inline formula syntax: `{{= expression }}`. The expression is\n"
        "  evaluated at render time and replaced by its result. Example:\n"
        "    `{{= IF(weather.temperature > 80, \"HOT\", \"OK\") }}`\n"
        "- Inside a formula, reference variables by their plain dotted\n"
        "  path (no surrounding `{{ }}`): `weather.temperature`,\n"
        "  `date_time.hour`, etc. Only variables listed in AVAILABLE\n"
        "  VARIABLES below may be referenced.\n"
        "- Operators:\n"
        "    arithmetic: + - * / %\n"
        "    comparison: =  ==  !=  <>  <  >  <=  >=\n"
        "    logical:    AND  OR  NOT  (also && || !)\n"
        "    string:     &  (concatenation, e.g. \"H\" & \"I\" -> \"HI\")\n"
        "- String literals use double quotes: \"text\". `{` and `}` may\n"
        "  not appear inside an expression body.\n"
        "- Errors short-circuit (e.g. divide-by-zero -> `#DIV/0`,\n"
        "  missing variable -> `#REF`). Wrap risky lookups with\n"
        "  `IFERROR(expr, fallback)` or `DEFAULT(expr, fallback)` to\n"
        "  render a sane value instead.\n"
        "- Built-in functions (uppercase, no space before parens):\n"
        + _format_builtins()
        + "\n"
        "- Examples:\n"
        "    `{{= IF(weather.temperature > 80, \"HOT\", \"MILD\") }}`\n"
        "    `{{= ROUND(weather.temperature) & \"F\" }}`\n"
        "    `{{= IFERROR(weather.temperature, \"--\") }}`\n"
        "    `{{= UPPER(LEFT(weather.condition, 6)) }}`\n"
        "    `{{= COLOR(IF(weather.temperature > 80, \"red\", \"blue\")) }}`\n"
        "- Limitations: no user-defined functions, no loops, no\n"
        "  arbitrary code. Prefer plain `{{plugin.field}}` substitution\n"
        "  when no logic is required — only reach for `{{= ... }}` when\n"
        "  you actually need a condition or computation.\n"
    )

    if mode == "generate":
        output_rules = (
            "OUTPUT\n"
            "Return ONLY a single JSON object that matches this schema. Do\n"
            "not include markdown, comments, or extra prose:\n"
            + json.dumps(_OUTPUT_SCHEMA, indent=2)
            + "\n\nRules:\n"
            "- Only use variables that appear in the AVAILABLE VARIABLES\n"
            "  section above. Do not invent plugin or field names.\n"
            "- If the user requests something that requires a variable\n"
            "  that does not exist, prefer plain static text or omit that\n"
            "  detail.\n"
            f"- `device_type` must be \"{device_type}\".\n"
            "- `type` must be \"template\".\n"
        )
    else:
        # Chat mode appends its own tool-grammar addendum after this
        # prompt; we only need to teach the model about the shared
        # constraints (variables, character set, etc.) and a short
        # conversational stance. Detailed action shapes live in
        # ``src/ai/chat.py``'s ``_build_tool_grammar_addendum``.
        output_rules = (
            "CONVERSATIONAL STYLE\n"
            "- Reply in plain prose. Do NOT emit a top-level JSON object\n"
            "  as your entire response — the chat tool grammar (described\n"
            "  below) is the only structured output channel.\n"
            "- Keep replies short and direct. Aim for a sentence or two\n"
            "  unless the user asks for detail; do not restate the prompt\n"
            "  or summarize your own actions after every block.\n"
            "- Only use variables listed in AVAILABLE VARIABLES above.\n"
            "  Do not invent plugin or field names.\n"
            f"- Pages you propose must target device_type \"{device_type}\".\n"
        )

    exemplars_block = json.dumps(
        [
            {
                "name": ex.get("name", "Example"),
                "device_type": ex.get("device_type"),
                "template": ex.get("template", []),
                "line_metadata": ex.get("line_metadata", []),
                "duration_seconds": ex.get("duration_seconds", 300),
            }
            for ex in exemplars
        ],
        indent=2,
    )

    pages_section = ""
    if available_pages is not None:
        pages_section = (
            "\n\nAVAILABLE PAGES (pages the user can navigate to):\n"
            + _format_available_pages(available_pages)
        )

    plugins_section = ""
    if installed_plugins is not None:
        plugins_section = (
            "\n\nINSTALLED PLUGINS:\n"
            + _format_installed_plugins(installed_plugins)
        )

    schedules_section = ""
    if available_schedules is not None:
        schedules_section = (
            "\n\nAVAILABLE SCHEDULES (existing schedule entries; use IDs to update/delete):\n"
            + _format_available_schedules(available_schedules)
        )

    carousels_section = ""
    if available_carousels is not None:
        carousels_section = (
            "\n\nAVAILABLE CAROUSELS (existing carousels; use IDs to update):\n"
            + _format_available_carousels(available_carousels)
        )

    registry_section = ""
    if registry_plugins is not None:
        registry_section = (
            "\n\nPLUGIN REGISTRY (plugins available to install; use the `id` "
            "field as plugin_id when proposing install_plugin):\n"
            + _format_registry_plugins(registry_plugins)
        )

    scope_intro = (
        "SCOPE — WHAT YOU CAN HELP WITH\n"
        "You are a FiestaBoard specialist. Only assist with tasks that\n"
        "produce board output or FiestaBoard configuration:\n"
        "  - Creating, editing, or refining board pages and templates\n"
        "  - Explaining template variables, expressions, or plugin features\n"
        "  - Suggesting which plugins to install for a desired display\n"
        "  - Managing schedules, carousels, and FiestaBoard settings\n"
        "  - Answering questions about FiestaBoard features and capabilities\n"
        "Do NOT help with unrelated topics (recipes, general coding help,\n"
        "essays, trivia, customer support for other products, etc.).\n"
    )
    if mode == "generate":
        scope_rules = (
            scope_intro
            + "If the user's request is off-topic, output ONLY this JSON\n"
            "object (no page, no prose):\n"
            '  {"refusal": true, "reason": "<one sentence why + what you can help with>"}\n'
        )
    else:
        scope_rules = (
            scope_intro
            + "If the user's request is off-topic, reply with a brief,\n"
            "friendly message explaining that you only help with\n"
            "FiestaBoard, and ask what they would like to show on their\n"
            "board. Do not emit any tool block in that case.\n"
        )

    system_prompt = (
        "You are FiestaBoard's page-generation assistant. You design\n"
        "short, glanceable pages for a Vestaboard split-flap display\n"
        "based on the user's natural-language request.\n\n"
        + scope_rules
        + "\n"
        + layout_rules
        + "\n"
        + char_rules
        + "\n"
        + template_syntax
        + "\n"
        + expression_syntax
        + "\n"
        "AVAILABLE VARIABLES (only these may be used — these are the\n"
        "variables exposed by the plugins enabled on THIS instance; do\n"
        "not invent or reference any plugin or field that is not listed):\n"
        + _format_variables(vars_dict)
        + "\n\nEXAMPLES:\n"
        + exemplars_block
        + "\n\n"
        + output_rules
        + pages_section
        + plugins_section
        + schedules_section
        + carousels_section
        + registry_section
    )

    return PromptContext(
        device_type=device_type,
        rows=rows,
        cols=cols,
        user_prompt=user_prompt,
        variables=vars_dict,
        exemplars=exemplars,
        current_page=current_page,
        system_prompt=system_prompt,
    )
