"""Board-geometry conformance checks for plugins.

A FiestaBoard plugin can be rendered onto any board the platform supports:
a Flagship (22x6), a Note (15x3), or a Note array of any size from 15x3 up
to 120x24 -- which is also what a FiestaPanel is (a virtual note array sized
to a TV). A plugin that only ever considered the Flagship will overflow a
Note and leave a panel almost entirely blank.

This module is the shared conformance suite. Plugin repositories import it
from their own tests; FiestaBoard core runs it over the built-in plugins.
Keeping it in one place means the definition of "supports every board" is
the same everywhere and moves in one edit.

Typical use from a plugin repository::

    from src.plugins.geometry_conformance import assert_board_conformance

    def test_board_conformance(monkeypatch):
        assert_board_conformance(lambda: make_plugin_with_mocked_network())

The callable must return a *fresh, ready-to-render* plugin: configured, and
with any network access already stubbed. The suite renders it many times and
never touches the network itself.

Two properties are deliberately NOT asserted by comparing rendered output
across boards. Plenty of plugins are legitimately non-deterministic (a random
joke, a rotating quote), so an equality check would flake. Instead the suite
renders every geometry on a single shared instance and then again in reverse
order: if a plugin caches rendered output without geometry in the key, the
stale frame shows up as an out-of-bounds violation, which is objective.
"""

from __future__ import annotations

import traceback
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from itertools import pairwise

from src.devices import NOTE_COLS, NOTE_ROWS, BoardContext
from src.plugins.base import PluginBase, PluginResult
from src.text_to_board import count_tiles

# Width below which the page editor's own validation is the binding
# constraint: a variable declared longer than this cannot be trusted to fit
# the narrowest board a user can own.
NARROWEST_BOARD_COLS = NOTE_COLS


def note_array(notes_wide: int, notes_tall: int) -> BoardContext:
    """Build a note-array :class:`BoardContext` from a note count per axis."""
    return BoardContext(
        device_type="note_array",
        rows=notes_tall * NOTE_ROWS,
        cols=notes_wide * NOTE_COLS,
    )


@dataclass(frozen=True)
class Geometry:
    """A board shape the conformance suite renders against."""

    label: str
    board: BoardContext

    @property
    def rows(self) -> int:
        return self.board.rows

    @property
    def cols(self) -> int:
        return self.board.cols


# The standard matrix. Note arrays are not simply "bigger than a Flagship":
# a 1-wide x 4-tall array is 15x12, NARROWER than a Flagship but twice as
# tall, and a 8-wide x 1-tall array is 120x3, wider but shorter. Code that
# assumes "not Flagship means smaller" fails one of those two, so both are
# in the matrix on purpose.
STANDARD_GEOMETRIES: tuple[Geometry, ...] = (
    Geometry("flagship 22x6", BoardContext.from_device_type("flagship")),
    Geometry("note 15x3", BoardContext.from_device_type("note")),
    Geometry("panel 30x12", note_array(2, 4)),
    Geometry("tall-narrow 15x12", note_array(1, 4)),
    Geometry("wide-short 120x3", note_array(8, 1)),
    Geometry("max array 120x24", note_array(8, 8)),
)

# Same width, increasing height. Holding width constant isolates the height
# variable, so a plugin that caps its item count independently of the board
# (a fixed MAX_ITEMS, a fixed character budget) shows up as a flat line here
# rather than being confounded by a width change.
GROWTH_LADDER: tuple[Geometry, ...] = (
    Geometry("15x3", BoardContext.from_device_type("note")),
    Geometry("15x12", note_array(1, 4)),
    Geometry("15x24", note_array(1, 8)),
)


@dataclass(frozen=True)
class Violation:
    """One conformance failure, with enough detail to act on."""

    code: str
    geometry: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.code}] {self.geometry}: {self.detail}"


@dataclass
class ConformanceReport:
    """Result of running the suite over one plugin."""

    plugin_id: str = ""
    violations: list[Violation] = field(default_factory=list)
    warnings: list[Violation] = field(default_factory=list)
    rows_by_geometry: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.violations

    def summary(self) -> str:
        lines = [f"Board-geometry conformance for {self.plugin_id or '<plugin>'}:"]
        if self.violations:
            lines.append(f"  {len(self.violations)} violation(s):")
            lines.extend(f"    {v}" for v in self.violations)
        else:
            lines.append("  no violations")
        if self.warnings:
            lines.append(f"  {len(self.warnings)} warning(s):")
            lines.extend(f"    {w}" for w in self.warnings)
        if self.rows_by_geometry:
            filled = ", ".join(f"{k}={v}" for k, v in self.rows_by_geometry.items())
            lines.append(f"  non-blank rows: {filled}")
        return "\n".join(lines)


