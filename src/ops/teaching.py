"""Teaching text for AI surfaces, generated once from real platform metadata.

Issue #1764: the chat system prompt (:mod:`src.ai.prompt_builder`) and the
MCP server instructions (:mod:`src.mcp_server`) each taught the model about
board dimensions and template syntax in their own hardcoded copy, and the
MCP copy had drifted from the engine — it advertised ``|upper`` and
``|lower`` filters that have never existed, omitted the real
``|truncate``/``|zeropad`` ones, gave the numeric color range as 63-71
where the named palette ends at 70, and froze a 15-function formula list
while the engine's registry kept growing.

Everything here is derived from the modules that define the behavior:

- dimensions from :data:`src.devices.DEVICE_DIMENSIONS`
- color tokens from :data:`src.templates.engine.COLOR_CODES`
- filters from :data:`TEMPLATE_FILTERS` below, which
  ``tests/test_ops_teaching.py`` verifies against the engine's actual
  ``_apply_filter``/``|wrap`` implementation so this table cannot rot
- formula functions from :func:`src.templates.expressions.function_signatures`
"""

from __future__ import annotations

from src.devices import DEVICE_DIMENSIONS, get_dimensions

#: The template filter chain the engine actually implements.
#: (spelling as written in a template, one-line teaching summary)
#: Kept in lock-step with ``TemplateEngine._apply_filter`` and the special
#: ``|wrap`` handling by tests/test_ops_teaching.py.
TEMPLATE_FILTERS: tuple[tuple[str, str], ...] = (
    ("pad:N", "right-pad the value with spaces to N chars"),
    ("truncate:N", "cut the value to N chars"),
    ("zeropad:N", "left-pad the value with zeros to N chars"),
    ("wrap", "let a long value flow into the empty lines below"),
)


def dimensions_phrase(device_type: str) -> str:
    """``"22 columns x 6 rows"`` — the chat system prompt's device line."""
    dims = get_dimensions(device_type)
    return f"{dims.cols} columns x {dims.rows} rows"


def _color_names_by_code() -> dict[int, list[str]]:
    """Group the named color tokens by flap code, aliases together."""
    from src.templates.engine import COLOR_CODES

    by_code: dict[int, list[str]] = {}
    for name, code in COLOR_CODES.items():
        by_code.setdefault(code, []).append(name)
    return by_code


def color_tokens_phrase() -> str:
    """``{{red}} {{orange}} ... {{black}}`` with aliases annotated."""
    parts: list[str] = []
    for _code, names in sorted(_color_names_by_code().items()):
        token = "{{" + names[0] + "}}"
        if len(names) > 1:
            aliases = " ".join("{{" + n + "}}" for n in names[1:])
            token += f" (alias {aliases})"
        parts.append(token)
    return " ".join(parts)


def numeric_color_range() -> tuple[int, int]:
    """The numeric flap-code range covered by the named palette."""
    from src.templates.engine import COLOR_CODES

    codes = COLOR_CODES.values()
    return min(codes), max(codes)


def filters_phrase() -> str:
    """``{{var|pad:N}} {{var|truncate:N}} ...`` from :data:`TEMPLATE_FILTERS`."""
    return " ".join("{{var|" + spelling + "}}" for spelling, _summary in TEMPLATE_FILTERS)


def formula_function_names() -> list[str]:
    """Every built-in formula function name, from the live registry."""
    from src.templates.expressions import function_signatures

    return sorted(function_signatures())


def device_dimensions_block() -> str:
    """The DEVICE DIMENSIONS section of the MCP server instructions."""
    width = max(len(device) for device in DEVICE_DIMENSIONS) + 1
    lines = ["DEVICE DIMENSIONS (template_lines length must match exactly)"]
    for device, dims in DEVICE_DIMENSIONS.items():
        lines.append(f"  • {device + ':':<{width}} {dims.cols} columns × {dims.rows} rows")
    lines += [
        "  Content longer than the board width is TRUNCATED at render time —",
        "  prefer concise variable names, the |wrap filter, or {{= LEFT(...)}}",
        "  over letting the engine silently cut text off.",
    ]
    return "\n".join(lines)


def template_syntax_block() -> str:
    """The TEMPLATE SYNTAX section of the MCP server instructions."""
    low, high = numeric_color_range()
    low_name = _color_names_by_code()[low][0]
    filter_lines = [f"                |{spelling:<11} {summary}" for spelling, summary in TEMPLATE_FILTERS]
    function_roster = ", ".join(formula_function_names())
    lines = [
        "TEMPLATE SYNTAX",
        "  • Variables:  {{plugin_id.variable_name}}  e.g. {{weather.temperature}}",
        f"  • Colors:     {color_tokens_phrase()}",
        f"                Numeric equivalents {low}–{high} also work ({{{{{low}}}}} = {low_name}).",
        "                Each color token renders as ONE solid tile (not a",
        "                style for following text). Place the token where you",
        "                want the dot/indicator to appear.",
        f"  • Filters:    {filters_phrase()}",
        *filter_lines,
        "                |wrap needs blank lines beneath the wrapped line for",
        "                its overflow.",
        "  • Formulas:   {{= EXPRESSION }} for Excel-like logic.",
        "                Functions include:",
        *_wrap_roster(function_roster, indent=" " * 16, width=76),
        '                Example: {{= IF(weather.temp_f > 80, "HOT", "OK")}}',
    ]
    return "\n".join(lines)


def _wrap_roster(roster: str, indent: str, width: int) -> list[str]:
    """Wrap a comma-separated roster into indented lines."""
    import textwrap

    return textwrap.wrap(roster, width=width, initial_indent=indent, subsequent_indent=indent)


def dimensions_summary_sentence() -> str:
    """One sentence for MCP prompt bodies, e.g. the create_display_page prompt."""
    parts = [
        f"{device.capitalize()} display is {dims.cols}×{dims.rows} characters"
        for device, dims in DEVICE_DIMENSIONS.items()
    ]
    return "; ".join(parts) + "."
