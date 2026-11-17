"""Typed, deterministic native renderer snapshot of the vendored FiestaUI data."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from src import fiestaui

Bitmap = list[Annotated[str, Field(pattern=r"^[#.]+$")]]
FontId = Literal["3x5", "5x7"]


class AssetModel(BaseModel):
    """Reject source drift instead of silently dropping new renderer fields."""

    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)


class LedFont(AssetModel):
    """A row-major face. '#' lights a pixel; '.' leaves it unlit."""

    glyph_width: int = Field(alias="glyphWidth", gt=0)
    glyph_height: int = Field(alias="glyphHeight", gt=0)
    spacing_x: int = Field(alias="spacingX", ge=0)
    spacing_y: int = Field(alias="spacingY", ge=0)
    glyphs: dict[str, Bitmap]
    icons: dict[str, Bitmap]


class BuiltinCharacterSet(AssetModel):
    """A flattened built-in set, retaining FiestaUI's document field names."""

    id: str
    label: str
    version: int = Field(ge=1)
    chars: list[str]
    tiles: bool
    icons: list[str]
    mixed_case: bool = Field(alias="mixedCase")
    color_spans: bool = Field(alias="colorSpans")
    block_spans: bool = Field(alias="blockSpans")
    extends: str | None = None
    font: FontId | None = None
    code62_glyph: Literal["degree", "heart"] | None = Field(default=None, alias="code62Glyph")
    glyphs: dict[str, Bitmap] | None = None


class RenderAssetSource(AssetModel):
    """The upstream data release; not the catalog's content revision."""

    source: str
    commit: str
    version: str


class RenderAssets(AssetModel):
    """One atomic built-in catalog, independent of boards and plugin state."""

    schema_version: Literal[1] = Field(description="Wire-format version, independent of charset versions.")
    revision: str = Field(pattern=r"^[0-9a-f]{64}$", description="SHA-256 of canonical fonts and character_sets JSON.")
    source: RenderAssetSource
    fonts: dict[str, LedFont]
    character_sets: dict[str, BuiltinCharacterSet]


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def render_asset_snapshot() -> tuple[bytes, str]:
    """Validate the current source, then hash exactly the bytes sent to clients.

    The source loaders cache file reads. Serialization is deliberately not cached:
    source changes in a reload must not leave the validator describing old data.
    """
    assets = {"fonts": fiestaui.builtin_led_fonts(), "character_sets": fiestaui.builtin_character_sets()}
    record = fiestaui.provenance()
    catalog = RenderAssets(
        schema_version=1,
        revision=hashlib.sha256(_canonical_json(assets)).hexdigest(),
        source=RenderAssetSource(**{key: record[key] for key in ("source", "commit", "version")}),
        **assets,
    )
    body = _canonical_json(catalog.model_dump(by_alias=True, exclude_none=True))
    return body, '"' + hashlib.sha256(body).hexdigest() + '"'


# RFC entity tags may contain commas. Validate the whole list before extracting
# tags, rather than treating a comma inside a quoted value as a separator.
_ENTITY_TAG = r'(?:W/)?"[\x21\x23-\x7e\x80-\xff]*"'
_ENTITY_TAG_LIST = re.compile(rf"[ \t]*{_ENTITY_TAG}(?:[ \t]*,[ \t]*{_ENTITY_TAG})*[ \t]*")


def matches_if_none_match(values: list[str] | None, etag: str) -> bool:
    """GET uses weak comparison, including repeated header fields and '*'."""
    if not values:
        return False
    combined = ", ".join(values).strip(" \t")
    if combined == "*":
        return True
    if not _ENTITY_TAG_LIST.fullmatch(combined):
        return False
    return any(tag.removeprefix("W/") == etag for tag in re.findall(_ENTITY_TAG, combined))