PluginFactory = Callable[[], PluginBase]


def _render(plugin: PluginBase, board: BoardContext) -> tuple[list[str], Exception | None, dict]:
    """Render *plugin* for *board*; return its board lines, any error, and its data.

    Two live paths exist and both matter. ``PluginResult.formatted_lines``
    (consumed by ``src/displays/service.py``) is whole-board content. Most
    plugins instead expose template variables in ``PluginResult.data`` and
    let the user's page place them, which is why the data dict is returned
    too. ``get_formatted_display()`` is checked separately by
    :func:`_render_hook` because the platform never calls it.
    """
    try:
        result: PluginResult = plugin.get_data(board)
    except Exception as exc:
        return [], exc, {}

    data = result.data or {}

    if not getattr(result, "available", False):
        # An unavailable result puts nothing on the board. That is a valid
        # state (no network, nothing to show) and not a geometry failure.
        return [], None, {}

    if result.formatted_lines:
        return list(result.formatted_lines), None, data

    formatted = data.get("formatted")
    if isinstance(formatted, str) and formatted:
        return formatted.split("\n"), None, data

    return [], None, data


def _flatten(data: dict, prefix: str = "") -> dict[str, str]:
    """Flatten a plugin's data dict to ``name -> string value``.

    Array variables are addressed in manifests as ``items.*.name``, so list
    entries collapse to that same wildcard form and every element is checked
    against the one declared bound.
    """
    out: dict[str, str] = {}
    for key, value in (data or {}).items():
        name = f"{prefix}{key}"
        if isinstance(value, str):
            out[name] = value
        elif isinstance(value, dict):
            out.update(_flatten(value, f"{name}."))
        elif isinstance(value, list):
            for element in value:
                if isinstance(element, dict):
                    for sub, sub_value in _flatten(element, f"{name}.*.").items():
                        # Keep the longest element: it is the one that breaks.
                        if len(sub_value) >= len(out.get(sub, "")):
                            out[sub] = sub_value
    return out


def _check_declared_lengths(data: dict, declared: dict[str, int], geometry: Geometry) -> list[Violation]:
    """Check each variable actually fits the length its manifest declares.

    The page editor sizes templates from ``max_lengths``, so a variable that
    renders longer than it declares makes the editor's fit warnings wrong.
    Measured in tiles, because a colour marker is four characters and one
    tile -- the usual reason a declared bound looks wrong.
    """
    out: list[Violation] = []
    for name, value in _flatten(data).items():
        bound = declared.get(name)
        if bound is None:
            continue
        tiles = count_tiles(value)
        if tiles > bound:
            out.append(
                Violation(
                    "DECLARED_LENGTH_EXCEEDED",
                    geometry.label,
                    f"{name} rendered {tiles} tiles but manifest declares max_length {bound}",
                )
            )
    return out


def _render_hook(plugin: PluginBase, board: BoardContext) -> tuple[list[str], Exception | None]:
    """Render the ``get_formatted_display()`` hook with *board* bound.

    The platform has no caller for this hook today, but it is the documented
    contract and plugins do implement it, so a plugin that overrides it is
    held to the same bounds. Returns ``([], None)`` when not overridden.
    """
    if type(plugin).get_formatted_display is PluginBase.get_formatted_display:
        return [], None
    try:
        with plugin._bound_board(board):
            lines = plugin.get_formatted_display()
    except Exception as exc:
        return [], exc
    if not lines:
        return [], None
    if not isinstance(lines, list) or not all(isinstance(line, str) for line in lines):
        return [], TypeError(f"get_formatted_display() must return list[str], got {type(lines).__name__}")
    return list(lines), None


def _check_bounds(lines: Sequence[str], geometry: Geometry, source: str) -> list[Violation]:
    """Check *lines* fit *geometry* in both axes, counting tiles not characters."""
    out: list[Violation] = []
    if len(lines) > geometry.rows:
        out.append(
            Violation(
                "TOO_MANY_ROWS",
                geometry.label,
                f"{source} returned {len(lines)} rows, board has {geometry.rows}",
            )
        )
    for index, line in enumerate(lines):
        # Colour markers like {66} occupy one tile but four characters, so
        # len() overstates width. count_tiles is the board's own measure.
        tiles = count_tiles(line)
        if tiles > geometry.cols:
            out.append(
                Violation(
                    "ROW_TOO_WIDE",
                    geometry.label,
                    f"{source} row {index} is {tiles} tiles, board is {geometry.cols} wide: {line!r}",
                )
            )
    return out


