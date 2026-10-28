"""The manifest ``output`` block: what an output plugin declares about its device.

An output plugin (``plugin_type: "output"``) carries one ``output`` block::

    "output": {
      "output_api": 1,
      "device_models": [ <DeviceModel> | "<built-in model id>" ]
                       | {"$ref": "output/device-models.json"},
      "character_set": <CharacterSet> | {"$ref": "output/character-set.json"},
      "delivery": "push" | "pull",
      "min_interval_ms": 0,
      "read_back": {"supported": false, "cost": "cheap", "suggested_interval_s": 30},
      "native_transitions": ["column", ...],
      "write_timeout_ms": 30000,
      "settings_schema": { <JSON Schema for the board's output_config> },
      "actions": [ {"id", "label", "description"?, "input_schema"?, "result_fields"?} ]
    }

- ``output_api`` is the contract major the plugin was written against. This
  core supports :data:`SUPPORTED_OUTPUT_API`; anything else is refused at
  load (fail closed). (The three-point gate and the seed fallback are a
  later layer.)
- ``device_models`` and ``character_set`` are FiestaUI's open vocabulary
  (plan D15 rev 7), validated against its vendored JSON Schemas
  (:mod:`src.outputs.fiestaui`). A ``$ref`` names a JSON file inside the
  plugin's own directory, which must also be listed in the manifest's
  ``data_files``. A built-in model id is recognised by name; an unknown one
  is an error — never coerced to a Vestaboard.
- The declared ``character_set`` is materialised at load (plan D17, by
  :func:`src.led.charsets.materialize_character_set`) and is the output's
  character set: it wins over the models' ``charset``.
- ``delivery``, ``min_interval_ms``, ``read_back`` and ``native_transitions``
  are transport facts FiestaUI does not model; core decides by them.
- ``write_timeout_ms`` lowers how long core waits for one write before it
  fails and cancels it (:mod:`src.outputs.breaker`); it can never raise the
  default.
- ``settings_schema`` describes each board's ``output_config`` with the
  same JSON-schema vocabulary as a plugin's settings. A property marked
  ``"secret": true`` (or ``"ui:widget": "password"``) is masked on the way
  out of the API and restored on the way back (:mod:`src.outputs.output_config`).

- ``actions`` are the buttons of the board settings screen (plan D13). The
  ids ``test_connection``, ``discover``, ``identify`` and
  ``detect_geometry`` map to the plugin's hooks of those names; any other id
  is a custom action, run by the plugin's ``action_<id>(inputs)`` method (or
  its ``run_action`` dispatch hook). ``input_schema`` describes inputs that
  are not config fields (a pairing token, a tile position);
  ``result_fields`` declares what a result fills (``{"secret": true,
  "fills": "<settings field>"}``).
- **The UI vocabulary is versioned with** ``output_api``: a
  ``settings_schema`` or ``input_schema`` may use only the widgets of the
  declared major (:data:`OUTPUT_UI_WIDGETS`). Unlike a data plugin's unknown
  widget (a warning), an output's is an error: a board's setup screen that
  cannot render is a board that cannot be set up.

Validation runs twice: :func:`parse_output_block` with no directory checks
the shape and every inline object (``validate_manifest``); with the plugin's
directory it also loads and checks each ``$ref`` (``load_manifest``).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.fiestaui import builtin_device_models
from src.led.charsets import CharacterSetError, materialize_character_set

from .fiestaui import validate_character_set, validate_device_model
from .hooks import OutputActionSpec, ReadBack, ResultFieldSpec
from .registry import OutputCapabilities
from .transitions import NATIVE_STRATEGIES

#: The ``output_api`` majors this core implements (inclusive).
SUPPORTED_OUTPUT_API: tuple[int, int] = (1, 1)

_DELIVERIES = ("push", "pull")
_READ_BACK_COSTS = ("cheap", "network")
_KNOWN_KEYS = frozenset(
    {
        "output_api",
        "device_models",
        "character_set",
        "delivery",
        "min_interval_ms",
        "read_back",
        "native_transitions",
        "settings_schema",
        "write_timeout_ms",
        "actions",
    }
)

#: The settings widgets an output plugin may use, per ``output_api`` major.
#: A new widget lands with a new major, so a plugin that needs it is refused
#: by a core that cannot render it (fail closed, like the API gate itself).
OUTPUT_UI_WIDGETS: dict[int, frozenset[str]] = {
    1: frozenset(
        {
            "datetime",
            "device-picker",
            "mode-cards",
            "password",
            "remote-options",
            "textarea",
            "tile-grid",
            "timezone",
        }
    ),
}

_ACTION_KEYS = frozenset({"id", "label", "description", "input_schema", "result_fields", "visible_when", "auto_apply"})
_RESULT_FIELD_KEYS = frozenset({"secret", "fills"})
_ACTION_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")

#: A read-back nobody declared: core never polls the device.
NO_READ_BACK = ReadBack(supported=False, cost="cheap", suggested_interval_s=30)


@dataclass(frozen=True)
class OutputManifest:
    """A parsed, validated ``output`` block."""

    output_api: int
    #: Each a FiestaUI DeviceModel object, or a built-in model id.
    device_models: tuple[Any, ...]
    #: The materialised character set the plugin declares, or ``None`` (the
    #: models' ``charset`` applies).
    character_set: dict | None
    delivery: str
    min_interval_ms: int
    read_back: ReadBack
    native_transitions: frozenset[str]
    settings_schema: dict = field(default_factory=dict)
    #: The output's write budget when it lowers the default; None = default.
    write_timeout_ms: int | None = None
    #: The board settings screen's actions, in declared order.
    actions: tuple[OutputActionSpec, ...] = ()

    @property
    def device_model_ids(self) -> tuple[str, ...]:
        return tuple(m if isinstance(m, str) else m["id"] for m in self.device_models)

    def model(self, index: int = 0) -> Mapping[str, Any]:
        """The *index*-th device model as an object (a built-in id resolved)."""
        model = self.device_models[index]
        return builtin_device_models()[model] if isinstance(model, str) else model

    @property
    def capabilities(self) -> OutputCapabilities:
        """What core may assume about every board this output drives.

        Technology and animation come from the first device model (the
        plugin's default); the transport facts from the block itself.
        """
        first = self.model(0)
        charset = self.character_set["id"] if self.character_set is not None else first.get("charset")
        return OutputCapabilities(
            technology=first["technology"],
            delivery=self.delivery,
            animation=first["animation"]["delivery"],
            native_transitions=self.native_transitions,
            min_interval_ms=self.min_interval_ms,
            read_back=self.read_back,
            device_models=self.device_model_ids,
            charset=charset if isinstance(charset, str) else charset.get("id"),
            max_frames=first["animation"].get("maxFrames"),
            write_timeout_ms=self.write_timeout_ms,
        )


class _Unresolved:
    """A ``$ref`` that was well-formed but not loaded (no directory given)."""


_UNRESOLVED = _Unresolved()


def _ref_target(value: Any) -> str | None:
    if isinstance(value, dict) and set(value) == {"$ref"} and isinstance(value["$ref"], str):
        return value["$ref"]
    return None


def _load_ref(path: str, where: str, base_dir: Path | None, data_files: list[str], errors: list[str]) -> Any:
    """Load a ``$ref``'d JSON file from the plugin directory, or record why not."""
    from src.plugins.manifest import parse_data_files

    normalised = parse_data_files([path])
    if normalised != [path.strip()]:
        errors.append(f"{where}.$ref must be a plain relative path inside the plugin, got {path!r}")
        return None
    if path.strip() not in data_files:
        errors.append(f"{where}.$ref {path!r} must also be listed in data_files")
        return None
    if base_dir is None:
        return _UNRESOLVED
    root = base_dir.resolve()
    target = (root / path.strip()).resolve()
    if root not in target.parents:
        errors.append(f"{where}.$ref {path!r} resolves outside the plugin directory")
        return None
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"{where}.$ref {path!r}: file not found")
    except (OSError, ValueError) as exc:
        errors.append(f"{where}.$ref {path!r}: not readable JSON ({exc})")
    return None


