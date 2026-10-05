"""FiestaUI's device vocabulary, as an output plugin's manifest is checked against it.

FiestaUI is the reference for what a display *is* (plan D15): a
**DeviceModel** (technology, geometry, colour, character set, animation,
appearance) and a **CharacterSet** (what the board can draw). An output
plugin declares its models and, optionally, its own character set in the
manifest ``output`` block; this module validates both against FiestaUI's
JSON Schemas and makes a declared character set whole (plan D17).

Everything here is **vendored** under ``schemas/fiestaui/`` — the two
schemas, plus FiestaUI's flattened built-in character sets and device
models — and the schemas resolve each other by ``$id`` through a local
``referencing`` registry, never over the network. Where the files came from,
and their sha256, is ``schemas/fiestaui/provenance.json``;
``tests/test_output_plugin_manifest.py`` holds the files to those hashes.

A built-in id (``vestaboard_v2``, ``divoom_pixoo64``) resolves to the
vendored data; an unknown id is an error, never coerced to a Vestaboard.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Iterable, Mapping
from functools import cache
from pathlib import Path
from typing import Any

SCHEMA_DIR = Path(__file__).parent / "schemas" / "fiestaui"
DEVICE_MODEL_SCHEMA_FILE = "device-model.schema.json"
CHARACTER_SET_SCHEMA_FILE = "character-set.schema.json"
BUILTIN_CHARACTER_SETS_FILE = "character-sets.json"
BUILTIN_DEVICE_MODELS_FILE = "device-models.json"


def _read(filename: str) -> Any:
    return json.loads((SCHEMA_DIR / filename).read_text(encoding="utf-8"))


@cache
def provenance() -> dict[str, Any]:
    """Where the vendored files came from, and their sha256."""
    return _read("provenance.json")


def vendored_digest(filename: str) -> str:
    """The sha256 of a vendored file as it is on disk."""
    return hashlib.sha256((SCHEMA_DIR / filename).read_bytes()).hexdigest()


@cache
def builtin_character_sets() -> Mapping[str, Mapping[str, Any]]:
    """FiestaUI's built-in character sets, flattened, by id."""
    return _read(BUILTIN_CHARACTER_SETS_FILE)


@cache
def builtin_device_models() -> Mapping[str, Mapping[str, Any]]:
    """FiestaUI's built-in device models, by id."""
    return _read(BUILTIN_DEVICE_MODELS_FILE)


class CharacterSetError(ValueError):
    """A declared character set cannot be made whole, or is not valid."""


@cache
def _validators() -> dict[str, Any]:
    """Draft-7 validators, resolving ``$ref`` by ``$id`` from the vendored files only."""
    from jsonschema import Draft7Validator
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT7

    schemas = {name: _read(name) for name in (DEVICE_MODEL_SCHEMA_FILE, CHARACTER_SET_SCHEMA_FILE)}
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema, default_specification=DRAFT7)) for schema in schemas.values()
    )
    return {name: Draft7Validator(schema, registry=registry) for name, schema in schemas.items()}


def _errors(validator: Any, value: Any, where: str) -> list[str]:
    found = sorted(validator.iter_errors(value), key=lambda e: [str(p) for p in e.absolute_path])
    out = []
    for error in found:
        path = "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in error.absolute_path)
        out.append(f"{where}{path}: {error.message}")
    return out


def validate_device_model(model: Any, where: str = "device_model") -> list[str]:
    """Errors for one DeviceModel object against FiestaUI's schema (empty = valid)."""
    return _errors(_validators()[DEVICE_MODEL_SCHEMA_FILE], model, where)


def validate_character_set(charset: Any, where: str = "character_set") -> list[str]:
    """Errors for a CharacterSet as a manifest may declare it.

    The schema itself tells a partial declaration from a whole one: a set
    that ``extends`` another needs only ``id``; one that extends nothing
    must be complete.
    """
    return _errors(_validators()[CHARACTER_SET_SCHEMA_FILE], charset, where)


def materialize_character_set(declaration: Mapping[str, Any], known: Iterable[Mapping[str, Any]] = ()) -> dict:
    """A declared character set made whole — a port of FiestaUI's
    ``materializeCharacterSet`` (``src/lib/character-sets.ts``).

    - A field the declaration gives **replaces** the parent's; arrays and
      ``glyphs`` are replaced wholesale, never merged.
    - A field it leaves out is **inherited** from the set it ``extends``: one
      of *known* (already materialised), else a built-in.
    - ``version`` is **not inherited**: the declaration's own, default 1.
    - ``extends`` is kept on the result as lineage.

    Raises:
        CharacterSetError: an unknown parent, a set extending itself, a set
            that extends nothing but is incomplete, or a result that is not a
            valid CharacterSet.
    """
    set_id = declaration.get("id")
    parent: Mapping[str, Any] | None = None
    parent_id = declaration.get("extends")
    where = f"character set {set_id!r}"
    if parent_id is None:
        errors = validate_character_set(dict(declaration), where)
        if errors:
            raise CharacterSetError(f'Character set "{set_id}" is invalid: {"; ".join(errors)}')
    else:
        found = next((k for k in known if k.get("id") == parent_id), None)
        if found is None:
            found = builtin_character_sets().get(parent_id)
        if found is None:
            raise CharacterSetError(f'Character set "{set_id}" extends unknown set "{parent_id}".')
        if found.get("id") == set_id:
            raise CharacterSetError(f'Character set "{set_id}" extends itself.')
        parent = found

    def pick(name: str, default: Any = None) -> Any:
        if name in declaration:
            return copy.deepcopy(declaration[name])
        if parent is not None and name in parent:
            return copy.deepcopy(parent[name])
        return default

    result: dict[str, Any] = {
        "id": set_id,
        "label": pick("label", set_id),
        "version": declaration.get("version", 1),
        "chars": pick("chars", []),
        "tiles": pick("tiles", False),
        "icons": pick("icons", []),
        "mixedCase": pick("mixedCase", False),
        "colorSpans": pick("colorSpans", False),
        "blockSpans": pick("blockSpans", False),
    }
    if parent_id is not None:
        result["extends"] = parent_id
    for optional in ("code62Glyph", "font", "glyphs"):
        value = pick(optional)
        if value is not None:
            result[optional] = value
    # Checked as a COMPLETE set: without the lineage, the schema's
    # "extends nothing => complete" branch applies.
    whole = {k: v for k, v in result.items() if k != "extends"}
    errors = validate_character_set(whole, where)
    if errors:
        raise CharacterSetError(f'Character set "{set_id}" is invalid: {"; ".join(errors)}')
    return result
