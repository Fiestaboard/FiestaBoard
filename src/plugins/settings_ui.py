"""The settings-form UI grammar beyond plain JSON Schema (plan D13).

Device setup needs three things a flat form lacks, so the ``settings_schema``
vocabulary grows by exactly these, all owned by core (no plugin JS):

``ui:visible_when`` (on a property)
    Show the field only when a condition over its **sibling** values holds.
    One tiny grammar, evaluated identically here (Python validation of a
    board's ``output_config``) and in the web form
    (``web/src/lib/visible-when.ts``); ``web/src/lib/visible-when.cases.json``
    holds the vectors both sides run::

        Condition := { "<field>": <scalar> }            field equals the scalar
                   | { "<field>": [<scalar>, ...] }     field is one of them
                   | { "<f1>": ..., "<f2>": ... }       every pair holds (AND)
                   | { "not": Condition }               negation ("not" alone)
                   | { "any": [Condition, ...] }        at least one holds ("any" alone)

    A scalar is a string, number, boolean or null. Equality is JSON equality
    with no coercion: ``true`` is not ``1``, ``"1"`` is not ``1``. A field
    absent from the values reads as its schema ``default`` when one is
    declared, else ``null``; an explicit ``null`` stays ``null``. A malformed
    condition evaluates to *visible* (fail open: a field is never hidden by a
    typo) — and is a manifest error, so it never ships.

    A hidden field is not validated: :func:`strip_hidden` drops its value and
    its ``required`` entry before JSON-Schema validation. Its stored value is
    kept (switching back restores it).

``ui:sections`` (on the schema root)
    ``[{"id", "title", "description"?, "fields": [...], "collapsible"?, "collapsed"?}]``
    groups root properties; a property belongs to at most one section, and
    properties in none render first, in schema order.

Core widgets (``ui:widget``), a **closed** set — a plugin cannot add one:

``mode-cards``
    A string ``enum`` rendered as a group of selectable cards (Vestaboard's
    local / cloud choice). ``ui:options.cards`` optionally gives each value
    a ``title`` and ``description``.
``tile-grid``
    An array of objects with integer ``row`` / ``col`` (note-array tile
    assignment). ``ui:options.rows_field`` / ``cols_field`` name the integer
    root properties that size the grid.
``device-picker``
    A string field filled from a ``discover`` action's devices.
    ``ui:options.action`` names the action (default ``discover``);
    ``value_key`` the device key written (default ``ip``); ``label_key`` the
    one shown (default ``hostname``).

The vocabulary an output plugin may use is versioned with ``output_api``
(:data:`src.outputs.output_manifest.OUTPUT_UI_WIDGETS`).
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

MODE_CARDS_WIDGET = "mode-cards"
TILE_GRID_WIDGET = "tile-grid"
DEVICE_PICKER_WIDGET = "device-picker"

#: ``ui:options`` vocabulary per core widget.
MODE_CARDS_UI_OPTIONS_KEYS = frozenset({"cards"})
TILE_GRID_UI_OPTIONS_KEYS = frozenset({"rows_field", "cols_field"})
DEVICE_PICKER_UI_OPTIONS_KEYS = frozenset({"action", "value_key", "label_key"})

VISIBLE_WHEN = "ui:visible_when"
SECTIONS = "ui:sections"

_SECTION_KEYS = frozenset({"id", "title", "description", "fields", "collapsible", "collapsed"})
_COMBINATORS = ("not", "any")


# --- evaluation --------------------------------------------------------------------------------


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, bool, int, float))


def _json_equal(actual: Any, expected: Any) -> bool:
    """JSON equality of a value with an expected scalar, no coercion."""
    if not _is_scalar(actual):
        return False
    if isinstance(actual, bool) or isinstance(expected, bool):
        return isinstance(actual, bool) and isinstance(expected, bool) and actual is expected
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return actual == expected
    return type(actual) is type(expected) and actual == expected


def _value_of(field: str, values: Mapping[str, Any], properties: Mapping[str, Any]) -> Any:
    if field in values:
        return values[field]
    prop = properties.get(field)
    return prop.get("default") if isinstance(prop, Mapping) else None


def _evaluate(cond: Any, values: Mapping[str, Any], properties: Mapping[str, Any]) -> bool | None:
    """True / False, or ``None`` when *cond* is malformed."""
    if not isinstance(cond, Mapping) or not cond:
        return None
    if "not" in cond or "any" in cond:
        if len(cond) != 1:
            return None
        if "not" in cond:
            inner = _evaluate(cond["not"], values, properties)
            return None if inner is None else not inner
        branches = cond["any"]
        if not isinstance(branches, list) or not branches:
            return None
        results = [_evaluate(b, values, properties) for b in branches]
        return None if any(r is None for r in results) else any(results)
    for field, expected in cond.items():
        actual = _value_of(field, values, properties)
        if isinstance(expected, list):
            if not all(_is_scalar(e) for e in expected):
                return None
            if not any(_json_equal(actual, e) for e in expected):
                return False
        elif _is_scalar(expected):
            if not _json_equal(actual, expected):
                return False
        else:
            return None
    return True


def is_visible(cond: Any, values: Mapping[str, Any] | None, properties: Mapping[str, Any] | None = None) -> bool:
    """Whether a field with ``ui:visible_when`` *cond* shows, given its
    object's *values* and property schemas (for defaults). Malformed → True."""
    result = _evaluate(cond, values or {}, properties or {})
    return True if result is None else result