def _check_device_models(raw: Any, errors: list[str]) -> list[Any]:
    if not isinstance(raw, list) or not raw:
        errors.append("output.device_models must be a non-empty array (or a $ref to one)")
        return []
    models: list[Any] = []
    for i, model in enumerate(raw):
        where = f"output.device_models[{i}]"
        if isinstance(model, str):
            if model not in builtin_device_models():
                errors.append(f"{where}: unknown built-in device model id {model!r}")
                continue
        else:
            found = validate_device_model(model, where)
            if found:
                errors.extend(found)
                continue
        models.append(model)
    return models


def _check_write_timeout(block: Mapping[str, Any], errors: list[str]) -> int | None:
    from .breaker import DEFAULT_WRITE_TIMEOUT_MS

    value = block.get("write_timeout_ms")
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= DEFAULT_WRITE_TIMEOUT_MS:
        errors.append(
            f"output.write_timeout_ms must be an integer from 1 to {DEFAULT_WRITE_TIMEOUT_MS} "
            "(it may only lower the default)"
        )
        return None
    return value


def _check_transport(block: Mapping[str, Any], errors: list[str]) -> tuple[str, int, ReadBack, frozenset[str]]:
    delivery = block.get("delivery", "push")
    if delivery not in _DELIVERIES:
        errors.append(f"output.delivery must be one of {list(_DELIVERIES)}, got {delivery!r}")

    min_interval_ms = block.get("min_interval_ms", 0)
    if not isinstance(min_interval_ms, int) or isinstance(min_interval_ms, bool) or min_interval_ms < 0:
        errors.append("output.min_interval_ms must be a non-negative integer")
        min_interval_ms = 0

    read_back = NO_READ_BACK
    raw_rb = block.get("read_back")
    if raw_rb is not None:
        if not isinstance(raw_rb, dict) or set(raw_rb) - {"supported", "cost", "suggested_interval_s"}:
            errors.append("output.read_back must be an object of supported, cost, suggested_interval_s")
        else:
            supported = raw_rb.get("supported", False)
            cost = raw_rb.get("cost", "cheap")
            interval = raw_rb.get("suggested_interval_s", 30)
            if not isinstance(supported, bool):
                errors.append("output.read_back.supported must be a boolean")
            if cost not in _READ_BACK_COSTS:
                errors.append(f"output.read_back.cost must be one of {list(_READ_BACK_COSTS)}")
            if not isinstance(interval, int) or isinstance(interval, bool) or interval < 1:
                errors.append("output.read_back.suggested_interval_s must be a positive integer")
            else:
                read_back = ReadBack(supported=bool(supported), cost=cost, suggested_interval_s=interval)

    native = block.get("native_transitions", [])
    natives: frozenset[str] = frozenset()
    if not isinstance(native, list) or not all(isinstance(n, str) for n in native):
        errors.append("output.native_transitions must be an array of strategy names")
    else:
        unknown = sorted(set(native) - NATIVE_STRATEGIES)
        if unknown:
            errors.append(f"output.native_transitions: unknown strategies {unknown}")
        natives = frozenset(native)
    return delivery, min_interval_ms, read_back, natives


