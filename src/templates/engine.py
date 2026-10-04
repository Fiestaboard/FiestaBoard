"""Template engine for dynamic content generation.

Template syntax:
- Data binding: {{plugin_id.field}} e.g., {{weather.temperature}}, {{date_time.time}}
- Inline formulas: {{= EXPRESSION }} - Excel-like expressions with IF/AND/OR,
  math, string functions, and COLOR(). See ``src/templates/expressions.py`` and
  the user-facing reference docs at ``docs/reference/template-formulas.md``.
- Colors: {{red}}, {{blue}}, etc. - Single colored tile (not text wrapping)
- Symbols: {sun}, {cloud}, {rain}
- Formatting: {{value|pad:3}}, {{value|zeropad:2}}, {{value|truncate:3}},
  {{value|upper}}, {{value|lower}}, {{value|wrap}} — chainable left to right
  ({{value|upper|truncate:3}}). The roster lives in
  ``src.templates.filters.TEMPLATE_FILTERS``; ``validate_template`` reports
  anything else.

Color tiles (each produces one solid color tile):
- {{red}} or {{63}} - Red tile
- {{orange}} or {{64}} - Orange tile
- {{yellow}} or {{65}} - Yellow tile
- {{green}} or {{66}} - Green tile
- {{blue}} or {{67}} - Blue tile
- {{violet}} or {{68}} - Violet tile
- {{white}} or {{69}} - White tile
- {{black}} or {{70}} - Black tile

Example: "{{red}} ALERT {{red}}" produces [red tile] ALERT [red tile]

Special filters:
- |wrap - Wraps long content across multiple lines, filling empty lines below

Uses the plugin system exclusively to resolve available variables.
Plugin IDs are used as template namespaces (e.g., {{weather.temp}}, {{stocks.symbol}}).
"""

import logging
import re
from dataclasses import dataclass
from typing import Any

from src.devices import DEFAULT_DEVICE_TYPE, BoardContext, resolve_dimensions
from src.markup import count_tiles as markup_count_tiles
from src.markup import neutralize_data, resolve_icon_name, take_tiles, wrap_line
from src.plugins import get_plugin_registry
from src.plugins.manifest import resolve_color_rules
from src.text_utils import extract_alignment_from_line

from .colors import COLOR_CODES
from .colors import is_color_code as _is_color_code
from .expressions import ensure_render_clock, find_formulas, render_expressions, validate_expression
from .filters import FILTER_NAMES

logger = logging.getLogger(__name__)

# Symbol shortcut -> legacy ASCII stand-in. This is what `{sun}` renders as
# with extended markup off (today, on every board). With extended markup on,
# a shortcut is an alias of the icon registry instead (plan D16): `{sun}` is
# `{icon:sun}`, resolved by `src.markup.resolve_icon_name` from FiestaUI's
# registry data, so this table carries no icon meanings. `{heart}` is the
# typed ♥ (code 62), not an icon. A shortcut the registry does not know keeps
# its ASCII in both modes.
SYMBOL_CHARS = {
    "sun": "*",
    "star": "*",
    "cloud": "O",
    "rain": "/",
    "snow": "*",
    "storm": "!",
    "fog": "-",
    "partly": "%",
    "heart": "<3",
    "check": "+",
    "x": "X",
}

# Regex patterns
# Note: ``[^}{]+`` (rather than ``[^}]+``) prevents overlapping matches and
# eliminates polynomial backtracking on inputs like ``{{{{{{...``.  Variable
# expressions never contain ``{`` themselves.
VAR_PATTERN = re.compile(r"\{\{([^}{]+)\}\}")  # {{source.field}} or {{source.field|filter}}
COLOR_PATTERN = re.compile(
    r"\{\{(red|orange|yellow|green|blue|violet|purple|white|black|filled|6[3-9]|7[01])\}\}", re.IGNORECASE
)
SYMBOL_PATTERN = re.compile(r"\{(sun|star|cloud|rain|snow|storm|fog|partly|heart|check|x)\}", re.IGNORECASE)
FILL_SPACE_PATTERN = re.compile(r"\{\{fill_space\}\}", re.IGNORECASE)
FILL_SPACE_REPEAT_PATTERN = re.compile(r"\{\{fill_space_repeat:(.+?)\}\}", re.IGNORECASE)
FILLED_PATTERN = re.compile(r"\{\{filled:(.+?)\}\}", re.IGNORECASE)

# Extended-markup authoring forms (plan D19): `{{<head>:<body>}}` where the
# head is CLOSED: a colour (name, 63-70 or #rrggbb, never filled/71), a
# block `fg/bg`, or the literal `icon`. Anything else is a variable.
_SPAN_COLOUR = r"(?:red|orange|yellow|green|blue|violet|purple|white|black|6[3-9]|70|#[0-9a-fA-F]{6})"
EXTENDED_HEAD_PATTERN = re.compile(r"\{\{(icon|" + _SPAN_COLOUR + r"(?:/" + _SPAN_COLOUR + r")?):", re.IGNORECASE)


def _matching_double_brace(text: str, start: int) -> int:
    """Index of the `}` closing the `{{` at *start*, counting nested braces; -1 if none.

    The closing pair must be `}}`, so the form ends where both opening braces
    are balanced (a body may hold `{{var}}`, `{{= f }}`, `{63}`, nested forms).
    """
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i if text[i - 1] == "}" and i - 1 > start + 1 else -1
    return -1


def extract_template_plugin_ids(template_lines: "list[str] | str | None") -> set[str] | None:
    """Statically extract the plugin ids a template's variables reference.

    A plain ``{{source.field...}}`` variable resolves against the template
    context by its root: ``source`` is the plugin id (or instance key like
    ``weather:sf``), exactly as ``_get_variable_value`` looks it up. That
    makes the fetch set of a template statically computable, so a render
    can fetch only the plugins it will actually read (issue #1751).

    Returns ``None`` when the set CANNOT be determined statically — today
    that is any ``{{= ... }}`` formula expression, whose variable references
    live inside an expression grammar this scan does not parse. ``None``
    tells the caller to fall back to fetching every enabled plugin, which
    is always safe (it is the pre-#1751 behavior).

    Expressions that never read plugin data are skipped: color markers
    (``{{red}}``), ``fill_space`` / ``filled:`` / ``fill_space_repeat:``
    specials, and dotless or empty roots (all of which render without a
    context lookup). Roots that don't name an enabled plugin are harmless
    to include — the registry intersects with the enabled set.
    """
    if template_lines is None:
        return set()
    lines = [template_lines] if isinstance(template_lines, str) else list(template_lines)

    refs: set[str] = set()
    for line in lines:
        if not line:
            continue
        for match in VAR_PATTERN.finditer(line):
            expr = match.group(1).strip()
            if expr.startswith("="):
                return None  # formula: variable owners are not statically known
            var_part = expr.split("|", 1)[0].strip().lower()
            if var_part == "fill_space" or var_part.startswith(("filled:", "fill_space_repeat:")):
                continue
            root, sep, rest = var_part.partition(".")
            if not sep or not root or not rest:
                continue  # colors, invalid or dotless expressions: no context lookup
            refs.add(root)
    return refs


@dataclass
class TemplateError:
    """Template validation error."""

    line: int
    column: int
    message: str