def strip_hidden(values: Any, schema: Mapping[str, Any]) -> tuple[Any, dict[str, Any]]:
    """``(values, schema)`` with every hidden field removed, recursively.

    A hidden property's value is dropped and its name removed from
    ``required``, so JSON-Schema validation of what remains checks only what
    the user can see. Copies; the inputs are untouched.
    """
    schema_out: dict[str, Any] = copy.deepcopy(dict(schema)) if isinstance(schema, Mapping) else {}
    if isinstance(values, list):
        items = schema_out.get("items")
        if isinstance(items, Mapping):
            stripped = [strip_hidden(v, items) for v in values]
            return [v for v, _ in stripped], schema_out
        return list(values), schema_out
    if not isinstance(values, Mapping):
        return values, schema_out
    properties = schema_out.get("properties")
    if not isinstance(properties, dict):
        return dict(values), schema_out
    hidden = {
        name
        for name, prop in properties.items()
        if isinstance(prop, Mapping) and VISIBLE_WHEN in prop and not is_visible(prop[VISIBLE_WHEN], values, properties)
    }
    out: dict[str, Any] = {}
    for key, value in values.items():
        if key in hidden:
            continue
        prop = properties.get(key)
        out[key] = strip_hidden(value, prop)[0] if isinstance(prop, Mapping) else value
    required = schema_out.get("required")
    if isinstance(required, list):
        schema_out["required"] = [name for name in required if name not in hidden]
    return out, schema_out


# --- validation ----------------------------------------------------------------------------------


def condition_errors(cond: Any, fields: Mapping[str, Any]) -> list[str]:
    """What is wrong with a ``ui:visible_when`` condition over *fields* (its
    object's properties); empty when it is well formed."""
    if not isinstance(cond, Mapping):
        return ["must be an object"]
    if not cond:
        return ["must name at least one field, or be a 'not' / 'any'"]
    for combinator in _COMBINATORS:
        if combinator in cond:
            if len(cond) != 1:
                return [f"'{combinator}' must be the only key"]
            if combinator == "not":
                return condition_errors(cond["not"], fields)
            branches = cond["any"]
            if not isinstance(branches, list) or not branches:
                return ["'any' must be a non-empty array of conditions"]
            return [e for branch in branches for e in condition_errors(branch, fields)]
    errors: list[str] = []
    for field, expected in cond.items():
        if field not in fields:
            errors.append(f"references unknown property '{field}'")
            continue
        candidates = expected if isinstance(expected, list) else [expected]
        if (isinstance(expected, list) and not expected) or not all(_is_scalar(c) for c in candidates):
            errors.append(f"{field}: expected a string, number, boolean or null, or an array of them")
    return errors