def _widget_errors(schema: Mapping[str, Any], where: str, api: Any) -> list[str]:
    from src.plugins.manifest import _iter_settings_fields

    allowed = OUTPUT_UI_WIDGETS.get(api) if isinstance(api, int) else None
    if allowed is None:
        return []
    return [
        f"{where}.{path}: ui:widget {prop['ui:widget']!r} is not in output_api {api}'s vocabulary"
        for path, prop, _siblings in _iter_settings_fields(dict(schema))
        if "ui:widget" in prop and prop["ui:widget"] not in allowed
    ]


def _parse_result_fields(raw: Any, where: str, settings: Mapping[str, Any], errors: list[str]) -> dict:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        errors.append(f"{where}.result_fields must be an object of field name -> {{secret, fills}}")
        return {}
    fields: dict[str, ResultFieldSpec] = {}
    root = settings.get("properties") or {}
    for name, spec in raw.items():
        here = f"{where}.result_fields.{name}"
        if not isinstance(spec, dict):
            errors.append(f"{here} must be an object")
            continue
        for key in sorted(set(spec) - _RESULT_FIELD_KEYS):
            errors.append(f"{here}: unknown key '{key}'")
        secret = spec.get("secret", False)
        fills = spec.get("fills")
        if not isinstance(secret, bool):
            errors.append(f"{here}.secret must be a boolean")
        if fills is not None and (not isinstance(fills, str) or fills not in root):
            errors.append(f"{here}.fills must name a settings_schema property, got {fills!r}")
        fields[name] = ResultFieldSpec(secret=secret is True, fills=fills if isinstance(fills, str) else None)
    return fields


def _parse_input_schema(raw: Any, where: str, api: Any, errors: list[str]) -> dict | None:
    from src.plugins.manifest import validate_settings_schema_ui

    if raw is None:
        return None
    if not isinstance(raw, dict) or raw.get("type", "object") != "object":
        errors.append(f"{where}.input_schema must be an object schema")
        return None
    errors.extend(e.replace("settings_schema", f"{where}.input_schema", 1) for e in validate_settings_schema_ui(raw))
    errors.extend(_widget_errors(raw, f"{where}.input_schema", api))
    return raw


