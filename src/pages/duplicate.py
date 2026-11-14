"""Copy a page to another display's size, with a crop report (H9c).

"Make a copy for another display… Pick a display; the copy opens with a crop
report" (Figma 04d 1.6b). Nothing is silently rewritten: template lines keep
their text (render cuts what does not fit, and the report says which lines
will be cut, by H4's own ``line_too_long`` at the target width and charset);
lines and composite rows past the target's last row are dropped and listed;
canvases move with the same ``scale_area`` a board resize uses. The source
page is never changed. The copy records a saved version, ``origin:
duplicated``, and keeps the source's tags.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from src.canvas import scale_area
from src.devices import dimensions_of, geometry_of, resolve_dimensions

from .drafts import PageNotFound
from .history import page_content
from .models import Page

NAME_LIMIT = 100


def target_geometry(request: Any, board: dict | None, source: Page) -> tuple:
    """Explicit geometry, else the board's, else the source's (H4's resolution order)."""
    if request.device_type is not None:
        return (
            request.device_type,
            request.notes_wide or 1,
            request.notes_tall or 1,
            request.grid_rows,
            request.grid_cols,
        )
    if board is not None:
        return tuple(geometry_of(board))
    return tuple(geometry_of(source))


def _name(source: Page, given: str | None, board: dict | None) -> str:
    if given:
        return given
    suffix = f" ({board['name']})" if board is not None and board.get("name") else " copy"
    return (source.name[: NAME_LIMIT - len(suffix)] + suffix)[:NAME_LIMIT]


def _lines_too_long(template: list[str], line_metadata, cols: int, extended: bool) -> list[dict]:
    from src.templates.engine import get_template_engine

    kw = {"extended_markup": True} if extended else {}
    problems = get_template_engine().validate_template(
        "\n".join(template), cols=cols, line_metadata=line_metadata, **kw
    )
    return [{"line": p.line, "max_length": p.max_length} for p in problems if p.code == "line_too_long"]


def _extended_markup(board: dict | None) -> bool:
    """Whether the target board measures in drawn tiles (an LED face), as H4 decides it."""
    if board is None:
        return False
    try:
        from src.led.charsets import has_extended_markup
        from src.outputs.board_profile import board_character_set
        from src.outputs.display_profile import display_profile_for_board

        display = display_profile_for_board(board)
        charset = (
            dict(display.character_set)
            if display is not None and display.character_set is not None
            else board_character_set(board)
        )
        return has_extended_markup(charset)
    except Exception:
        return False


def duplicate_page(
    service: Any, page_id: str, request: Any, *, board: dict | None, via: str | None = None
) -> tuple[Page, dict]:
    """Create the copy; answer ``(page, report)``. ``ValueError`` when the copy is not a valid page."""
    with service.storage.lock:
        source = service.storage.get(page_id)
        if source is None:
            raise PageNotFound(page_id)
        old = dimensions_of(source)
        geometry = target_geometry(request, board, source)
        new = resolve_dimensions(*geometry)
        content = page_content(source)
        report: dict[str, Any] = {
            "rows": new.rows,
            "cols": new.cols,
            "from_rows": old.rows,
            "from_cols": old.cols,
            "lines_too_long": [],
            "rows_dropped": [],
            "composite_rows_dropped": [],
            "canvases_scaled": 0,
        }

        if source.template is not None:
            report["rows_dropped"] = [i for i, line in enumerate(source.template) if i >= new.rows and line.strip()]
            content["template"] = list(source.template[: new.rows])
            if source.line_metadata is not None:
                content["line_metadata"] = content["line_metadata"][: new.rows]

        if source.rows is not None:
            kept, dropped = [], []
            for index, row in enumerate(source.rows):
                if row.row_index < new.rows and row.target_row < new.rows:
                    kept.append(content["rows"][index])
                else:
                    dropped.append(index)
            content["rows"] = kept
            report["composite_rows_dropped"] = dropped

        if source.canvases and (old.rows, old.cols) != (new.rows, new.cols):
            content["canvases"] = [
                c.model_copy(update={"area": scale_area(c.area, (old.rows, old.cols), (new.rows, new.cols))})
                for c in source.canvases
            ]
            report["canvases_scaled"] = len(source.canvases)

        device_type, notes_wide, notes_tall, grid_rows, grid_cols = geometry
        content.update(
            device_type=device_type,
            notes_wide=notes_wide or 1,
            notes_tall=notes_tall or 1,
            grid_rows=grid_rows,
            grid_cols=grid_cols,
            name=_name(source, request.name, board),
        )
        try:
            copy = Page(**content, tags=list(source.tags), created_at=datetime.now(UTC))
        except ValidationError as exc:
            raise ValueError(f"Cannot copy the page to that size: {exc.errors()[0]['msg']}") from exc
        errors = copy.validate_config()
        if errors:
            raise ValueError(f"Cannot copy the page to that size: {'; '.join(errors)}")
        created = service.storage.create(copy)
        service._record_revision(created, origin="duplicated", via=via)

    if created.template:
        report["lines_too_long"] = _lines_too_long(
            created.template, created.line_metadata, new.cols, _extended_markup(board)
        )
    return created, report
