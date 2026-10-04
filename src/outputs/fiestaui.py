"""FiestaUI's device vocabulary, as an output plugin's manifest is checked against it.

FiestaUI is the reference for what a display *is* (plan D15): a
**DeviceModel** (technology, geometry, colour, character set, animation,
appearance) and a **CharacterSet** (what the board can draw). An output
plugin declares its models and, optionally, its own character set in the
manifest ``output`` block; this module validates both against FiestaUI's
JSON Schemas.

The schemas, like the rest of FiestaUI's data (built-in character sets,
device models, LED fonts), are vendored once in :mod:`src.fiestaui`, with
their provenance and sha256. They resolve each other by ``$id`` through a
local ``referencing`` registry, never over the network.

Making a declared character set whole (plan D17) is
:func:`src.led.charsets.materialize_character_set`, core's one materialiser.
"""

from __future__ import annotations

from functools import cache
from typing import Any

from src.fiestaui import CHARACTER_SET_SCHEMA_FILE, DEVICE_MODEL_SCHEMA_FILE, read


@cache
def _validators() -> dict[str, Any]:
    """Draft-7 validators, resolving ``$ref`` by ``$id`` from the vendored files only."""
    from jsonschema import Draft7Validator
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT7

    schemas = {name: read(name) for name in (DEVICE_MODEL_SCHEMA_FILE, CHARACTER_SET_SCHEMA_FILE)}
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
    """Errors for a CharacterSet as a manifest may declare it, against FiestaUI's schema.

    The schema itself tells a partial declaration from a whole one: a set
    that ``extends`` another needs only ``id``; one that extends nothing
    must be complete. This is the published-schema check of the manifest
    document; :func:`src.led.charsets.materialize_character_set` then applies
    FiestaUI's stricter ``validateCharacterSet`` before and after inheriting.
    """
    return _errors(_validators()[CHARACTER_SET_SCHEMA_FILE], charset, where)