def _non_blank(lines: Iterable[str]) -> int:
    return sum(1 for line in lines if line.strip())


def check_geometries(
    factory: PluginFactory,
    geometries: Sequence[Geometry] = STANDARD_GEOMETRIES,
    declared_max_lengths: dict[str, int] | None = None,
) -> ConformanceReport:
    """Render one plugin instance across *geometries*, forwards then back.

    Using a single instance is the point: the platform holds one instance per
    plugin id and renders it for every board, so this is the arrangement that
    exposes state or caches that are not keyed by geometry.
    """
    report = ConformanceReport()
    plugin = factory()
    report.plugin_id = getattr(plugin, "plugin_id", "") or ""

    declared = {k: v for k, v in (declared_max_lengths or {}).items() if isinstance(v, int)}
    saw_board_output = False

    # Forwards, then back. The reverse pass re-renders a geometry that has
    # already been seen, which is when a stale cached frame surfaces.
    order = list(geometries) + list(reversed(geometries))
    for geometry in order:
        lines, exc, data = _render(plugin, geometry.board)
        if exc is not None:
            report.violations.append(
                Violation("RAISED", geometry.label, f"get_data() raised {exc!r}\n{_short_tb(exc)}")
            )
            continue
        if lines:
            saw_board_output = True
        report.violations.extend(_check_bounds(lines, geometry, "formatted_lines"))
        report.rows_by_geometry[geometry.label] = _non_blank(lines)
        report.violations.extend(_check_declared_lengths(data, declared, geometry))

        hook_lines, hook_exc = _render_hook(plugin, geometry.board)
        if hook_exc is not None:
            report.violations.append(
                Violation("HOOK_RAISED", geometry.label, f"get_formatted_display() raised {hook_exc!r}")
            )
        else:
            report.violations.extend(_check_bounds(hook_lines, geometry, "get_formatted_display()"))

    if not saw_board_output:
        # The plugin renders through template variables rather than emitting
        # whole-board content. That is normal and valid, but it means the
        # row/column checks above had nothing to measure -- say so, so a
        # green run is never mistaken for proof the layout was exercised.
        report.warnings.append(
            Violation(
                "NO_BOARD_OUTPUT",
                "all geometries",
                "plugin emits no formatted_lines; row and width checks did not apply. "
                "Variable lengths were still checked against the manifest.",
            )
        )

    return report


def check_unbound_board(factory: PluginFactory) -> list[Violation]:
    """A plugin must render when no board is bound, defaulting to a Flagship.

    ``self.board`` is ``None`` outside a board-scoped render -- unit tests and
    legacy callers both hit this -- so treating it as "assume 22x6" rather
    than crashing is part of the contract.
    """
    plugin = factory()
    try:
        plugin.get_data(None)
    except Exception as exc:
        return [Violation("UNBOUND_RAISED", "board=None", f"get_data(None) raised {exc!r}")]
    return []


def check_growth(
    factory: PluginFactory,
    ladder: Sequence[Geometry] = GROWTH_LADDER,
) -> tuple[list[Violation], dict[str, int]]:
    """Taller boards must not render fewer rows than shorter ones.

    Width is held constant across the ladder so this measures the height
    response alone. A plugin that caps its output at a fixed item count or a
    fixed character budget stays flat here while the board grows, which is
    the "mostly empty panel" failure stated as an objective invariant rather
    than an arbitrary fill percentage.

    **What this cannot catch, by construction.** The rule fires only when a
    rung was filled to its last row, which proves more content existed than
    fit. A cap that lands just *under* a rung's capacity escapes: a plugin
    limited to 10 items renders 3 -> 11 -> 11 on this ladder, and 11 of 12
    rows is not saturation.

    That gap cannot be closed from out here. "Capped at 10" and "only has 7
    things to show" produce identical row counts, and the suite has no way to
    see how much content the plugin's upstream actually had -- widening the
    rule to catch the first misreports every plugin whose test fixture or
    ``maxItems`` config is legitimately small. An earlier attempt to gate on
    the shortest rung did exactly that, flagging four correct plugins whose
    output was bounded by their own config.

    So a data cap must be pinned by a test inside the plugin, which is the
    only place that knows what was available -- assert the cap itself scales
    with the board (``MAX_ITEMS == MAX_BOARD_ROWS - 1``) rather than
    asserting a rendered row count.
    """
    plugin = factory()
    counts: dict[str, int] = {}
    for geometry in ladder:
        lines, exc, _ = _render(plugin, geometry.board)
        if exc is not None:
            return [Violation("RAISED", geometry.label, f"get_data() raised {exc!r}")], counts
        counts[geometry.label] = _non_blank(lines)

    violations: list[Violation] = []
    for shorter, taller in pairwise(ladder):
        short_count = counts.get(shorter.label, 0)
        tall_count = counts.get(taller.label, 0)

        if tall_count < short_count:
            violations.append(
                Violation(
                    "SHRANK_ON_TALLER_BOARD",
                    taller.label,
                    f"{tall_count} non-blank rows vs {short_count} on the shorter {shorter.label}",
                )
            )
            continue

        # Saturation is what makes this decidable. If the shorter board was
        # filled to its last row the plugin had more to say than would fit,
        # so a taller board must show strictly more. If it was not full the
        # plugin simply ran out of content, which is legitimate -- a clock
        # has two lines to give and no board makes it a list.
        if short_count == shorter.rows and tall_count <= short_count:
            violations.append(
                Violation(
                    "DID_NOT_GROW",
                    taller.label,
                    f"{shorter.label} was full ({short_count}/{shorter.rows} rows) but "
                    f"{taller.label} still renders {tall_count} rows -- output is capped "
                    f"independently of the board",
                )
            )

    return violations, counts