def sections_errors(sections: Any, properties: Mapping[str, Any]) -> list[str]:
    """What is wrong with a root ``ui:sections`` declaration."""
    where = f"settings_schema.{SECTIONS}"
    if not isinstance(sections, list):
        return [f"{where} must be an array"]
    errors: list[str] = []
    ids: set[str] = set()
    owner: dict[str, str] = {}
    for i, section in enumerate(sections):
        here = f"{where}[{i}]"
        if not isinstance(section, Mapping):
            errors.append(f"{here} must be an object")
            continue
        for key in sorted(set(section) - _SECTION_KEYS):
            errors.append(f"{here}: unknown key '{key}'")
        section_id = section.get("id")
        if not isinstance(section_id, str) or not section_id:
            errors.append(f"{here}: id must be a non-empty string")
        elif section_id in ids:
            errors.append(f"{here}: duplicate id '{section_id}'")
        else:
            ids.add(section_id)
        title = section.get("title")
        if not isinstance(title, str) or not title.strip():
            errors.append(f"{here}: title must be a non-empty string")
        for flag in ("collapsible", "collapsed"):
            if flag in section and not isinstance(section[flag], bool):
                errors.append(f"{here}: {flag} must be a boolean")
        if section.get("collapsed") and not section.get("collapsible"):
            errors.append(f"{here}: collapsed requires collapsible")
        fields = section.get("fields")
        if not isinstance(fields, list) or not all(isinstance(f, str) for f in fields):
            errors.append(f"{here}: fields must be an array of property names")
            continue
        for name in fields:
            if name in owner:
                errors.append(f"{here}: field '{name}' is already in section '{owner[name]}'")
            elif name not in properties:
                errors.append(f"{here}: unknown property '{name}'")
            else:
                owner[name] = section_id if isinstance(section_id, str) else str(i)
    return errors


def _int_property(properties: Mapping[str, Any], name: Any) -> bool:
    prop = properties.get(name) if isinstance(name, str) else None
    return isinstance(prop, Mapping) and prop.get("type") == "integer"


def widget_errors(
    field_path: str, prop: Mapping[str, Any], siblings: Mapping[str, Any], root: Mapping[str, Any]
) -> list[str]:
    """Malformed values for the core widgets' own requirements."""
    widget = prop.get("ui:widget")
    where = f"settings_schema.{field_path}"
    options = prop.get("ui:options", {})
    if not isinstance(options, Mapping):
        return [f"{where}: ui:options must be an object"]
    errors: list[str] = []
    if widget == MODE_CARDS_WIDGET:
        enum = prop.get("enum")
        if not isinstance(enum, list) or not enum:
            return [f"{where}: ui:widget '{MODE_CARDS_WIDGET}' requires an enum"]
        cards = options.get("cards", [])
        if not isinstance(cards, list):
            return [f"{where}: ui:options.cards must be an array"]
        for i, card in enumerate(cards):
            if not isinstance(card, Mapping):
                errors.append(f"{where}: ui:options.cards[{i}] must be an object")
            elif card.get("value") not in enum:
                errors.append(
                    f"{where}: ui:options.cards[{i}].value {card.get('value')!r} is not one of the enum values"
                )
    elif widget == TILE_GRID_WIDGET:
        items = prop.get("items")
        item_props = items.get("properties") if isinstance(items, Mapping) else None
        if prop.get("type") != "array" or not isinstance(item_props, Mapping):
            return [f"{where}: ui:widget '{TILE_GRID_WIDGET}' requires an array of objects"]
        if not (_int_property(item_props, "row") and _int_property(item_props, "col")):
            errors.append(f"{where}: ui:widget '{TILE_GRID_WIDGET}' items need integer 'row' and 'col' properties")
        root_props = root.get("properties") or {}
        for key in ("rows_field", "cols_field"):
            if not _int_property(root_props, options.get(key)):
                errors.append(f"{where}: ui:options.{key} must name an integer property")
    elif widget == DEVICE_PICKER_WIDGET:
        if prop.get("type") != "string":
            errors.append(f"{where}: ui:widget '{DEVICE_PICKER_WIDGET}' requires type 'string'")
        for key in ("action", "value_key", "label_key"):
            if key in options and (not isinstance(options[key], str) or not options[key]):
                errors.append(f"{where}: ui:options.{key} must be a non-empty string")
    return errors


def device_picker_actions(schema: Mapping[str, Any]) -> list[tuple[str, str]]:
    """``(field_path, action id)`` for every ``device-picker`` in *schema*."""
    from .manifest import _iter_settings_fields

    found = []
    for field_path, prop, _siblings in _iter_settings_fields(dict(schema)):
        if prop.get("ui:widget") == DEVICE_PICKER_WIDGET:
            options = prop.get("ui:options")
            action = options.get("action", "discover") if isinstance(options, Mapping) else "discover"
            found.append((field_path, action))
    return found