def _parse_actions(raw: Any, settings: Mapping[str, Any], api: Any, errors: list[str]) -> tuple[OutputActionSpec, ...]:
    from src.plugins.settings_ui import condition_errors

    if raw is None:
        return ()
    if not isinstance(raw, list):
        errors.append("output.actions must be an array")
        return ()
    actions: list[OutputActionSpec] = []
    seen: set[str] = set()
    for i, entry in enumerate(raw):
        where = f"output.actions[{i}]"
        if not isinstance(entry, dict):
            errors.append(f"{where} must be an object")
            continue
        for key in sorted(set(entry) - _ACTION_KEYS):
            errors.append(f"{where}: unknown key '{key}'")
        action_id = entry.get("id")
        if not isinstance(action_id, str) or not _ACTION_ID_RE.match(action_id):
            errors.append(f"{where}.id must match {_ACTION_ID_RE.pattern}")
            continue
        if action_id in seen:
            errors.append(f"{where}: duplicate action id '{action_id}'")
            continue
        seen.add(action_id)
        label = entry.get("label")
        if not isinstance(label, str) or not label.strip():
            errors.append(f"{where}.label must be a non-empty string")
        description = entry.get("description", "")
        if not isinstance(description, str):
            errors.append(f"{where}.description must be a string")
            description = ""
        visible_when = entry.get("visible_when")
        if visible_when is not None:
            problems = condition_errors(visible_when, settings.get("properties") or {})
            errors.extend(f"{where}.visible_when {problem}" for problem in problems)
            if problems:
                visible_when = None
        auto_apply = entry.get("auto_apply", False)
        if not isinstance(auto_apply, bool):
            errors.append(f"{where}.auto_apply must be a boolean")
            auto_apply = False
        actions.append(
            OutputActionSpec(
                id=action_id,
                label=label if isinstance(label, str) else action_id,
                description=description,
                input_schema=_parse_input_schema(entry.get("input_schema"), where, api, errors),
                result_fields=_parse_result_fields(entry.get("result_fields"), where, settings, errors),
                visible_when=visible_when,
                auto_apply=auto_apply,
            )
        )
    return tuple(actions)


def parse_output_block(
    block: Any, *, base_dir: Path | None, data_files: list[str]
) -> tuple[OutputManifest | None, list[str]]:
    """Validate an ``output`` block; with *base_dir*, also resolve its ``$ref`` files.

    Returns ``(manifest, [])`` when valid and fully resolved, ``(None, [])``
    when valid but a ``$ref`` was left unresolved (no *base_dir*), and
    ``(None, errors)`` otherwise.
    """
    from src.plugins.manifest import validate_settings_schema_ui
    from src.plugins.settings_ui import device_picker_actions, tile_grid_item_actions

    errors: list[str] = []
    if not isinstance(block, dict):
        return None, ["output must be an object"]
    for key in sorted(set(block) - _KNOWN_KEYS):
        errors.append(f"output.{key}: not an output block field")

    api = block.get("output_api")
    low, high = SUPPORTED_OUTPUT_API
    if not isinstance(api, int) or isinstance(api, bool):
        errors.append("output.output_api is required: the integer contract major the plugin targets")
    elif not low <= api <= high:
        errors.append(
            f"output.output_api {api} is not supported by this FiestaBoard (supports {low}"
            + (f"-{high}" if high != low else "")
            + "); update FiestaBoard or install a compatible version of the plugin"
        )

    unresolved = False
    raw_models = block.get("device_models")
    ref = _ref_target(raw_models)
    if ref is not None:
        raw_models = _load_ref(ref, "output.device_models", base_dir, data_files, errors)
    models: list[Any] = []
    if raw_models is _UNRESOLVED:
        unresolved = True
    elif raw_models is not None or ref is None:
        models = _check_device_models(raw_models, errors)

    character_set = None
    raw_set = block.get("character_set")
    ref = _ref_target(raw_set)
    if ref is not None:
        raw_set = _load_ref(ref, "output.character_set", base_dir, data_files, errors)
    if raw_set is _UNRESOLVED:
        unresolved = True
    elif raw_set is not None:
        found = validate_character_set(raw_set, "output.character_set")
        if found:
            errors.extend(found)
        else:
            try:
                character_set = materialize_character_set(raw_set)
            except CharacterSetError as exc:
                errors.append(f"output.character_set: {exc}")

    delivery, min_interval_ms, read_back, natives = _check_transport(block, errors)
    write_timeout_ms = _check_write_timeout(block, errors)

    settings_schema = block.get("settings_schema", {})
    if not isinstance(settings_schema, dict):
        errors.append("output.settings_schema must be an object")
        settings_schema = {}
    else:
        errors.extend(f"output.settings_schema: {e}" for e in validate_settings_schema_ui(settings_schema))
        errors.extend(_widget_errors(settings_schema, "output.settings_schema", api))

    actions = _parse_actions(block.get("actions"), settings_schema, api, errors)
    declared = {a.id for a in actions}
    for path, action in device_picker_actions(settings_schema):
        if action not in declared:
            errors.append(f"output.settings_schema.{path}: device-picker action '{action}' is not declared in actions")
    for path, action in tile_grid_item_actions(settings_schema):
        if action not in declared:
            errors.append(f"output.settings_schema.{path}: tile-grid item action '{action}' is not declared in actions")

    if errors:
        return None, errors
    if unresolved:
        return None, []
    return (
        OutputManifest(
            output_api=api,
            device_models=tuple(models),
            character_set=character_set,
            delivery=delivery,
            min_interval_ms=min_interval_ms,
            read_back=read_back,
            native_transitions=natives,
            settings_schema=settings_schema,
            write_timeout_ms=write_timeout_ms,
            actions=actions,
        ),
        [],
    )