class TemplateEngine:
    """Template engine for rendering dynamic content.

    Supports:
    - Variable substitution from plugin data sources
    - Board color codes (inline and block)
    - Symbol shortcuts
    - Text formatting filters
    - Dynamic colors based on plugin configuration rules

    Uses plugin system exclusively for all variable resolution.
    Plugin IDs serve as template namespaces (e.g., {{weather.temp}}, {{stocks.symbol}}).
    """

    def __init__(self):
        """Initialize template engine."""
        self._display_service = None
        self._config_manager = None
        self._plugin_registry = None

        try:
            self._plugin_registry = get_plugin_registry()
            logger.info("TemplateEngine initialized with plugin system")
        except Exception as e:
            logger.error(f"Failed to initialize plugin registry: {e}")
            raise RuntimeError("Plugin system is required but failed to initialize") from e

    def reset_cache(self):
        """Reset cached services to pick up configuration changes."""
        self._display_service = None
        self._config_manager = None
        self._plugin_registry = get_plugin_registry()
        logger.info("TemplateEngine cache reset")

    @property
    def display_service(self):
        """Lazy-load display service to avoid circular imports."""
        if self._display_service is None:
            from src.displays.service import get_display_service

            self._display_service = get_display_service()
        return self._display_service

    @property
    def config_manager(self):
        """Lazy-load config manager to avoid circular imports."""
        if self._config_manager is None:
            from src.config_manager import get_config_manager

            self._config_manager = get_config_manager()
        return self._config_manager

    def render(self, template: str, context: dict[str, Any] | None = None, *, extended_markup: bool = False) -> str:
        """Render template with data context.

        Args:
            template: Template string with {{variables}} and {{colors}}
            context: Optional pre-fetched context data. If not provided,
                     data will be fetched from display sources.
            extended_markup: Resolve symbol shortcuts (``{sun}``) through the
                icon registry instead of their ASCII stand-ins (plan D16). Off
                by default; nothing turns it on until the v10 markup switch.

        Returns:
            Rendered string with all substitutions applied
        """
        if context is None:
            # Demand-driven, exactly as PageService.render_page already is
            # (#1751): fetch only the plugins this template's variables name.
            # ``extract_template_plugin_ids`` returns None for a formula page,
            # which keeps the safe fetch-everything fallback.
            context = self._build_context(plugin_ids=extract_template_plugin_ids(template))

        # Pin one instant for this render so NOW()/TODAY() in different
        # formulas cannot straddle a minute or midnight boundary. A no-op
        # when render_lines (or any outer caller) already pinned it.
        context = ensure_render_clock(context)

        result = template

        # Extended-markup authoring forms ({{red:HOT}}, {{icon:sun}}) before
        # anything else: VAR_PATTERN would read "red:HOT" as a variable name.
        if extended_markup:
            result = self._normalize_extended(result, context)

        # Process colors FIRST (before variables) to prevent VAR_PATTERN from matching them
        # This converts {{red}} to {{63}}, etc.
        result = self._normalize_colors(result)

        # Process inline formula expressions ({{= ... }}) before plain variables.
        # See ``src/templates/expressions.py`` for the language reference.
        # Formulas resolve their own variable references against ``context``;
        # the result is plain text (possibly containing color tile markers
        # like ``{67}`` from ``COLOR()``) which then flows through the
        # remaining passes unchanged.
        result = render_expressions(result, context)

        # Process variables
        result = self._render_variables(result, context)

        # Process symbols (single brackets like {sun})
        return self._render_symbols(result, extended_markup=extended_markup)

    def _count_tiles(self, text: str, *, extended_markup: bool = False) -> int:
        """Count the number of tiles in a text string.

        Color markers like {66} count as 1 tile each, not their character length.

        Args:
            text: Rendered text string (may contain color markers like {66})
            extended_markup: Measure what an extended-markup board draws
                (plan D19): a span or block counts its cells, an icon one
                tile (:func:`src.markup.count_tiles`).

        Returns:
            Number of tiles (characters + color markers, where each marker = 1 tile)
        """
        if extended_markup:
            return markup_count_tiles(text)
        tile_count = 0
        i = 0

        while i < len(text):
            # Check for color marker
            if text[i] == "{":
                closing_brace = text.find("}", i)
                if closing_brace != -1:
                    content = text[i + 1 : closing_brace]
                    # Check if it's a color code (numeric 63-71 or named)
                    if content.isdigit():
                        code = int(content)
                        if _is_color_code(code):
                            # Numeric color code like {66}, {70}, or {71}
                            tile_count += 1
                            i = closing_brace + 1
                            continue
                    elif content.lower() in COLOR_CODES:
                        # Named color like {green}
                        tile_count += 1
                        i = closing_brace + 1
                        continue
                    elif content.startswith("/"):
                        # End tag - skip it (doesn't count as a tile)
                        i = closing_brace + 1
                        continue

            # Regular character
            tile_count += 1
            i += 1

        return tile_count

    def _truncate_to_tiles(self, text: str, max_tiles: int = 22, *, extended_markup: bool = False) -> str:
        """Truncate text to max_tiles, where color markers count as 1 tile each.

        Args:
            text: Rendered text string (may contain color markers like {66})
            max_tiles: Maximum number of tiles (characters + color markers)
            extended_markup: Cut by drawn tiles, never inside a span, block
                or icon; a span cut short is closed
                (:func:`src.markup.take_tiles`).

        Returns:
            Truncated string that fits within max_tiles
        """
        if extended_markup:
            return take_tiles(text, max_tiles)[0]
        # Count tiles (characters + color markers) and truncate appropriately
        result = []
        tile_count = 0
        i = 0

        while i < len(text) and tile_count < max_tiles:
            # Check for color marker
            if text[i] == "{":
                closing_brace = text.find("}", i)
                if closing_brace != -1:
                    content = text[i + 1 : closing_brace]
                    # Check if it's a color code (numeric 63-71 or named)
                    if content.isdigit():
                        code = int(content)
                        if _is_color_code(code):
                            # Numeric color code like {66}, {70}, or {71}
                            result.append(text[i : closing_brace + 1])
                            tile_count += 1
                            i = closing_brace + 1
                            continue
                    elif content.lower() in COLOR_CODES:
                        # Named color like {green}
                        result.append(text[i : closing_brace + 1])
                        tile_count += 1
                        i = closing_brace + 1
                        continue
                    elif content.startswith("/"):
                        # End tag - skip it
                        i = closing_brace + 1
                        continue

            # Regular character
            result.append(text[i])
            tile_count += 1
            i += 1

        return "".join(result)

    def render_lines(
        self,
        template_lines: list[str],
        context: dict[str, Any] | None = None,
        line_metadata: list[dict] | None = None,
        device_type: str | None = None,
        notes_wide: int = 1,
        notes_tall: int = 1,
        grid_rows: int | None = None,
        grid_cols: int | None = None,
        *,
        extended_markup: bool = False,
    ) -> str:
        """Render a list of template lines (for template pages).

        Handles:
        - The special |wrap filter which allows content to flow across multiple lines
        - Alignment via line_metadata (preferred) or legacy inline prefixes
        - The {{fill_space}} variable for flexible spacing

        Args:
            template_lines: List of template lines, padded or truncated to
                match the device's row count (6 for flagship, 3 for note,
                notes_tall×3 for note_array, grid_rows for panel).
                Pure content when line_metadata is provided; may contain
                legacy prefixes otherwise.
            context: Optional pre-fetched context
            line_metadata: Optional per-line metadata dicts with 'alignment' and
                'wrap' keys.  When provided, template_lines are treated as pure
                content (no prefix parsing).
            device_type: Device type ('flagship', 'note', 'note_array' or
                'panel') to determine board dimensions. Defaults to flagship
                (22 cols, 6 rows).
            notes_wide: For 'note_array' device type, the number of notes side by
                side (determines cols = notes_wide × 15). Ignored for other types.
            notes_tall: For 'note_array' device type, the number of notes stacked
                vertically (determines rows = notes_tall × 3). Ignored for other types.
            grid_rows / grid_cols: For 'panel', the explicit grid. Ignored for
                other types.
            extended_markup: The target board speaks extended markup (its
                character set is rich; plan D19). Every line renders with it,
                as :meth:`render` documents.

        Returns:
            Rendered string with newlines
        """
        # Resolve to a known device type, falling back to the default so a bad
        # value never crashes a render. This is the single place a BoardContext
        # is constructed for callers that only know the device_type string.
        # Resolve dims (note-array aware); fall back to the default device for an
        # unknown type so a bad value never crashes a render.
        render_device_type = device_type or DEFAULT_DEVICE_TYPE
        try:
            dims = resolve_dimensions(render_device_type, notes_wide, notes_tall, grid_rows, grid_cols)
        except ValueError:
            render_device_type = DEFAULT_DEVICE_TYPE
            dims = resolve_dimensions(render_device_type, notes_wide, notes_tall)

        # Build the BoardContext from the resolved dims so plugins receive the true
        # board size — including note arrays (no fixed DEVICE_DIMENSIONS entry).
        if context is None:
            context = self._build_context(
                BoardContext(render_device_type, rows=dims.rows, cols=dims.cols),
                plugin_ids=extract_template_plugin_ids(template_lines),
            )
        # Pin the clock once for the whole board: every line's render()
        # inherits this instant instead of re-reading the clock, so row 1 and
        # row 6 can never disagree about what time it is.
        context = ensure_render_clock(context)

        num_rows = dims.rows
        board_width = dims.cols
        # With extended_markup, every width below (alignment, padding,
        # truncation, fill_space, wrap) is measured in the tiles the board
        # draws: a span or block by its cells, an icon as one tile. Off, each
        # helper takes its unchanged split-flap path.

        # Pad to num_rows lines
        lines = list(template_lines[:num_rows])
        while len(lines) < num_rows:
            lines.append("")

        # Build per-line alignment/wrap arrays from metadata or legacy parsing
        alignments: list[str] = []
        wraps: list[bool] = []
        contents: list[str] = []

        for i, line in enumerate(lines):
            if line_metadata and i < len(line_metadata):
                meta = line_metadata[i]
                alignments.append(
                    meta.get("alignment", "left") if isinstance(meta, dict) else getattr(meta, "alignment", "left")
                )
                wraps.append(meta.get("wrap", False) if isinstance(meta, dict) else getattr(meta, "wrap", False))
                contents.append(line)
            else:
                alignment, wrap_enabled, content = self._extract_alignment(line)
                alignments.append(alignment)
                wraps.append(wrap_enabled)
                contents.append(content)

        # Process lines, handling |wrap specially
        rendered = [""] * num_rows
        skip_until = -1  # Track lines filled by wrap overflow
        # Cache rendered content per line so the wrap-budget probe and the
        # main non-wrap branch don't render the same line twice.
        rendered_cache: dict[int, str] = {}

        def _render_cached(idx: int) -> str:
            if idx not in rendered_cache:
                rendered_cache[idx] = self.render(contents[idx], context, extended_markup=extended_markup)
            return rendered_cache[idx]

        for i in range(num_rows):
            if i <= skip_until:
                continue

            alignment = alignments[i]
            wrap_enabled = wraps[i]
            content = contents[i]

            has_wrap = wrap_enabled or "|wrap}}" in content or "|wrap|" in content

            def _overflow_budget(start: int) -> int:
                """Rows an overflowing line at ``start`` may fill, itself included.

                A row is available if it is literally empty, opts into the
                region with wrap=True, or renders to whitespace (e.g.
                ``{{plugin.var}}`` where var resolves to ""). A wrap=False row
                that renders visible content hard-stops the overflow — that is
                what protects a footer the author put below.

                Both overflow paths share this: ``|wrap`` and a row-emitting
                formula spill the same way, so they must stop the same way.
                """
                available = 1  # the overflowing line itself
                for j in range(start + 1, num_rows):
                    if contents[j].strip() == "":
                        available += 1
                        continue
                    if wraps[j] or "|wrap}}" in contents[j] or "|wrap|" in contents[j]:
                        available += 1
                        continue
                    if _render_cached(j).strip() == "":
                        available += 1
                        continue
                    break
                return available

            if has_wrap:
                wrapped_lines = self._render_with_wrap(
                    content,
                    context,
                    max_lines=_overflow_budget(i),
                    board_width=board_width,
                    extended_markup=extended_markup,
                )

                for k, wrapped_line in enumerate(wrapped_lines):
                    if i + k < num_rows:
                        processed = self._process_fill_space(
                            wrapped_line, width=board_width, extended_markup=extended_markup
                        )
                        rendered[i + k] = self._apply_alignment(
                            processed, alignment, width=board_width, extended_markup=extended_markup
                        )

                skip_until = i + len(wrapped_lines) - 1
            else:
                rendered_line = _render_cached(i)

                if "\n" in rendered_line:
                    # A row-emitting formula (FOREACH) spills into the rows
                    # below exactly as |wrap overflow does, so it stops where
                    # |wrap would. Without this it wrote straight over a
                    # footer, and the footer was not pushed down or shown
                    # anywhere — it was simply gone.
                    split_lines = rendered_line.split("\n")[: _overflow_budget(i)]
                    for line_idx, split_line in enumerate(split_lines):
                        if i + line_idx >= num_rows:
                            break
                        processed_line = self._process_fill_space(
                            split_line, width=board_width, extended_markup=extended_markup
                        )
                        rendered[i + line_idx] = self._apply_alignment(
                            processed_line, alignment, width=board_width, extended_markup=extended_markup
                        )
                    if len(split_lines) > 1:
                        skip_until = min(i + len(split_lines) - 1, num_rows - 1)
                else:
                    rendered_line = self._process_fill_space(
                        rendered_line, width=board_width, extended_markup=extended_markup
                    )
                    rendered[i] = self._apply_alignment(
                        rendered_line, alignment, width=board_width, extended_markup=extended_markup
                    )

        return "\n".join(rendered)

    @staticmethod
    def _find_wrap_expression(template: str) -> tuple[int, int, str] | None:
        """Find the first ``{{...}}`` whose filter chain contains ``|wrap``.

        Linear-time replacement for the former regex
        ``\\{\\{([^}]+\\|wrap(?:\\|[^}]*)?)\\}\\}``, which backtracked
        polynomially on adversarial user-authored templates (CodeQL alert
        #65, py/polynomial-redos). The matching semantics are preserved
        exactly: the expression is everything between ``{{`` and the first
        following ``}`` (which must itself be followed by another ``}``),
        and it qualifies when splitting on ``|`` yields a segment equal to
        ``wrap`` (lowercase, unstripped — same as the old regex) that is
        preceded by at least one character.

        Args:
            template: Template string to scan

        Returns:
            ``(start, end, expr)`` for the first qualifying ``{{expr}}``
            (``start``/``end`` span the braces), or ``None``.
        """
        pos = 0
        while True:
            start = template.find("{{", pos)
            if start == -1:
                return None
            close = template.find("}", start + 2)
            if close == -1:
                return None
            if template[close + 1 : close + 2] != "}":
                # "{{...}" without a second "}": nothing can match at or
                # before this "}", so resume scanning right after it.
                pos = close + 1
                continue
            expr = template[start + 2 : close]
            segments = expr.split("|")
            for idx in range(1, len(segments)):
                # idx > 1 or a non-empty first segment mirrors the old
                # regex's [^}]+ requirement of ≥1 char before "|wrap".
                if segments[idx] == "wrap" and (idx > 1 or segments[0]):
                    return (start, close + 2, expr)
            pos = close + 2

    def _render_with_wrap(
        self,
        template: str,
        context: dict[str, Any],
        max_lines: int = 1,
        board_width: int = 22,
        *,
        extended_markup: bool = False,
    ) -> list[str]:
        """Render a template line that should wrap across multiple lines.

        Handles two cases:
        1. Line-level wrap (via {wrap} prefix): wraps the entire rendered content
        2. Variable-level wrap (via |wrap filter): wraps only the variable with |wrap

        Args:
            template: Template string that may contain |wrap filter or should be wrapped entirely
            context: Data context
            max_lines: Maximum number of lines to fill
            board_width: Board width in columns (default 22 for flagship)

        Returns:
            List of rendered lines (up to max_lines)
        """
        # First, check if there's a variable with |wrap filter (variable-level wrap)
        wrap_match = self._find_wrap_expression(template)

        if wrap_match:
            # Variable-level wrap: wrap only the variable with |wrap filter
            # Get the variable expression (without |wrap)
            match_start, match_end, expr = wrap_match
            # Remove |wrap from the filter chain
            parts = expr.split("|")
            var_part = parts[0].strip()
            other_filters = [p for p in parts[1:] if p.lower() != "wrap"]

            # Get the raw value
            value = self._get_variable_value(var_part, context)

            # Apply any other filters (except wrap)
            for f in other_filters:
                value = self._apply_filter(value, f)
            value = self._as_data(var_part, value)

            # Get prefix and suffix around the variable
            prefix = template[:match_start]
            suffix = template[match_end:]

            # Render prefix and suffix (they may have other variables)
            prefix = self.render(prefix, context, extended_markup=extended_markup)
            suffix = self.render(suffix, context, extended_markup=extended_markup)

            # Calculate available width for wrapped content using tile counts, not character counts
            # Color markers like {67} are 4 characters but only 1 tile
            prefix_tiles = self._count_tiles(prefix, extended_markup=extended_markup)
            suffix_tiles = self._count_tiles(suffix, extended_markup=extended_markup)

            # First line has prefix and suffix
            first_line_width = max(1, board_width - prefix_tiles - suffix_tiles)  # Ensure at least 1 tile available
            # Subsequent lines have full width
            subsequent_width = board_width

            wrapped = self._word_wrap(
                value, first_line_width, subsequent_width, max_lines, extended_markup=extended_markup
            )

            # Build result lines
            result = []
            for idx, wrapped_line in enumerate(wrapped):
                if idx == 0:
                    result.append(f"{prefix}{wrapped_line}{suffix}")
                else:
                    result.append(wrapped_line)

            return result
        # Line-level wrap: render the entire template first, then wrap the result
        rendered = self.render(template, context, extended_markup=extended_markup)

        # Use tile-based wrapping for the entire rendered content
        # Full width available on all lines
        return self._word_wrap_tiles(
            rendered,
            first_width=board_width,
            subsequent_width=board_width,
            max_lines=max_lines,
            extended_markup=extended_markup,
        )

    def _word_wrap(
        self, text: str, first_width: int, subsequent_width: int, max_lines: int, *, extended_markup: bool = False
    ) -> list[str]:
        """Word-wrap text across multiple lines.

        Args:
            text: Text to wrap
            first_width: Width available on first line
            subsequent_width: Width available on subsequent lines
            max_lines: Maximum number of lines
            extended_markup: Wrap by drawn tiles, as :meth:`_word_wrap_tiles`
                does with it on.

        Returns:
            List of wrapped lines
        """
        if not text:
            return [""]
        if extended_markup:
            return self._word_wrap_tiles(text, first_width, subsequent_width, max_lines, extended_markup=True)

        words = text.split()
        lines = []
        current_line = ""
        current_width = first_width

        for word in words:
            if not current_line:
                # First word on line
                if len(word) <= current_width:
                    current_line = word
                else:
                    # Word too long, truncate
                    current_line = word[:current_width]
            elif len(current_line) + 1 + len(word) <= current_width:
                # Word fits on current line
                current_line += " " + word
            else:
                # Start new line
                lines.append(current_line)
                if len(lines) >= max_lines:
                    break
                current_line = word[:subsequent_width] if len(word) > subsequent_width else word
                current_width = subsequent_width

        # Don't forget the last line
        if current_line and len(lines) < max_lines:
            lines.append(current_line)

        # Ensure we have at least one line
        if not lines:
            lines = [""]

        return lines

    def _split_into_tokens(self, text: str) -> list[str]:
        """Split text into tokens (complete color markers or single characters).

        This ensures color markers are never split in the middle.

        Args:
            text: Text to split (may contain color markers like {67})

        Returns:
            List of tokens, where each token is either a complete color marker
            (like {67} or {red}) or a single character
        """
        tokens = []
        i = 0

        while i < len(text):
            if text[i] == "{":
                # Found a potential color marker
                closing_brace = text.find("}", i)
                if closing_brace != -1:
                    content = text[i + 1 : closing_brace]
                    if content.isdigit() and _is_color_code(int(content)):
                        # It's a numeric color marker
                        tokens.append(text[i : closing_brace + 1])
                        i = closing_brace + 1
                        continue
                    if content.lower() in COLOR_CODES:
                        # Named color marker
                        tokens.append(text[i : closing_brace + 1])
                        i = closing_brace + 1
                        continue
                    if content.startswith("/"):
                        # End tag - treat as single token
                        tokens.append(text[i : closing_brace + 1])
                        i = closing_brace + 1
                        continue

            # Regular character
            tokens.append(text[i])
            i += 1

        return tokens

    def _word_wrap_tiles(
        self, text: str, first_width: int, subsequent_width: int, max_lines: int, *, extended_markup: bool = False
    ) -> list[str]:
        """Word-wrap text across multiple lines using tile counts instead of character counts.

        This is used for line-level wrap where the text may contain color markers
        like {67} which are 4 characters but only 1 tile.

        Args:
            text: Text to wrap (may contain color markers like {67})
            first_width: Tile width available on first line
            subsequent_width: Tile width available on subsequent lines
            max_lines: Maximum number of lines
            extended_markup: Wrap by drawn tiles with :func:`src.markup.wrap_line`
                (FiestaUI semantics): never inside a span, block or icon, and
                a span crossing rows is closed on one and reopened on the next.

        Returns:
            List of wrapped lines
        """
        if not text:
            return [""]
        if extended_markup:
            return wrap_line(text, subsequent_width, first_cols=first_width)[:max_lines]

        # Split into words, preserving color markers
        # We'll split on spaces but keep color markers with adjacent text
        words = []
        current_word = ""
        i = 0

        while i < len(text):
            if text[i] == "{":
                # Found a potential color marker
                closing_brace = text.find("}", i)
                if closing_brace != -1:
                    content = text[i + 1 : closing_brace]
                    if content.isdigit() and _is_color_code(int(content)):
                        # It's a color marker - add to current word
                        current_word += text[i : closing_brace + 1]
                        i = closing_brace + 1
                        continue
                    if content.lower() in COLOR_CODES:
                        # Named color marker
                        current_word += text[i : closing_brace + 1]
                        i = closing_brace + 1
                        continue

            if text[i].isspace():
                if current_word:
                    words.append(current_word)
                    current_word = ""
            else:
                current_word += text[i]
            i += 1

        if current_word:
            words.append(current_word)

        # Now wrap using tile counts
        lines = []
        current_line = ""
        current_width = first_width

        for word in words:
            word_tiles = self._count_tiles(word)
            current_line_tiles = self._count_tiles(current_line) if current_line else 0

            if not current_line:
                # First word on line
                if word_tiles <= current_width:
                    current_line = word
                else:
                    # Word too long - break it across multiple lines using tokens
                    remaining_word = word
                    while remaining_word and len(lines) < max_lines:
                        # Split into tokens to avoid breaking color markers
                        tokens = self._split_into_tokens(remaining_word)
                        test_line = ""
                        tokens_to_take = 0

                        for token in tokens:
                            test_with_token = test_line + token
                            if self._count_tiles(test_with_token) > current_width:
                                break
                            test_line = test_with_token
                            tokens_to_take += 1

                        if tokens_to_take > 0:
                            current_line = "".join(tokens[:tokens_to_take])
                            remaining_word = "".join(tokens[tokens_to_take:])
                            lines.append(current_line)
                            if len(lines) >= max_lines:
                                break
                            current_line = ""
                            current_width = subsequent_width
                        else:
                            # Can't fit even one token (shouldn't happen, but handle it)
                            # Force at least one token to prevent infinite loop
                            if tokens:
                                current_line = tokens[0]
                                remaining_word = "".join(tokens[1:])
                                lines.append(current_line)
                                if len(lines) >= max_lines:
                                    break
                                current_line = ""
                                current_width = subsequent_width
                            else:
                                break
                    current_line = remaining_word if remaining_word else ""
            elif current_line_tiles + 1 + word_tiles <= current_width:
                # Word fits on current line
                current_line += " " + word
            else:
                # Start new line
                lines.append(current_line)
                if len(lines) >= max_lines:
                    break
                # Try to fit word on new line
                if word_tiles <= subsequent_width:
                    current_line = word
                else:
                    # Word too long - break it across multiple lines using tokens
                    remaining_word = word
                    current_line = ""
                    current_width = subsequent_width
                    while remaining_word and len(lines) < max_lines:
                        # Split into tokens to avoid breaking color markers
                        tokens = self._split_into_tokens(remaining_word)
                        test_line = ""
                        tokens_to_take = 0

                        for token in tokens:
                            test_with_token = test_line + token
                            if self._count_tiles(test_with_token) > current_width:
                                break
                            test_line = test_with_token
                            tokens_to_take += 1

                        if tokens_to_take > 0:
                            current_line = "".join(tokens[:tokens_to_take])
                            remaining_word = "".join(tokens[tokens_to_take:])
                            lines.append(current_line)
                            if len(lines) >= max_lines:
                                break
                            current_line = ""
                        else:
                            # Can't fit even one token - force at least one to prevent infinite loop
                            if tokens:
                                current_line = tokens[0]
                                remaining_word = "".join(tokens[1:])
                                lines.append(current_line)
                                if len(lines) >= max_lines:
                                    break
                                current_line = ""
                            else:
                                break
                    current_line = remaining_word if remaining_word else ""
                current_width = subsequent_width

        # Don't forget the last line
        if current_line and len(lines) < max_lines:
            lines.append(current_line)

        # Ensure we have at least one line
        if not lines:
            lines = [""]

        return lines

    def _build_context(self, board: BoardContext | None = None, plugin_ids: "set[str] | None" = None) -> dict[str, Any]:
        """Build context by fetching data from enabled plugins.

        Args:
            board: Board being rendered on, forwarded to plugins so board-aware
                ones can adapt their data. ``None`` keeps board-agnostic behavior.
            plugin_ids: Fetch only these plugins (plus trigger plugins, which
                the registry adds itself). ``None`` fetches everything — the
                safe fallback for a template whose variable owners cannot be
                determined statically.

        Returns:
            Dictionary mapping plugin_id to plugin data
        """
        if not self._plugin_registry:
            return {}

        if plugin_ids is None:
            return self._plugin_registry.build_template_context(board)
        return self._plugin_registry.build_template_context(board, plugin_ids=plugin_ids)

    def _render_variables(self, template: str, context: dict[str, Any]) -> str:
        """Replace {{source.field}} variables with values from context.

        Also applies color rules from feature configuration if defined.
        """

        def replace_var(match):
            expr = match.group(1).strip()

            # Check for filter: {{value|filter:arg}}
            if "|" in expr:
                var_part, filter_part = expr.split("|", 1)
                value = self._get_variable_value(var_part.strip(), context)
                filtered = self._as_data(var_part, self._apply_filter(value, filter_part.strip()))
                # Apply color rules to the variable (before filtering changed it)
                color_prefix = self._get_color_for_value(var_part.strip(), context)
                return f"{color_prefix}{filtered}" if color_prefix else filtered
            value = self._as_data(expr, self._get_variable_value(expr, context))
            # Check if the value itself is a color code (e.g., {66})
            # This allows plugins to return color codes directly
            # Only recognize color codes, not color names (to avoid issues with team names like "Green Hornets")
            if isinstance(value, str):
                # Check if value is exactly a color code like {66}
                color_code_match = re.match(r"^\{(\d+)\}$", value)
                if color_code_match:
                    code = int(color_code_match.group(1))
                    if _is_color_code(code):
                        # Already a valid color code, return as-is
                        return value
                # If value already starts with a color code (e.g. {66}RISE), do not add
                # a color prefix (which would add an unwanted space after the tile)
                if re.match(r"^\{\d+\}", value):
                    return value

            # Apply color rules
            color_prefix = self._get_color_for_value(expr, context)
            return f"{color_prefix}{value}" if color_prefix else value

        return VAR_PATTERN.sub(replace_var, template)

    def _as_data(self, expr: str, value: Any) -> Any:
        """A substituted value as *data* (plan D19): neutralise any brace that
        is not a base-grammar tile or end tag, unless the plugin declares the
        variable ``"format": "markup"``. Applies on every output."""
        if not isinstance(value, str) or self._variable_format(expr) == "markup":
            return value
        return neutralize_data(value)

    def _variable_format(self, expr: str) -> str:
        """The manifest ``format`` of ``plugin[:instance].field[.n.sub]``; ``"text"`` if undeclared."""
        parts = expr.strip().split(".")
        registry = getattr(self, "_plugin_registry", None)
        if len(parts) < 2 or registry is None:
            return "text"
        manifest = registry.get_manifest(parts[0].lower().split(":", 1)[0])
        if manifest is None:
            return "text"
        metadata = manifest.variables.metadata
        fields = parts[1:]
        meta = metadata.get(".".join(fields)) or metadata.get(".".join("*" if f.isdigit() else f for f in fields))
        return meta.format if meta else "text"

    def _normalize_extended(self, template: str, context: dict[str, Any]) -> str:
        """Turn the double-brace authoring forms into single-brace markup (plan D19).

        ``{{red:HOT}}`` -> ``{red:HOT}``, ``{{black/white:OPEN}}`` ->
        ``{black/white:OPEN}``, ``{{icon:sun}}`` -> ``{icon:sun}``. The head
        grammar is closed (:data:`EXTENDED_HEAD_PATTERN`), so everything else,
        including instance keys like ``{{weather:sf.temperature}}`` and
        ``{{filled:-}}``, stays a variable. The body is rendered first
        (variables, formulas, tiles, nested spans), then wrapped. Runs before
        variable substitution, which would otherwise read ``red:HOT`` as a
        variable name.
        """
        return self._rewrite_extended(template, lambda body: self.render(body, context, extended_markup=True))

    @staticmethod
    def _rewrite_extended(template: str, body_of: Any) -> str:
        """``{{<head>:<body>}}`` -> ``{<head>:<body_of(body)>}`` for every authoring form."""
        out: list[str] = []
        i = 0
        while i < len(template):
            head = EXTENDED_HEAD_PATTERN.match(template, i)
            end = _matching_double_brace(template, i) if head else -1
            if end == -1:
                out.append(template[i])
                i += 1
                continue
            body = template[head.end() : end - 1]
            out.append("{" + head.group(1) + ":" + body_of(body) + "}")
            i = end + 1
        return "".join(out)

    def _get_configured_color_rules(self, plugin_id: str, base_plugin_id: str, field: str) -> list:
        """The rules that color ``plugin_id.field`` (see :func:`resolve_color_rules`)."""
        manifest = self._plugin_registry.get_manifest(base_plugin_id) if self._plugin_registry else None
        return resolve_color_rules(self.config_manager, plugin_id, field, manifest)

    def _get_color_for_value(self, expr: str, context: dict[str, Any]) -> str:
        """Get color tile prefix based on plugin color rules.

        Args:
            expr: Variable expression like 'weather.temperature'
            context: Data context

        Returns:
            Color prefix like '{65} ' or empty string if no rule matches
        """
        parts = expr.split(".")
        if len(parts) < 2:
            return ""

        plugin_id = parts[0].lower()
        field = parts[1].lower()

        # For plugin instances the key has the form "weather:sf".  Color rules
        # and manifests are registered under the base plugin ID only, so strip
        # any instance suffix before looking them up.
        base_plugin_id = plugin_id.split(":", 1)[0]

        # Skip automatic coloring for fields that have separate _color variables
        # These fields should only be colored via their explicit _color variable
        if field in ("uv_index", "temperature"):
            return ""

        rules = self._get_configured_color_rules(plugin_id, base_plugin_id, field)
        if not rules:
            return ""

        # Map field name for data lookup (e.g., 'temp' -> 'temperature' for weather)
        data_field = self._map_field_for_data_lookup(base_plugin_id, field)

        # Get the raw value for comparison
        raw_value = None
        if plugin_id in context:
            raw_value = context[plugin_id].get(data_field) or context[plugin_id].get(parts[1])

        if raw_value is None:
            return ""

        # Evaluate rules in order (first match wins)
        for rule in rules:
            condition = rule.get("condition", "==")
            rule_value = rule.get("value")
            color = rule.get("color", "")

            if self._evaluate_condition(raw_value, condition, rule_value):
                # Return color code with space
                color_code = COLOR_CODES.get(color.lower(), color)
                if isinstance(color_code, int):
                    return f"{{{color_code}}} "
                return ""

        return ""

    def _evaluate_condition(self, actual: Any, condition: str, expected: Any) -> bool:
        """Evaluate a color rule condition.

        Args:
            actual: The actual value from data
            condition: Comparison operator (==, !=, >, <, >=, <=)
            expected: The expected value from rule

        Returns:
            True if condition matches
        """
        try:
            # Try numeric comparison first
            if condition in (">", "<", ">=", "<="):
                actual_num = float(actual)
                expected_num = float(expected)

                if condition == ">":
                    return actual_num > expected_num
                if condition == "<":
                    return actual_num < expected_num
                if condition == ">=":
                    return actual_num >= expected_num
                if condition == "<=":
                    return actual_num <= expected_num

            # String comparison
            actual_str = str(actual).lower()
            expected_str = str(expected).lower()

            if condition == "==":
                return actual_str == expected_str
            if condition == "!=":
                return actual_str != expected_str

        except (ValueError, TypeError):
            # Fall back to string comparison
            if condition == "==":
                return str(actual).lower() == str(expected).lower()
            if condition == "!=":
                return str(actual).lower() != str(expected).lower()

        return False

    def _get_variable_value(self, expr: str, context: dict[str, Any]) -> str:
        """Get value from context using dot notation (source.field).

        Also supports _color suffix to get just the color tile for a field.
        e.g., {{weather.temperature_color}} returns {65} based on temperature value.

        Supports array access:
        - {{baywheels.stations.0.electric_bikes}} - Access first station's e-bikes
        - {{baywheels.stations.1.station_name}} - Access second station's name

        Supports Home Assistant entity_id based lookups:
        - {{home_assistant.sensor_temperature.state}} - Get state of sensor.temperature
        - {{home_assistant.media_player_living_room.media_title}} - Get media_title attribute

        Special variables:
        - fill_space: Returns a placeholder that will be expanded later

        Returns "???" if variable is unavailable (API error, missing data, etc.)
        """
        # Handle special fill_space variable
        if expr.lower() == "fill_space":
            return "\x00FILL_SPACE\x00"  # Special marker to be processed later

        # Handle filled:char — user-facing alias for fill_space_repeat
        if expr.lower().startswith("filled:"):
            repeat_str = expr.split(":", 1)[1]
            return f"\x00FILL_SPACE_REPEAT:{repeat_str}\x00"

        # Handle fill_space_repeat:char/string variable (backward compat)
        if expr.lower().startswith("fill_space_repeat:"):
            repeat_str = expr.split(":", 1)[1] if ":" in expr else " "
            return f"\x00FILL_SPACE_REPEAT:{repeat_str}\x00"  # Special marker with repeat pattern

        parts = expr.split(".")

        if len(parts) < 2:
            return "???"  # Invalid expression

        source = parts[0].lower()

        # Special handling for home_assistant with entity_id syntax
        # Format: home_assistant.entity_id.attribute (3 parts minimum)
        if source == "home_assistant" and len(parts) >= 3:
            # Convert underscores back to dots for entity_id
            # (entity_id uses dots like sensor.temperature, but dots can't be in template syntax)
            # So we expect: home_assistant.sensor_temperature.state
            # Which maps to: entity_id=sensor.temperature, attribute=state
            entity_id_part = parts[1]
            attribute = parts[2]

            ha_data = context.get("home_assistant", {})

            # Smart entity_id conversion: try different underscore positions
            # Some domains have underscores (media_player, binary_sensor, device_tracker, etc.)
            # Try to find the entity by testing different split points
            entity_id = None
            entity_data = {}

            if "_" in entity_id_part:
                # Try each underscore position as a potential domain/entity split
                parts_split = entity_id_part.split("_")
                for i in range(1, len(parts_split)):
                    # Try domain as first i parts, rest as entity name
                    test_domain = "_".join(parts_split[:i])
                    test_entity = "_".join(parts_split[i:])
                    test_entity_id = f"{test_domain}.{test_entity}"

                    if test_entity_id in ha_data:
                        entity_id = test_entity_id
                        entity_data = ha_data[test_entity_id]
                        break

                # Fallback to old behavior if no match found (replace first underscore)
                if not entity_data:
                    entity_id = entity_id_part.replace("_", ".", 1)
                    entity_data = ha_data.get(entity_id, {})
            else:
                entity_id = entity_id_part
                entity_data = ha_data.get(entity_id, {})

            if not entity_data:
                return "???"  # Entity not found

            # Check if requesting the state directly
            if attribute == "state":
                return str(entity_data.get("state", "???"))

            # Check if requesting an attribute
            attributes = entity_data.get("attributes", {})
            if attribute in attributes:
                value = attributes[attribute]
                # Convert to string
                if value is None:
                    return "???"
                if isinstance(value, bool):
                    return "Yes" if value else "No"
                if isinstance(value, int | float):
                    return str(int(value) if float(value).is_integer() else round(value, 1))
                return str(value)

            # Check if attribute exists at top level
            if attribute in entity_data:
                value = entity_data[attribute]
                if value is None:
                    return "???"
                if isinstance(value, bool):
                    return "Yes" if value else "No"
                if isinstance(value, int | float):
                    return str(int(value) if float(value).is_integer() else round(value, 1))
                return str(value)

            return "???"  # Attribute not found

        field = parts[1]

        # Check if this is a _color request (case-insensitive)
        field_lower = field.lower()
        if field_lower.endswith("_color"):
            base_field = field_lower[:-6]  # Remove '_color' suffix (already lowercased)
            color_result = self._get_color_only(source, base_field, context)
            # If color lookup fails, return empty string (no color tile)
            return color_result if color_result else ""

        if source not in context:
            return "???"  # Source not available (API failed, not configured, etc.)

        # Navigate to the field, supporting array access
        value = context[source]
        for part in parts[1:]:
            if isinstance(value, dict):
                value = value.get(part, value.get(part.lower()))
                if value is None:
                    return "???"  # Field not found in data
            elif isinstance(value, list):
                # Handle array access: stations.0 or stations[0]
                try:
                    # Try to parse as integer index
                    if part.isdigit():
                        index = int(part)
                        if 0 <= index < len(value):
                            value = value[index]
                        else:
                            return "???"  # Index out of range
                    else:
                        # Try bracket notation: stations[0]
                        if "[" in part and "]" in part:
                            index_str = part[part.index("[") + 1 : part.index("]")]
                            index = int(index_str)
                            if 0 <= index < len(value):
                                value = value[index]
                            else:
                                return "???"  # Index out of range
                        else:
                            return "???"  # Invalid array access
                except (ValueError, IndexError):
                    return "???"  # Invalid index
            else:
                return "???"  # Invalid path

        # Convert to string
        if value is None:
            return "???"  # Null value
        if isinstance(value, bool):
            return "Yes" if value else "No"
        if isinstance(value, int | float):
            return str(int(value) if float(value).is_integer() else round(value, 1))
        if isinstance(value, list | dict):
            # A container has no board rendering — this used to emit a Python
            # repr ("[{'high': 70}]"). Arrays are reached with an index, or with
            # COUNT/AT/JOIN/FOREACH in a formula.
            logger.debug("Variable %s resolved to a %s; not renderable", expr, type(value).__name__)
            return "???"
        return str(value)

    def _get_color_only(self, plugin_id: str, field: str, context: dict[str, Any]) -> str:
        """Get just the color tile for a field based on color rules.

        Args:
            plugin_id: Plugin ID (e.g., 'weather' or 'weather:sf' for instances)
            field: Field name (e.g., 'temp')
            context: Data context

        Returns:
            Color tile like '{65}' or empty string if no rule matches
        """
        # For plugin instances the key has the form "weather:sf".  Color rules
        # and manifests are registered under the base plugin ID only.
        base_plugin_id = plugin_id.split(":", 1)[0]

        rules = self._get_configured_color_rules(plugin_id, base_plugin_id, field)
        if not rules:
            return ""

        # Map field name for data lookup (e.g., 'temp' -> 'temperature' for weather)
        # Use base_plugin_id for field mapping; look up data under full plugin_id key
        data_field = self._map_field_for_data_lookup(base_plugin_id, field)

        # Get the raw value for comparison
        raw_value = None
        if plugin_id in context:
            raw_value = context[plugin_id].get(data_field) or context[plugin_id].get(data_field.lower())

        if raw_value is None:
            return ""

        # Evaluate rules in order (first match wins)
        for rule in rules:
            condition = rule.get("condition", "==")
            rule_value = rule.get("value")
            color = rule.get("color", "")

            if self._evaluate_condition(raw_value, condition, rule_value):
                color_code = COLOR_CODES.get(color.lower(), color)
                if isinstance(color_code, int):
                    return f"{{{color_code}}}"
                return ""

        return ""

    def _map_field_for_data_lookup(self, source: str, field: str) -> str:
        """Map field name from config to data field name.

        Some fields in config (like color rules) use different names than
        the actual data fields. This maps them appropriately.

        Args:
            source: Data source name (e.g., 'weather')
            field: Field name from config (e.g., 'temp')

        Returns:
            Field name as it appears in the data (e.g., 'temperature')
        """
        # Map weather.temp -> temperature (for backward compatibility with old 'temp' field name)
        # The primary field name is now 'temperature', so temperature_color works directly
        if source == "weather" and field == "temp":
            return "temperature"

        return field

    def _apply_filter(self, value: str, filter_expr: str) -> str:
        """Apply a filter chain to a value.

        ``filter_expr`` is everything after the first ``|``, so it may hold
        several filters (``upper|truncate:3``); they apply left to right. The
        chain was documented from the start but used to be parsed as one filter
        name, which made every chain a silent no-op.

        Supported filters:
        - upper / lower - Change case
        - pad:N - Right-pad with spaces to N characters
        - truncate:N - Truncate to N characters
        - zeropad:N - Left-pad with zeros to N characters (e.g., 1 -> 01).
          For numeric values, a leading '-' sign is preserved (e.g., -1 -> -01).
        - wrap - Handled by the wrap machinery in ``render_lines``; a no-op here.

        An unrecognised filter leaves the value untouched (the board must still
        show something); ``validate_template`` reports it so the author can see
        why nothing happened.
        """
        for single in filter_expr.split("|"):
            value = self._apply_single_filter(value, single.strip())
        return value

    def _apply_single_filter(self, value: str, filter_expr: str) -> str:
        """Apply one filter (see :meth:`_apply_filter` for the roster)."""
        if ":" not in filter_expr:
            name = filter_expr.lower()
            if name == "upper":
                return value.upper()
            if name == "lower":
                return value.lower()
            return value

        if ":" in filter_expr:
            filter_name, arg = filter_expr.split(":", 1)
            filter_name = filter_name.lower()

            if filter_name == "pad":
                try:
                    width = int(arg)
                    return value.ljust(width)[:width]
                except ValueError:
                    return value

            elif filter_name == "truncate":
                try:
                    length = int(arg)
                    return value[:length]
                except ValueError:
                    return value

            elif filter_name == "zeropad":
                try:
                    width = int(arg)
                except ValueError:
                    return value
                if width <= 0:
                    return value
                if value.startswith("-"):
                    return "-" + value[1:].rjust(width - 1, "0")
                return value.rjust(width, "0")

        return value

    def _render_symbols(self, template: str, *, extended_markup: bool = False) -> str:
        """Replace {symbol} shortcuts.

        With ``extended_markup`` off: the legacy ASCII stand-in from
        :data:`SYMBOL_CHARS`. With it on: the icon the registry names
        (``{icon:<canonical name>}``), or ``♥`` for ``{heart}``.
        """

        def replace_symbol(match):
            symbol = match.group(1).lower()
            if extended_markup:
                if symbol == "heart":
                    return "♥"
                icon = resolve_icon_name(symbol)
                if icon is not None:
                    return "{icon:" + icon + "}"
            return SYMBOL_CHARS.get(symbol, match.group(0))

        return SYMBOL_PATTERN.sub(replace_symbol, template)

    def _normalize_colors(self, template: str) -> str:
        """Normalize color markers to consistent format.

        Converts named colors to code format for consistency.
        e.g., {{red}} -> {63} (single brackets so VAR_PATTERN won't match them)
        """

        def replace_color(match):
            color = match.group(1).lower()
            if color.isdigit():
                return f"{{{color}}}"
            code = COLOR_CODES.get(color)
            if code:
                return f"{{{code}}}"
            return match.group(0)

        return COLOR_PATTERN.sub(replace_color, template)

    def _extract_alignment(self, line: str) -> tuple:
        """Extract alignment and wrap directives from a line.

        Delegates to the shared ``extract_alignment_from_line`` utility.
        """
        return extract_alignment_from_line(line)

    def _apply_alignment(self, text: str, alignment: str, width: int = 22, *, extended_markup: bool = False) -> str:
        """Apply alignment to rendered text.

        Args:
            text: Rendered text (may contain color markers)
            alignment: 'left', 'center', or 'right'
            width: Target width (default 22 for board)
            extended_markup: Measure and cut by drawn tiles (see
                :meth:`_count_tiles`). A cut no markup can express keeps a
                whole span for the cut-off part, so the kept part can fall
                short of *width*; it is then aligned like any short row.

        Returns:
            Text padded/aligned to the specified width
        """
        if extended_markup:
            text = self._truncate_to_tiles(text, width, extended_markup=True)
            tile_count = self._count_tiles(text, extended_markup=True)
        else:
            # Calculate actual tile count (color markers count as 1 tile)
            tile_count = self._count_tiles(text)

        if tile_count >= width:
            # Already at or over width, truncate
            return self._truncate_to_tiles(text, width, extended_markup=extended_markup)

        padding_needed = width - tile_count

        if alignment == "center":
            left_pad = padding_needed // 2
            right_pad = padding_needed - left_pad
            return " " * left_pad + text + " " * right_pad
        if alignment == "right":
            return " " * padding_needed + text
        # left (default)
        return text + " " * padding_needed

    def _process_fill_space(self, text: str, width: int = 22, *, extended_markup: bool = False) -> str:
        """Process fill_space markers, expanding them to fill available space.

        If multiple fill_space markers exist, space is distributed evenly.
        The fill_space markers are represented by the special marker '\x00FILL_SPACE\x00'
        or '\x00FILL_SPACE_REPEAT:pattern\x00' after variable substitution.

        Pattern can be:
        - A color name (red, blue, etc.) - will repeat color tiles
        - A text pattern (-, =, etc.) - will repeat characters

        Args:
            text: Rendered text with fill_space markers
            width: Target width (default 22 for board)
            extended_markup: Measure the text around the markers, and cut it
                when there is no room, by drawn tiles (see :meth:`_count_tiles`).

        Returns:
            Text with fill_space markers replaced by appropriate padding
        """
        from src.board_chars import BoardChars

        # Find all fill markers (both regular and repeat)
        fill_pattern = re.compile(r"\x00FILL_SPACE(?:_REPEAT:(.+?))?\x00")
        fill_matches = list(fill_pattern.finditer(text))
        fill_count = len(fill_matches)

        if fill_count == 0:
            return text

        # Calculate text width without fill_space markers
        text_without_fills = fill_pattern.sub("", text)
        tile_count = self._count_tiles(text_without_fills, extended_markup=extended_markup)

        if tile_count >= width:
            # No room for fills, remove them
            return self._truncate_to_tiles(text_without_fills, width, extended_markup=extended_markup)

        # Calculate space to distribute
        total_fill_space = width - tile_count
        base_fill = total_fill_space // fill_count
        extra = total_fill_space % fill_count

        # Replace each fill_space marker with calculated padding
        result = text
        for i, match in enumerate(fill_matches):
            # Distribute extra space to earlier fills
            fill_width = base_fill + (1 if i < extra else 0)

            # Get the repeat pattern (group 1 from regex, or space as default)
            repeat_pattern = match.group(1) if match.group(1) else " "

            # Check if pattern is a color name
            color_code = BoardChars.get_color_code(repeat_pattern)
            if color_code is not None:
                # Repeat color tiles using the special color marker
                fill_content = f"{{{color_code}}}" * fill_width
            else:
                # Calculate how many times to repeat the text pattern
                pattern_len = len(repeat_pattern)
                if pattern_len > 0:
                    # Repeat pattern to fill width, may be truncated
                    full_repeats = fill_width // pattern_len
                    remainder = fill_width % pattern_len
                    fill_content = (repeat_pattern * full_repeats) + repeat_pattern[:remainder]
                else:
                    fill_content = " " * fill_width

            # Replace this specific match with the repeated pattern
            result = result.replace(match.group(0), fill_content, 1)

        return result

    def get_available_variables(self) -> dict[str, list[str]]:
        """Get list of all available template variables by plugin.

        Returns variables from enabled plugins.

        Returns:
            Dict mapping plugin_id to lists of field names
        """
        if not self._plugin_registry:
            return {}
        return self._plugin_registry.get_all_variables()

    def _get_available_sources(self) -> list[str]:
        """Get enabled plugin IDs.

        Returns:
            List of enabled plugin IDs
        """
        if not self._plugin_registry:
            return []
        return list(self._plugin_registry.enabled_plugins.keys())

    def validate_template(self, template: str, cols: int = 22, *, extended_markup: bool = False) -> list[TemplateError]:
        """Validate template syntax.

        Args:
            template: Template string to validate
            cols: Board column width to check against. Defaults to 22 (flagship).
                  Pass the actual board width for note/note_array devices.
                  TODO(#1176): callers in the web template editor should pass the
                  actual board width once web preview rendering is updated.
            extended_markup: The target board speaks extended markup: line
                length is measured in the tiles it draws (spans and blocks by
                their cells, icons and shortcut aliases as one tile).

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        lines = template.split("\n")

        # Get available sources based on system mode
        available_sources = self.get_all_known_sources()
        known_fields = self._known_fields()

        for line_num, line in enumerate(lines, 1):
            # Check for unclosed variable braces
            open_count = line.count("{{")
            close_count = line.count("}}")
            if open_count != close_count:
                errors.append(TemplateError(line=line_num, column=0, message="Mismatched variable braces {{}}"))

            max_length = self._calculate_max_line_length(line, cols=cols, extended_markup=extended_markup)
            if max_length > cols:
                errors.append(
                    TemplateError(
                        line=line_num,
                        column=cols,
                        message=f"Line may be too long (up to {max_length} chars, max {cols})",
                    )
                )

            # Check for invalid variable references
            for match in VAR_PATTERN.finditer(line):
                body = match.group(1)
                expr = body.split("|")[0].strip()
                # Skip formula bodies -- they're validated in the separate
                # ``find_formulas`` loop below.
                if expr.startswith("="):
                    continue

                for filter_name in self._filter_names_in(body):
                    if filter_name not in FILTER_NAMES:
                        errors.append(
                            TemplateError(
                                line=line_num,
                                column=match.start(),
                                message=f"Unknown filter: {filter_name} (value renders unchanged)",
                            )
                        )

                parts = expr.split(".")
                if len(parts) >= 2:
                    source = parts[0].lower()
                    if source not in available_sources:
                        errors.append(
                            TemplateError(line=line_num, column=match.start(), message=f"Unknown source: {source}")
                        )
                    else:
                        unknown_field = self._unknown_field(source, parts[1:], known_fields)
                        if unknown_field:
                            errors.append(
                                TemplateError(
                                    line=line_num,
                                    column=match.start(),
                                    message=f"Unknown field: {source}.{unknown_field} (renders as ???)",
                                )
                            )

            # Validate inline formulas ({{= ... }}). This surfaces parse
            # errors, unknown function names, unknown variable sources,
            # and obvious arity mistakes at edit time so users don't have
            # to wait for a render to discover problems.
            for start, _end, body in find_formulas(line):
                if not body:
                    continue
                for issue in validate_expression(body, known_sources=available_sources):
                    errors.append(
                        TemplateError(
                            line=line_num,
                            column=start,
                            message=f"Formula {issue.code}: {issue.message}",
                        )
                    )

        return errors

    @staticmethod
    def _filter_names_in(body: str) -> list[str]:
        """The filter names used by one ``{{...}}`` body, lowercased."""
        if "|" not in body:
            return []
        return [segment.strip().split(":", 1)[0].lower() for segment in body.split("|")[1:] if segment.strip()]

    def _known_fields(self) -> dict[str, set[str]]:
        """``{plugin_id: {declared field names}}`` for field validation.

        Built from the same catalog the editor autocompletes on, so a field the
        picker offers can never be flagged as unknown.
        """
        try:
            catalog = self.get_available_variables()
            return {source.lower(): {name.lower() for name in names} for source, names in catalog.items()}
        except Exception:
            # No catalog means no field validation — never a failed validate.
            logger.debug("Variable catalog unavailable for validation", exc_info=True)
            return {}

    def _unknown_field(self, source: str, path: list[str], known_fields: dict[str, set[str]]) -> str | None:
        """The field name to report as unknown, or ``None`` when it looks fine.

        Deliberately conservative — it only judges the FIRST path segment, so a
        deep path into a declared array (``forecast.0.high``) or a dynamic
        sub-array key is never flagged. It exists to catch the plain typo
        (``weather.temperatur``) that used to validate clean and render ``???``.

        Returns ``None`` without judging when:

        * the plugin declares no variables at all — an ``auto_discover`` plugin
          whose discovery fetch failed has an empty catalog, and guessing there
          would flag every field it exposes;
        * the source is ``home_assistant``, whose paths are entity ids resolved
          at render time rather than declared names.
        """
        if not path:
            return None
        base_source = source.split(":", 1)[0]
        if base_source == "home_assistant":
            return None

        fields = known_fields.get(source) or known_fields.get(base_source)
        if not fields:
            return None

        first = path[0].lower()
        candidates = {first}
        if first.endswith("_color"):
            candidates.add(first[: -len("_color")])
        if candidates & fields:
            return None
        # An array's documented pattern is stored as ``name.*.field``.
        if any(name.split(".", 1)[0] in candidates for name in fields):
            return None
        return path[0]

    def get_all_known_sources(self) -> set:
        """Get all known plugin IDs (for validation).

        Includes all plugins, not just enabled ones, so templates
        can be validated even if not all plugins are enabled.

        Public because routers validate payloads against it — reaching into
        another object's ``_private`` members from a route is exactly what
        ``docs/internal/reference/API_CONVENTIONS.md`` bans.
        """
        if not self._plugin_registry:
            return set()
        return set(self._plugin_registry.plugins.keys())

    def _calculate_max_line_length(self, line: str, cols: int = 22, *, extended_markup: bool = False) -> int:
        """Calculate maximum possible rendered length of a template line.

        Considers:
        - Static text (counted as-is)
        - Variables (replaced with their max character length)
        - Color markers (not counted - they become tiles)
        - |wrap filter (returns cols since it handles overflow)

        Args:
            line: Template line to analyze
            cols: Board column width. Defaults to 22 (flagship).
            extended_markup: Count drawn tiles under the extended grammar:
                ``{{red:HOT}}`` is 3, ``{{icon:sun}}`` and ``{sun}`` are 1,
                ``{heart}`` is 1 (♥), a variable inside a span its max length.

        Returns:
            Maximum possible character count after rendering
        """
        # If line has |wrap, it handles overflow automatically
        if "|wrap}}" in line or "|wrap|" in line:
            return cols  # Wrap ensures lines don't overflow

        # A row-emitting formula (FOREACH) returns newline-joined rows that
        # render_lines spreads down the board, so its width is per row, not the
        # sum. Measuring it as one line reported every such template as too
        # long.
        if any("FOREACH(" in body.upper() for _start, _end, body in find_formulas(line)):
            return cols

        # Start with the line
        result = line

        if extended_markup:
            # Authoring forms to the single-brace markup render() produces,
            # keeping each body's variables for the max-length pass below;
            # named tiles to codes so VAR_PATTERN cannot read them.
            def body_of(body: str) -> str:
                return self._rewrite_extended(body, body_of)

            result = self._normalize_colors(self._rewrite_extended(result, body_of))
        else:
            # Remove color markers (they become single tiles, count as 1 char each)
            # Replace {color} with single char placeholder
            result = re.sub(
                r"\{(red|orange|yellow|green|blue|violet|purple|white|black|6[3-9]|70)\}",
                "C",
                result,
                flags=re.IGNORECASE,
            )
            result = re.sub(
                r"\{/(red|orange|yellow|green|blue|violet|purple|white|black)?\}", "", result, flags=re.IGNORECASE
            )

            # Replace symbols with their character equivalent (usually 1-2 chars)
            for symbol, char in SYMBOL_CHARS.items():
                result = re.sub(rf"\{{{symbol}\}}", char, result, flags=re.IGNORECASE)

        # Get max lengths from appropriate source
        max_lengths = self._get_max_lengths_for_validation()

        def replace_with_max_length(match):
            expr = match.group(1).strip()
            # Remove filters for lookup
            var_part = expr.split("|")[0].strip().lower()

            # Check for color rules (adds 2 chars: color tile + space)
            color_prefix_len = 0
            parts = var_part.split(".")
            if len(parts) >= 2:
                plugin_id = parts[0]
                field = parts[1]
                # Check if plugin has color rules for this field
                try:
                    base_plugin_id = plugin_id.split(":", 1)[0]
                    rules = self._get_configured_color_rules(plugin_id, base_plugin_id, field)
                    if rules:
                        color_prefix_len = 2  # Color tile + space
                except Exception:
                    logger.debug("Error getting color rules for variable %s", var_part, exc_info=True)
            max_len = max_lengths.get(var_part)
            if max_len is None:
                max_len = 1 if self._renders_as_color_tile(parts) else cols
            return "X" * (max_len + color_prefix_len)

        result = VAR_PATTERN.sub(replace_with_max_length, result)

        if extended_markup:
            # Shortcuts become what the board draws ({sun} -> one icon tile,
            # {heart} -> ♥), then the line is measured in drawn tiles.
            return markup_count_tiles(self._render_symbols(result, extended_markup=True))
        return len(result)

    @staticmethod
    def _renders_as_color_tile(parts: list[str]) -> bool:
        """Whether ``_get_variable_value`` resolves this path to a color tile (or nothing).

        It treats ``source.<field>_color`` as a color lookup, except for Home
        Assistant entity paths (``home_assistant.light_x.rgb_color``), which
        return the raw attribute value.
        """
        if len(parts) < 2 or not parts[1].endswith("_color"):
            return False
        return not (parts[0] == "home_assistant" and len(parts) >= 3)

    def _get_max_lengths_for_validation(self) -> dict[str, int]:
        """Get max lengths for template validation.

        Returns all max lengths from all plugins (not just enabled ones) so
        templates can be fully validated.
        """
        if not self._plugin_registry:
            return {}

        max_lengths: dict[str, int] = {}
        # list() snapshots atomically, so a concurrent plugin install can't
        # mutate the manifests dict mid-iteration (#1828).
        for plugin_id, manifest in list(self._plugin_registry._manifests.items()):
            for var_name, max_len in manifest.max_lengths.items():
                full_name = f"{plugin_id}.{var_name}"
                max_lengths[full_name] = max_len
        return max_lengths

    def get_variable_max_lengths(self) -> dict[str, int]:
        """Get the max character lengths for all variables from enabled plugins.

        Returns:
            Dict mapping variable names to max lengths
        """
        if not self._plugin_registry:
            return {}
        return self._plugin_registry.get_all_max_lengths()

    def strip_formatting(self, text: str) -> str:
        """Remove all template formatting markers from text.

        Useful for getting plain text length or display.
        """
        # Remove variables that weren't resolved
        result = re.sub(r"\{\{[^}]*\}\}", "", text)
        # Remove color markers
        return re.sub(r"\{[^}]*\}", "", result)


# Singleton instance
_template_engine: TemplateEngine | None = None


def get_template_engine() -> TemplateEngine:
    """Get or create the template engine singleton."""
    global _template_engine
    if _template_engine is None:
        _template_engine = TemplateEngine()
    return _template_engine


def reset_template_engine() -> None:
    """Reset the template engine singleton to force reinitialization.

    This should be called when configuration changes to ensure
    the template engine picks up updated settings.
    """
    if _template_engine is not None:
        _template_engine.reset_cache()
    logger.info("Template engine reset")
