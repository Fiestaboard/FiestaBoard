"""The flexible page document (design: flexible pages, sections 2 and 3).

A flexible page has no grid. It is a stack of ``blocks`` styled by a page
``style`` and each block's own ``style``; the server lays it out once per
board. These models only check what a document *says*: style values are
requests, resolved (and compromised, with a reported issue) per board by
``src/layout/``.

Unknown block kinds, layout kinds and style properties are kept, through
:class:`ExtensibleDocument`, so older software preserves what it cannot draw.
"""

import re
from typing import Any, Literal

from pydantic import ConfigDict, Field, field_validator

from src.led.matrix import BOARD_COLORS
from src.pages.document import DocumentContent, ExtensibleDocument

__all__ = [
    "KNOWN_BLOCK_KINDS",
    "MAX_BLOCKS",
    "Block",
    "BlockStyle",
    "CanvasBlockBody",
    "FlexLayout",
    "FlexTargets",
    "PageStyle",
]

#: The most blocks one flexible page may hold.
MAX_BLOCKS = 32

#: The block kinds this build lays out; any other kind is kept and reported.
KNOWN_BLOCK_KINDS = frozenset({"text", "canvas", "spacer"})

_HEX6 = re.compile(r"#[0-9a-fA-F]{6}")
_TILE_CODE = re.compile(r"\{?(6[3-9]|7[01])\}?")
_ONE_EXPRESSION = re.compile(r"\{\{(?:(?!\{\{|\}\}).)*\}\}", re.DOTALL)


def _check_color_text(value: str | None) -> str | None:
    """A colour *request*: a board colour name, ``#rrggbb``, a tile code or one ``{{…}}``.

    Only the form is checked here. An expression's result is resolved per
    board at render time, where a bad value is a layout issue, not an error.
    The tile code may be braced (``{63}``) as in template colour markup.
    """
    if value is None:
        return None
    text = value.strip()
    if (
        text.lower() in BOARD_COLORS
        or _HEX6.fullmatch(text)
        or _TILE_CODE.fullmatch(text)
        or _ONE_EXPRESSION.fullmatch(text)
    ):
        return value
    raise ValueError(
        f"{value!r} is not a colour: use a board colour name ({', '.join(BOARD_COLORS)}), #rrggbb, "
        "a tile code 63-71, or one {{…}} expression"
    )


class BlockStyle(ExtensibleDocument):
    """Requested style for a block; each board shows the nearest it can.

    Every property is optional; an unset one falls through the cascade
    (device default, board style, page style, block style). ``color`` and
    ``background`` take a board colour name, ``#rrggbb``, a tile code 63-71,
    or one ``{{…}}`` expression.
    """

    font: str | None = None
    size: Literal["small", "medium", "large", "xlarge", "fit"] | int | None = None
    color: str | None = None
    background: str | None = None
    align: Literal["left", "center", "right"] | None = None
    case: Literal["as-is", "upper", "lower"] | None = None
    overflow: Literal["wrap", "shrink", "ellipsis", "scroll"] | None = None
    height: Literal["auto", "fill"] | int | float | None = None

    @field_validator("size")
    @classmethod
    def _size_in_range(cls, value: Any) -> Any:
        if isinstance(value, int) and not 1 <= value <= 256:
            raise ValueError("size in pixels must be between 1 and 256")
        return value

    @field_validator("color", "background")
    @classmethod
    def _color_form(cls, value: str | None) -> str | None:
        return _check_color_text(value)


class PageStyle(BlockStyle):
    """A flexible page's style defaults; blocks inherit and override them."""


class FlexLayout(ExtensibleDocument):
    """How blocks are arranged. Only ``stack`` is built; any kind is kept."""

    kind: str = "stack"
    valign: Literal["top", "middle", "bottom", "spread"] = "top"
    gap: Literal["none", "small", "medium", "large"] | int = "small"


class CanvasBlockBody(ExtensibleDocument):
    """A canvas block's drawing: today's canvas content, or a plugin source."""

    content: DocumentContent | None = None
    source: str | None = None


class Block(ExtensibleDocument):
    """One content unit of a flexible page.

    Known kinds are ``text`` (one line of template syntax), ``canvas`` and
    ``spacer``; a block of any other kind is kept as written. ``if`` is a
    formula: the block shows only while it is true.
    """

    # ``if`` is a Python keyword: the field is ``if_`` with the JSON name
    # ``if``, and page dumps always use the JSON name.
    model_config = ConfigDict(extra="allow", allow_inf_nan=False, populate_by_name=True)

    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,32}$")
    kind: str
    text: str | None = None
    canvas: CanvasBlockBody | None = None
    style: BlockStyle | None = None
    priority: int | None = Field(default=None, ge=0, le=1000)
    if_: str | None = Field(default=None, alias="if")


class FlexTargets(ExtensibleDocument):
    """Optional restriction of where a flexible page may be scheduled."""

    technology: list[str] | None = None
    boards: list[str] | None = None
