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
- filters from :data:`src.templates.filters.TEMPLATE_FILTERS`, which
  ``tests/test_ops_teaching.py`` verifies against the engine's actual
  ``_apply_filter``/``|wrap`` implementation so this table cannot rot
- formula functions from :func:`src.templates.expressions.function_signatures`
"""

from __future__ import annotations

from dataclasses import dataclass

from src.devices import DEVICE_DIMENSIONS, get_dimensions
from src.templates.filters import FILTER_NAMES as _FILTER_NAMES
from src.templates.filters import TEMPLATE_FILTERS as _TEMPLATE_FILTERS


@dataclass(frozen=True)
class LanguageConstruct:
    """One thing a template author can write, and how to teach it.

    Functions were always generated from the live registry, so a new one
    reached every AI surface for free. Syntax was hand-written prose in two
    places, which is how one copy came to advertise filters that did not exist
    (#1764). Registering constructs here makes syntax behave like functions:
    ``tests/test_teaching_surface_parity.py`` fails when a construct is missing
    from any surface.
    """

    name: str
    example: str
    summary: str


#: Every construct the template language offers, in teaching order.
LANGUAGE_CONSTRUCTS: tuple[LanguageConstruct, ...] = (
    LanguageConstruct("variable", "{{weather.temperature}}", "substitute a plugin variable"),
    LanguageConstruct("array index", "{{transit.stops.0.eta}}", "one item of an array, zero-based"),
    LanguageConstruct("color suffix", "{{weather.temperature_color}}", "just the color tile for a value"),
    LanguageConstruct("filter", "{{weather.condition|upper|truncate:6}}", "transform a value, chainable"),
    LanguageConstruct("fill space", "Left{{fill_space}}Right", "push content to both edges of a line"),
    LanguageConstruct("filled", "Title{{filled:-}}99", "fill the gap with a character or color"),
    LanguageConstruct("formula", '{{= IF(weather.temperature > 80, "HOT", "OK") }}', "Excel-like logic"),
    LanguageConstruct("count", "{{= COUNT(mlb.games) }}", "how many items an array holds"),
    LanguageConstruct("safe item", '{{= AT(mlb.games, 2, "team1") }}', "an item field, blank when absent"),
    LanguageConstruct(
        "iteration",
        '{{= FOREACH(mlb.games, item.team1 & " " & item.score1, 4) }}',
        "one board row per item; fills the rows below",
    ),
    LanguageConstruct(
        "array pipeline", 'SORT(FILTER(mlb.games, item.final), "score1")', "filter/sort before iterating"
    ),
    LanguageConstruct("date maths", "{{= DATEDIFF(TODAY(), DATE(launch.day)) }}", "whole days between two dates"),
    LanguageConstruct("date format", '{{= FORMATDATE(NOW(), "ddd hh:mm AP") }}', "render a date your way"),
    LanguageConstruct("reuse", 'LET(t, weather.temperature, t & "F/" & t)', "name a value once and reuse it"),
)

#: Re-exported from :mod:`src.templates.filters`, which owns the roster because
#: the engine implements and validates it — teaching derives from the engine,
#: never the other way round, which is also why the imports below are lazy.
#: Re-exporting keeps ``teaching.TEMPLATE_FILTERS`` working for its consumers.
TEMPLATE_FILTERS = _TEMPLATE_FILTERS
FILTER_NAMES = _FILTER_NAMES


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
    """The numeric flap-code range the engine actually accepts.

    Derived from the engine rather than recomputed here: teaching a narrower
    range than the engine honors makes models avoid a valid flap, which is
    what #1885 recorded when this returned 63-70 for an engine that took 71.
    """
    from src.templates.colors import NUMERIC_COLOR_RANGE

    return NUMERIC_COLOR_RANGE


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
        "  • Constructs: every form the language accepts —",
        *construct_lines(indent=" " * 16),
        "                FOREACH returns one row per item and fills the rows",
        "                BELOW it, exactly as |wrap overflow does — leave them",
        "                empty, and cap it with a limit so it cannot outgrow",
        "                the board.",
        "                Inside FOREACH/FILTER, `item` is the current item and",
        "                `index` its 1-based position; `item.field` reads a",
        "                field. An array cannot be printed directly.",
    ]
    return "\n".join(lines)


def construct_lines(indent: str = "") -> list[str]:
    """One teaching line per :data:`LANGUAGE_CONSTRUCTS` entry.

    Shared verbatim by the MCP instructions and the chat system prompt so the
    two cannot describe different languages.
    """
    width = max(len(construct.name) for construct in LANGUAGE_CONSTRUCTS) + 1
    return [
        f"{indent}{construct.name + ':':<{width}} {construct.example}   — {construct.summary}"
        for construct in LANGUAGE_CONSTRUCTS
    ]


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