def check_manifest(
    manifest: dict,
    *,
    require_note_array_preview: bool = False,
) -> tuple[list[Violation], list[Violation]]:
    """Static checks on a plugin manifest. Returns ``(violations, warnings)``.

    ``max_lengths`` above the Note width are reported because the page editor
    validates a template against the target board's column count: a variable
    declared at 22 passes validation on a Note it cannot actually fit.
    """
    violations: list[Violation] = []
    warnings: list[Violation] = []

    max_lengths = manifest.get("max_lengths") or {}
    for name, value in sorted(max_lengths.items()):
        if isinstance(value, int) and value > NARROWEST_BOARD_COLS:
            warnings.append(
                Violation(
                    "MAX_LENGTH_EXCEEDS_NOTE",
                    "manifest",
                    f"max_lengths[{name!r}] is {value}, wider than a Note ({NARROWEST_BOARD_COLS})",
                )
            )

    previews = manifest.get("previews") or []
    shapes = {(p.get("device_type") or "flagship") for p in previews if isinstance(p, dict)}
    if "note_array" not in shapes:
        entry = Violation(
            "NO_NOTE_ARRAY_PREVIEW",
            "manifest",
            "previews cover " + (", ".join(sorted(shapes)) or "nothing") + " but not note_array",
        )
        (violations if require_note_array_preview else warnings).append(entry)

    return violations, warnings


def run_conformance(
    factory: PluginFactory,
    *,
    manifest: dict | None = None,
    geometries: Sequence[Geometry] = STANDARD_GEOMETRIES,
    strict_growth: bool = False,
    require_note_array_preview: bool = False,
) -> ConformanceReport:
    """Run every conformance check and return a combined report."""
    report = check_geometries(factory, geometries, declared_max_lengths=(manifest or {}).get("max_lengths"))
    report.violations.extend(check_unbound_board(factory))

    growth_violations, counts = check_growth(factory)
    report.rows_by_geometry.update(counts)
    if strict_growth:
        report.violations.extend(growth_violations)
    else:
        report.warnings.extend(growth_violations)

    if manifest is not None:
        manifest_violations, manifest_warnings = check_manifest(
            manifest, require_note_array_preview=require_note_array_preview
        )
        report.violations.extend(manifest_violations)
        report.warnings.extend(manifest_warnings)

    return report


def assert_board_conformance(
    factory: PluginFactory,
    *,
    manifest: dict | None = None,
    geometries: Sequence[Geometry] = STANDARD_GEOMETRIES,
    strict_growth: bool = False,
    require_note_array_preview: bool = False,
) -> ConformanceReport:
    """Assert a plugin renders correctly on every supported board shape.

    Raises ``AssertionError`` with the full report when any hard check fails.
    Returns the report so a caller can inspect warnings.
    """
    report = run_conformance(
        factory,
        manifest=manifest,
        geometries=geometries,
        strict_growth=strict_growth,
        require_note_array_preview=require_note_array_preview,
    )
    assert report.ok, "\n" + report.summary()
    return report


def _short_tb(exc: BaseException, limit: int = 3) -> str:
    """Last few frames of *exc*'s traceback, for an actionable failure message."""
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__, limit=limit)[-limit:]).rstrip()
