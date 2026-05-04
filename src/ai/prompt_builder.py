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
from typing import Any, Dict, List, Optional

from ..devices import DeviceType, get_dimensions


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
            "{{weather.temperature}}{degree}F  {{weather.condition}}",
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
            "{red}HELLO{red}",
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


def build_prompt(
    user_prompt: str,
    device_type: DeviceType,
    variables: Optional[Dict[str, Dict[str, Dict[str, Any]]]] = None,
    plugin_demos: Optional[List[Dict[str, Any]]] = None,
    current_page: Optional[Dict[str, Any]] = None,
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
        "- The degree token `{degree}` (or the literal `\u00b0` character)\n"
        "  renders as a degree sign on the Flagship and as a heart on\n"
        "  the Note. Use it for both temperatures and hearts.\n"
        "- Color tokens (insert as colored tiles): {red}, {orange},\n"
        "  {yellow}, {green}, {blue}, {violet}, {white}, {black}.\n"
        "  Wrap a phrase like `{red}HELLO{red}` to put colored tiles on\n"
        "  either side. Each color token consumes one column.\n"
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
        f"- Variable substitutions ({{{{plugin.field}}}}) expand at\n"
        f"  render time; their character widths are listed below so you\n"
        f"  can budget for them.\n"
    )

    template_syntax = (
        "TEMPLATE SYNTAX\n"
        "- Variables: `{{plugin_id.field}}`, e.g.\n"
        "  `{{weather.temperature}}` or `{{date_time.time_12h}}`.\n"
        "- Filters: `{{var|pad:N}}` right-pads to N chars,\n"
        "  `{{var|truncate:N}}` cuts to N chars, `{{var|wrap}}` flows\n"
        "  long values across rows.\n"
        "- Spacing: `{{fill_space}}` expands to fill the line; use it\n"
        "  for left/right alignment within a single line, e.g.\n"
        "  `Left{{fill_space}}Right`.\n"
        "- Color and symbol tokens: `{red}`, `{green}`, `{sun}`,\n"
        "  `{heart}`, etc. Each token = one tile.\n"
    )

    output_rules = (
        "OUTPUT\n"
        "Return ONLY a single JSON object that matches this schema. Do\n"
        "not include markdown, comments, or extra prose:\n"
        + json.dumps(_OUTPUT_SCHEMA, indent=2)
        + "\n\nRules:\n"
        "- Only use variables that appear in the AVAILABLE VARIABLES\n"
        "  section below. Do not invent plugin or field names.\n"
        "- If the user requests something that requires a variable\n"
        "  that does not exist, prefer plain static text or omit that\n"
        "  detail.\n"
        f"- `device_type` must be \"{device_type}\".\n"
        "- `type` must be \"template\".\n"
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

    system_prompt = (
        "You are FiestaBoard's page-generation assistant. You design\n"
        "short, glanceable pages for a Vestaboard split-flap display\n"
        "based on the user's natural-language request.\n\n"
        + layout_rules
        + "\n"
        + char_rules
        + "\n"
        + template_syntax
        + "\n"
        "AVAILABLE VARIABLES (only these may be used):\n"
        + _format_variables(vars_dict)
        + "\n\nEXAMPLES:\n"
        + exemplars_block
        + "\n\n"
        + output_rules
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
