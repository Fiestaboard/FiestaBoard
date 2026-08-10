"""Plugin manifest validation and parsing.

The manifest.json file is the heart of each plugin, defining:
- Plugin metadata (id, name, version, author, etc.)
- Settings schema (JSON Schema for configuration UI)
- Environment variables (required/optional)
- Template variables schema (simple, arrays, nested)
- Max lengths for template validation
- Color rules schema
- Board previews (teaser + previews) that let docs render the plugin
  without a screenshot -- see :mod:`src.plugins.previews`
"""

import copy
import json
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .previews import BoardPreview, parse_previews, validate_previews, validate_teaser

logger = logging.getLogger(__name__)


# Canonical settings-schema entry auto-injected for any plugin whose manifest
# declares ``supports_triggers: true``.  Plugin authors can still override the
# field by declaring their own ``trigger_page_id`` property — the override
# wins, so they keep full control of label/description/default behaviour.
TRIGGER_PAGE_ID_PROPERTY: dict[str, Any] = {
    "type": "string",
    "title": "Trigger Page",
    "description": (
        "Page rendered when this plugin fires a trigger. The trigger's "
        "data is exposed to the template as the plugin's variables."
    ),
    "ui:widget": "page-picker",
    "default": "",
}


# ``ui:widget`` value that opts a settings field into the generic remote
# options primitive: the field's choices come from the plugin's own
# ``get_options()`` implementation rather than a static ``enum``.
REMOTE_OPTIONS_WIDGET = "remote-options"

# ``options_id`` becomes a URL path segment on the options route, so keep it to
# a boring lowercase identifier.
OPTIONS_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# Every key a ``ui:options`` block may carry. Anything else is a typo, and a
# silently-ignored typo is how a picker ships without ever calling the plugin.
UI_OPTIONS_KEYS = frozenset({"options_id", "depends_on", "multiple", "cache_seconds"})

# How long the UI may reuse a fetched option list. Zero means "never cache";
# the ceiling is an hour, above which a stale picker outlives the dialog it
# was opened from.
MIN_OPTIONS_CACHE_SECONDS = 0
MAX_OPTIONS_CACHE_SECONDS = 3600

# ``ui:widget`` values the settings form knows how to render. An unrecognised
# value is a *warning*, never an error: several installed plugins declare
# picker widgets core never implemented, and load_manifest() returns None on
# any validation error -- rejecting them here would uninstall them in practice.
KNOWN_SETTINGS_WIDGETS = frozenset(
    {
        "datetime",
        "disney-parks-times-picker",
        "generic-data-mapping-helper",
        "page-picker",
        "password",
        REMOTE_OPTIONS_WIDGET,
        "textarea",
        "timezone",
        "wsdot-route-picker",
    }
)


def _inject_trigger_page_id(settings_schema: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *settings_schema* with the canonical ``trigger_page_id``
    field injected when the author has not declared their own.

    The on-disk manifest is never mutated; the loader uses this enriched
    schema so the configuration UI surfaces a page picker automatically for
    every plugin that declares ``supports_triggers: true``.
    """
    enriched = copy.deepcopy(settings_schema) if settings_schema else {}
    enriched.setdefault("type", "object")
    properties = enriched.setdefault("properties", {})
    if "trigger_page_id" not in properties:
        properties["trigger_page_id"] = copy.deepcopy(TRIGGER_PAGE_ID_PROPERTY)
    return enriched


# JSON Schema for validating manifest.json files
MANIFEST_SCHEMA = {
    "type": "object",
    "required": ["id", "name", "version"],
    "properties": {
        "id": {
            "type": "string",
            "pattern": "^[a-z][a-z0-9_]*$",
            "description": "Unique plugin identifier (lowercase, underscores allowed)",
        },
        "name": {"type": "string", "minLength": 1, "maxLength": 50, "description": "Human-readable plugin name"},
        "version": {
            "type": "string",
            "pattern": "^\\d+\\.\\d+\\.\\d+$",
            "description": "Semantic version (e.g., 1.0.0)",
        },
        "description": {"type": "string", "maxLength": 200, "description": "Short description of the plugin"},
        "author": {"type": "string", "description": "Plugin author or maintainer"},
        "repository": {"type": "string", "format": "uri", "description": "Source repository URL"},
        "documentation": {"type": "string", "description": "Path to documentation file (relative to plugin folder)"},
        "settings_schema": {"type": "object", "description": "JSON Schema for plugin configuration"},
        "env_vars": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string"},
                    "required": {"type": "boolean", "default": False},
                    "description": {"type": "string"},
                    "default": {"type": "string"},
                },
            },
            "description": "Environment variables used by the plugin",
        },
        "variables": {
            "type": "object",
            "properties": {
                "auto_discover": {
                    "type": "boolean",
                    "description": "Auto-expose all data keys as variables (default: true when no variables declared)",
                },
                "groups": {
                    "type": "object",
                    "additionalProperties": {"type": "object", "properties": {"label": {"type": "string"}}},
                    "description": "Named groups for organising variables in the UI",
                },
                "simple": {
                    "oneOf": [
                        {"type": "array", "items": {"type": "string"}},
                        {"type": "object", "additionalProperties": {"type": "object"}},
                    ],
                    "description": "Simple key-value variables (list or dict with metadata)",
                },
                "arrays": {
                    "type": "object",
                    "additionalProperties": {
                        "type": "object",
                        "properties": {
                            "label_field": {"type": "string"},
                            "item_fields": {"type": "array", "items": {"type": "string"}},
                            "sub_arrays": {
                                "type": "object",
                                "additionalProperties": {
                                    "type": "object",
                                    "properties": {
                                        "key_type": {"type": "string", "enum": ["index", "dynamic"]},
                                        "key_field": {"type": "string"},
                                        "item_fields": {"type": "array", "items": {"type": "string"}},
                                    },
                                },
                            },
                        },
                    },
                    "description": "Array variables with indexed access",
                },
            },
            "description": "Template variables exposed by the plugin",
        },
        "max_lengths": {
            "type": "object",
            "additionalProperties": {"type": "integer"},
            "description": "Maximum character lengths for variables",
        },
        "color_rules_schema": {"type": "object", "description": "Schema for configurable color rules"},
        "icon": {"type": "string", "description": "Icon name from Lucide icons"},
        "category": {
            "type": "string",
            "enum": ["art", "data", "transit", "weather", "entertainment", "utility", "home", "transition"],
            "description": "Plugin category for organization",
        },
        "plugin_type": {
            "type": "string",
            "enum": ["data", "transition"],
            "default": "data",
            "description": "Plugin kind. 'data' (default) returns template variables; 'transition' produces frame-by-frame board animations.",
        },
        "transition_settings": {
            "type": "object",
            "description": "Per-plugin caps and behavior flags for transition plugins (only used when plugin_type='transition').",
            "properties": {
                "interruptible": {
                    "type": "boolean",
                    "default": True,
                    "description": "When true, a new page or trigger arriving mid-transition cancels the current transition. When false, the transition runs to completion before the new state is applied.",
                },
                "min_interval_ms": {
                    "type": "integer",
                    "minimum": 0,
                    "default": 50,
                    "description": "Floor on the delay between frame sends. Protects against runaway loops and respects board API rate limits regardless of what the plugin yields.",
                },
                "max_frames": {
                    "type": "integer",
                    "minimum": 1,
                    "default": 500,
                    "description": "Hard cap on the number of frames the runner will send before aborting and snapping to the target grid.",
                },
                "max_runtime_seconds": {
                    "type": "integer",
                    "minimum": 1,
                    "default": 120,
                    "description": "Hard cap on wall-clock seconds the transition may run before the runner aborts and snaps to the target grid.",
                },
            },
        },
        "fiestaboard_version": {
            "type": "string",
            "description": "Minimum FiestaBoard version required (semver constraint, e.g. '>=2.10.0')",
        },
        "supports_triggers": {
            "type": "boolean",
            "default": False,
            "description": "Whether this plugin supports event-based triggers via check_triggers()",
        },
        "screenshots": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["src", "alt"],
                "properties": {
                    "src": {
                        "type": "string",
                        "description": "Relative path from plugin directory (e.g., docs/board-display.png)",
                    },
                    "alt": {"type": "string", "description": "Alt text for accessibility"},
                    "caption": {"type": "string", "description": "Human-readable caption"},
                    "primary": {
                        "type": "boolean",
                        "default": False,
                        "description": "Whether this is the hero image for galleries and registries",
                    },
                },
            },
            "description": "Screenshots for plugin galleries, docs, and the registry",
        },
        "demo": {
            "type": "object",
            "required": ["name", "template"],
            "properties": {
                "name": {"type": "string", "description": "Demo page name shown in the pages list"},
                "device_type": {
                    "type": "string",
                    "enum": ["flagship", "note"],
                    "default": "flagship",
                    "description": "Target device type for the demo page",
                },
                "template": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Template lines with {{plugin_id.var}} placeholders",
                },
                "line_metadata": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "alignment": {"type": "string", "enum": ["left", "center", "right"]},
                            "wrap": {"type": "boolean"},
                        },
                    },
                    "description": "Per-line formatting (alignment, wrap)",
                },
                "duration_seconds": {
                    "type": "integer",
                    "default": 300,
                    "minimum": 10,
                    "description": "Rotation duration in seconds",
                },
            },
            "description": "Demo page template that showcases the plugin's features",
        },
        "teaser": {
            "type": "string",
            "description": (
                "One line of literal board text, at most 15 tiles (the Note width). "
                "Rendered as a split-flap strip on plugin directory cards. "
                "Colour markers like {66} count as one tile."
            ),
        },
        "previews": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["rows"],
                "properties": {
                    "label": {
                        "type": "string",
                        "description": "Tab label; defaults to the board shape (e.g. 'Flagship')",
                    },
                    "device_type": {
                        "type": "string",
                        "enum": ["flagship", "note", "note_array"],
                        "default": "flagship",
                        "description": "Board shape this preview is composed for",
                    },
                    "notes_wide": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 4,
                        "default": 1,
                        "description": "Notes wide (note_array only)",
                    },
                    "notes_tall": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 4,
                        "default": 1,
                        "description": "Notes tall (note_array only)",
                    },
                    "rows": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Literal board rows. May be shorter than the device's row "
                            "count (padded with blanks) but never longer."
                        ),
                    },
                },
            },
            "description": "Literal board previews rendered on the plugin detail page",
        },
    },
}


@dataclass
class VariableMetadata:
    """Rich metadata for a single variable.

    All fields are optional -- when omitted, sensible defaults apply.
    This powers descriptions, type hints, grouping, and examples
    shown in the editor's variable picker.
    """

    description: str = ""
    type: str = "string"  # "string", "number", "boolean"
    max_length: int | None = None
    group: str = ""
    example: str = ""


@dataclass
class Screenshot:
    """A plugin screenshot entry for galleries, docs, and the registry."""

    src: str
    alt: str
    caption: str = ""
    primary: bool = False


@dataclass
class DemoPageSchema:
    """Bundled demo page template that showcases a plugin's features."""

    name: str
    template: list[str]
    device_type: str = "flagship"
    line_metadata: list[dict[str, Any]] | None = None
    duration_seconds: int = 300


@dataclass
class VariableGroupSchema:
    """A named group used to organise variables in the UI."""

    label: str = ""


@dataclass
class VariableArraySchema:
    """Schema for array-type variables."""

    name: str
    label_field: str
    item_fields: list[str]
    sub_arrays: dict[str, "VariableArraySchema"] = field(default_factory=dict)
    key_type: str = "index"  # "index" or "dynamic"
    key_field: str | None = None


@dataclass
class VariablesSchema:
    """Complete variables schema from manifest.

    Supports two formats for ``simple``:
    - **List** (legacy/beginner): ``["temperature", "humidity"]``
    - **Dict** (rich metadata):  ``{"temperature": {"description": "...", ...}}``

    When the manifest omits the ``variables`` section entirely,
    ``auto_discover`` defaults to ``True`` so that every key returned
    by ``fetch_data()`` is automatically surfaced in the editor.
    """

    simple: list[str] = field(default_factory=list)
    arrays: dict[str, VariableArraySchema] = field(default_factory=dict)
    metadata: dict[str, VariableMetadata] = field(default_factory=dict)
    groups: dict[str, VariableGroupSchema] = field(default_factory=dict)
    auto_discover: bool = True

    def get_all_variable_names(self, plugin_id: str) -> list[str]:
        """Get all variable names for template engine.

        Returns flattened list like:
        - simple_var
        - array_name (for aggregate access)
        - array_name.*.field (documented pattern)
        """
        names = []

        for var in self.simple:
            names.append(var)

        for array_name, schema in self.arrays.items():
            names.append(array_name)
            for field_name in schema.item_fields:
                names.append(f"{array_name}.*.{field_name}")

            for sub_name, sub_schema in schema.sub_arrays.items():
                names.append(f"{array_name}.*.{sub_name}")
                for sub_field in sub_schema.item_fields:
                    names.append(f"{array_name}.*.{sub_name}.*.{sub_field}")

        return names

    def get_variable_metadata(self, var_name: str) -> VariableMetadata:
        """Return metadata for *var_name*, falling back to defaults."""
        return self.metadata.get(var_name, VariableMetadata())


@dataclass
class PluginManifest:
    """Parsed and validated plugin manifest."""

    id: str
    name: str
    version: str
    description: str = ""
    author: str = "Unknown"
    repository: str = ""
    documentation: str = "README.md"
    settings_schema: dict[str, Any] = field(default_factory=dict)
    env_vars: list[dict[str, Any]] = field(default_factory=list)
    variables: VariablesSchema = field(default_factory=VariablesSchema)
    max_lengths: dict[str, int] = field(default_factory=dict)
    color_rules_schema: dict[str, Any] = field(default_factory=dict)
    icon: str = "puzzle"
    category: str = "utility"
    fiestaboard_version: str = ""
    supports_triggers: bool = False
    screenshots: list[Screenshot] = field(default_factory=list)
    demo: dict[str, DemoPageSchema] | None = None  # keyed by device_type
    teaser: str = ""
    previews: list[BoardPreview] = field(default_factory=list)
    plugin_type: str = "data"  # "data" or "transition"
    transition_settings: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PluginManifest":
        """Create PluginManifest from dictionary.

        The ``variables.simple`` field accepts two formats:
        - **List** (legacy): ``["temperature", "humidity"]``
        - **Dict** (rich):   ``{"temperature": {"description": "...", ...}}``

        When the manifest has no ``variables`` section at all,
        ``auto_discover`` defaults to ``True``.
        """
        variables_data = data.get("variables", {})

        # --- parse simple (list or dict) ---
        simple_raw = variables_data.get("simple", [])
        simple_names: list[str] = []
        var_metadata: dict[str, VariableMetadata] = {}

        if isinstance(simple_raw, list):
            simple_names = list(simple_raw)
        elif isinstance(simple_raw, dict):
            for var_name, meta_dict in simple_raw.items():
                simple_names.append(var_name)
                if isinstance(meta_dict, dict):
                    var_metadata[var_name] = VariableMetadata(
                        description=meta_dict.get("description", ""),
                        type=meta_dict.get("type", "string"),
                        max_length=meta_dict.get("max_length"),
                        group=meta_dict.get("group", ""),
                        example=meta_dict.get("example", ""),
                    )

        # --- parse groups ---
        groups_raw = variables_data.get("groups", {})
        groups: dict[str, VariableGroupSchema] = {}
        if isinstance(groups_raw, dict):
            for group_id, group_data in groups_raw.items():
                label = group_data.get("label", group_id) if isinstance(group_data, dict) else str(group_data)
                groups[group_id] = VariableGroupSchema(label=label)

        # --- auto_discover ---
        has_declared_vars = bool(simple_names) or bool(variables_data.get("arrays"))
        if "auto_discover" in variables_data:
            auto_discover = bool(variables_data["auto_discover"])
        else:
            auto_discover = not has_declared_vars

        variables = VariablesSchema(
            simple=simple_names,
            arrays={},
            metadata=var_metadata,
            groups=groups,
            auto_discover=auto_discover,
        )

        # --- parse array schemas ---
        for array_name, array_data in variables_data.get("arrays", {}).items():
            sub_arrays: dict[str, VariableArraySchema] = {}
            for sub_name, sub_data in array_data.get("sub_arrays", {}).items():
                sub_arrays[sub_name] = VariableArraySchema(
                    name=sub_name,
                    label_field=sub_data.get("label_field", ""),
                    item_fields=sub_data.get("item_fields", []),
                    key_type=sub_data.get("key_type", "index"),
                    key_field=sub_data.get("key_field"),
                )

            variables.arrays[array_name] = VariableArraySchema(
                name=array_name,
                label_field=array_data.get("label_field", ""),
                item_fields=array_data.get("item_fields", []),
                sub_arrays=sub_arrays,
            )

        # Merge per-variable max_length from metadata into top-level max_lengths
        top_max_lengths = dict(data.get("max_lengths", {}))
        for var_name, meta in var_metadata.items():
            if meta.max_length is not None and var_name not in top_max_lengths:
                top_max_lengths[var_name] = meta.max_length

        # --- parse screenshots ---
        screenshots: list[Screenshot] = []
        for entry in data.get("screenshots", []):
            if isinstance(entry, dict) and "src" in entry and "alt" in entry:
                screenshots.append(
                    Screenshot(
                        src=entry["src"],
                        alt=entry["alt"],
                        caption=entry.get("caption", ""),
                        primary=bool(entry.get("primary", False)),
                    )
                )

        # --- parse demo page schema ---
        demo: dict[str, DemoPageSchema] | None = None
        demo_raw = data.get("demo")
        if isinstance(demo_raw, dict):
            if "name" in demo_raw and "template" in demo_raw:
                # Old flat format — normalise to keyed dict
                schema = DemoPageSchema(
                    name=demo_raw["name"],
                    template=demo_raw["template"],
                    device_type=demo_raw.get("device_type", "flagship"),
                    line_metadata=demo_raw.get("line_metadata"),
                    duration_seconds=demo_raw.get("duration_seconds", 300),
                )
                demo = {schema.device_type: schema}
            else:
                # New keyed format: {"flagship": {...}, "note": {...}}
                demo = {}
                for dt, entry in demo_raw.items():
                    if isinstance(entry, dict) and "name" in entry and "template" in entry:
                        demo[dt] = DemoPageSchema(
                            name=entry["name"],
                            template=entry["template"],
                            device_type=dt,
                            line_metadata=entry.get("line_metadata"),
                            duration_seconds=entry.get("duration_seconds", 300),
                        )
                if not demo:
                    demo = None

        # Auto-inject `trigger_page_id` into the effective settings_schema
        # for any plugin that declares `supports_triggers: true`.  This frees
        # plugin authors from having to hand-roll the field while still
        # letting them override it by declaring their own property.  The
        # on-disk manifest is left untouched — only the in-memory copy used
        # by the loader (and forwarded into `raw` so the plugin instance
        # sees the same schema) is enriched.
        supports_triggers = bool(data.get("supports_triggers", False))
        settings_schema = data.get("settings_schema", {})
        if supports_triggers:
            settings_schema = _inject_trigger_page_id(settings_schema)
            raw = dict(data)
            raw["settings_schema"] = settings_schema
        else:
            raw = data

        return cls(
            id=data["id"],
            name=data["name"],
            version=data["version"],
            description=data.get("description", ""),
            author=data.get("author", "Unknown"),
            repository=data.get("repository", ""),
            documentation=data.get("documentation", "README.md"),
            settings_schema=settings_schema,
            env_vars=data.get("env_vars", []),
            variables=variables,
            max_lengths=top_max_lengths,
            color_rules_schema=data.get("color_rules_schema", {}),
            icon=data.get("icon", "puzzle"),
            category=data.get("category", "utility"),
            fiestaboard_version=data.get("fiestaboard_version", ""),
            supports_triggers=supports_triggers,
            screenshots=screenshots,
            demo=demo,
            teaser=data.get("teaser", "") if isinstance(data.get("teaser", ""), str) else "",
            previews=parse_previews(data.get("previews")),
            plugin_type=data.get("plugin_type", "data"),
            transition_settings=dict(data.get("transition_settings", {})),
            raw=raw,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        result = {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "repository": self.repository,
            "documentation": self.documentation,
            "settings_schema": self.settings_schema,
            "env_vars": self.env_vars,
            "variables": self.raw.get("variables", {}),
            "max_lengths": self.max_lengths,
            "color_rules_schema": self.color_rules_schema,
            "icon": self.icon,
            "category": self.category,
            "fiestaboard_version": self.fiestaboard_version,
            "supports_triggers": self.supports_triggers,
            "plugin_type": self.plugin_type,
            "transition_settings": self.transition_settings,
            "screenshots": [
                {
                    "src": s.src,
                    "alt": s.alt,
                    "caption": s.caption,
                    "primary": s.primary,
                }
                for s in self.screenshots
            ],
            "teaser": self.teaser,
            "previews": [
                {
                    "label": p.label,
                    "device_type": p.device_type,
                    "notes_wide": p.notes_wide,
                    "notes_tall": p.notes_tall,
                    "rows": p.rows,
                }
                for p in self.previews
            ],
        }
        # Include parsed metadata and groups so the frontend can use them
        # even when the raw variables section uses list format.
        if self.variables.metadata:
            result["variable_metadata"] = {
                name: {
                    "description": m.description,
                    "type": m.type,
                    "max_length": m.max_length,
                    "group": m.group,
                    "example": m.example,
                }
                for name, m in self.variables.metadata.items()
            }
        if self.variables.groups:
            result["variable_groups"] = {gid: {"label": g.label} for gid, g in self.variables.groups.items()}
        return result


def _iter_settings_fields(
    settings_schema: dict[str, Any],
) -> Iterator[tuple[str, dict[str, Any], dict[str, Any]]]:
    """Yield ``(dotted_path, property_schema, sibling_properties)`` for every
    field in *settings_schema*, recursing through nested ``properties`` and
    array ``items.properties``.
    """

    def _walk(properties: dict[str, Any], path: str) -> Iterator[tuple[str, dict[str, Any], dict[str, Any]]]:
        for name, prop in properties.items():
            if not isinstance(prop, dict):
                continue
            field_path = f"{path}.{name}" if path else name
            yield field_path, prop, properties

            nested = prop.get("properties")
            if isinstance(nested, dict):
                yield from _walk(nested, field_path)
            items = prop.get("items")
            if isinstance(items, dict) and isinstance(items.get("properties"), dict):
                yield from _walk(items["properties"], f"{field_path}.items")

    yield from _walk(settings_schema.get("properties") or {}, "")


def collect_options_ids(settings_schema: dict[str, Any]) -> set[str]:
    """Return every ``ui:options.options_id`` declared anywhere in *settings_schema*.

    A non-empty result means the plugin promises to answer options requests and
    therefore must implement :meth:`~src.plugins.base.PluginBase.get_options`.
    """
    ids: set[str] = set()
    for _path, prop, _siblings in _iter_settings_fields(settings_schema):
        if prop.get("ui:widget") != REMOTE_OPTIONS_WIDGET:
            continue
        ui_options = prop.get("ui:options")
        options_id = ui_options.get("options_id") if isinstance(ui_options, dict) else None
        if isinstance(options_id, str) and options_id:
            ids.add(options_id)
    return ids


def options_cache_seconds(settings_schema: dict[str, Any], options_id: str) -> int | None:
    """Return the ``ui:options.cache_seconds`` declared for *options_id*.

    ``None`` means the field did not declare one and the caller's default
    applies; ``0`` is a deliberate "never cache this". The TTL lives per
    provider because only the plugin author knows whether the catalog is a
    departure board that goes stale in seconds or a list of airports that does
    not change this decade.

    Args:
        settings_schema: The plugin's ``settings_schema`` object.
        options_id: The provider being asked about.

    Returns:
        The declared TTL in seconds, or ``None`` when unspecified.
    """
    for _path, prop, _siblings in _iter_settings_fields(settings_schema):
        if prop.get("ui:widget") != REMOTE_OPTIONS_WIDGET:
            continue
        ui_options = prop.get("ui:options")
        if not isinstance(ui_options, dict) or ui_options.get("options_id") != options_id:
            continue
        seconds = ui_options.get("cache_seconds")
        # bool is an int subclass; a `true` here is a schema bug, not a TTL.
        if isinstance(seconds, int) and not isinstance(seconds, bool):
            return seconds
        return None
    return None


def validate_settings_schema_ui(settings_schema: dict[str, Any]) -> list[str]:
    """Validate the ``ui:*`` annotations in a plugin's ``settings_schema``.

    Returns a list of hard **errors** (empty when the schema is fine). An
    unrecognised ``ui:widget`` is deliberately *not* an error -- see the module
    note on ``load_manifest`` returning ``None`` for any validation failure.

    Args:
        settings_schema: The manifest's ``settings_schema`` object.

    Returns:
        List of human-readable error strings.
    """
    errors: list[str] = []
    seen_ids: dict[str, str] = {}
    root_properties = settings_schema.get("properties") or {}

    for field_path, prop, siblings in _iter_settings_fields(settings_schema):
        widget = prop.get("ui:widget")
        if widget is not None and widget not in KNOWN_SETTINGS_WIDGETS:
            # Soft failure on purpose -- see KNOWN_SETTINGS_WIDGETS.
            logger.warning(
                "settings_schema.%s: unknown ui:widget '%s' — the settings form will fall back to a plain input",
                field_path,
                widget,
            )
        if widget != REMOTE_OPTIONS_WIDGET:
            continue

        ui_options = prop.get("ui:options") or {}
        if not isinstance(ui_options, dict):
            errors.append(f"settings_schema.{field_path}: ui:options must be an object")
            # Fall through with an empty block so the field still gets the
            # "missing options_id" error rather than two shapes of the same bug.
            ui_options = {}

        options_id = ui_options.get("options_id")
        if not options_id:
            errors.append(f"settings_schema.{field_path}: ui:widget 'remote-options' requires ui:options.options_id")
        elif not isinstance(options_id, str) or not OPTIONS_ID_RE.match(options_id):
            errors.append(
                f"settings_schema.{field_path}: ui:options.options_id '{options_id}' must match {OPTIONS_ID_RE.pattern}"
            )
        elif options_id in seen_ids:
            errors.append(
                f"settings_schema.{field_path}: duplicate ui:options.options_id '{options_id}' "
                f"(already declared by settings_schema.{seen_ids[options_id]})"
            )
        else:
            seen_ids[options_id] = field_path

        for key in sorted(set(ui_options) - UI_OPTIONS_KEYS):
            errors.append(f"settings_schema.{field_path}: unknown ui:options key '{key}'")

        if ui_options.get("multiple") and prop.get("type") != "array":
            errors.append(
                f"settings_schema.{field_path}: ui:options.multiple requires type 'array', got {prop.get('type')!r}"
            )

        cache_seconds = ui_options.get("cache_seconds")
        if cache_seconds is not None and (
            not isinstance(cache_seconds, int)
            or isinstance(cache_seconds, bool)
            or not (MIN_OPTIONS_CACHE_SECONDS <= cache_seconds <= MAX_OPTIONS_CACHE_SECONDS)
        ):
            errors.append(
                f"settings_schema.{field_path}: ui:options.cache_seconds must be an integer between "
                f"{MIN_OPTIONS_CACHE_SECONDS} and {MAX_OPTIONS_CACHE_SECONDS}, got {cache_seconds!r}"
            )

        depends_on = ui_options.get("depends_on") or []
        if not isinstance(depends_on, list):
            errors.append(f"settings_schema.{field_path}: ui:options.depends_on must be an array")
        else:
            # A dependency may point at a sibling (same object) or at a
            # top-level setting -- array item fields routinely depend on a
            # root field such as the account or agency the rows belong to.
            for dep in depends_on:
                if dep not in siblings and dep not in root_properties:
                    errors.append(
                        f"settings_schema.{field_path}: ui:options.depends_on references unknown property '{dep}'"
                    )

    return errors


def validate_manifest(data: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate a manifest dictionary against the schema.

    Args:
        data: Manifest dictionary to validate

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []

    # Check required fields
    for required in ["id", "name", "version"]:
        if required not in data:
            errors.append(f"Missing required field: {required}")

    if errors:
        return False, errors

    # Validate id format
    plugin_id = data.get("id", "")
    if not plugin_id:
        errors.append("Plugin id cannot be empty")
    elif not plugin_id[0].islower() or not plugin_id[0].isalpha():
        errors.append("Plugin id must start with a lowercase letter")
    elif not all(c.islower() or c.isdigit() or c == "_" for c in plugin_id):
        errors.append("Plugin id must contain only lowercase letters, numbers, and underscores")

    # Validate version format
    version = data.get("version", "")
    if version:
        parts = version.split(".")
        if len(parts) != 3:
            errors.append("Version must be in format X.Y.Z (semantic versioning)")
        else:
            for part in parts:
                if not part.isdigit():
                    errors.append("Version parts must be integers")
                    break

    # Validate settings_schema if present
    settings = data.get("settings_schema", {})
    if settings and not isinstance(settings, dict):
        errors.append("settings_schema must be an object")
    elif isinstance(settings, dict):
        errors.extend(validate_settings_schema_ui(settings))

    # Validate env_vars if present
    env_vars = data.get("env_vars", [])
    if not isinstance(env_vars, list):
        errors.append("env_vars must be an array")
    else:
        for i, env_var in enumerate(env_vars):
            if not isinstance(env_var, dict):
                errors.append(f"env_vars[{i}] must be an object")
            elif "name" not in env_var:
                errors.append(f"env_vars[{i}] missing required field: name")

    # Validate variables if present
    variables = data.get("variables", {})
    if variables:
        if not isinstance(variables, dict):
            errors.append("variables must be an object")
        else:
            # Validate simple variables (list or dict format)
            simple = variables.get("simple", [])
            if not isinstance(simple, list | dict):
                errors.append("variables.simple must be an array or object")

            # Validate groups if present
            groups = variables.get("groups", {})
            if groups and not isinstance(groups, dict):
                errors.append("variables.groups must be an object")

            # Validate arrays
            arrays = variables.get("arrays", {})
            if not isinstance(arrays, dict):
                errors.append("variables.arrays must be an object")
            else:
                for array_name, array_schema in arrays.items():
                    if not isinstance(array_schema, dict):
                        errors.append(f"variables.arrays.{array_name} must be an object")
                    elif "item_fields" not in array_schema:
                        errors.append(f"variables.arrays.{array_name} missing item_fields")

    # Validate max_lengths if present
    max_lengths = data.get("max_lengths", {})
    if max_lengths and not isinstance(max_lengths, dict):
        errors.append("max_lengths must be an object")
    else:
        for key, value in max_lengths.items():
            if not isinstance(value, int) or value < 1:
                errors.append(f"max_lengths.{key} must be a positive integer")

    # Validate plugin_type if present
    plugin_type = data.get("plugin_type", "data")
    if plugin_type not in ("data", "transition"):
        errors.append(f"plugin_type must be 'data' or 'transition', got '{plugin_type}'")

    # Validate transition_settings if present
    transition_settings = data.get("transition_settings")
    if transition_settings is not None:
        if not isinstance(transition_settings, dict):
            errors.append("transition_settings must be an object")
        else:
            for key, expected_type, min_value in (
                ("min_interval_ms", int, 0),
                ("max_frames", int, 1),
                ("max_runtime_seconds", int, 1),
            ):
                if key in transition_settings:
                    value = transition_settings[key]
                    if not isinstance(value, expected_type) or isinstance(value, bool):
                        errors.append(f"transition_settings.{key} must be an integer")
                    elif value < min_value:
                        errors.append(f"transition_settings.{key} must be >= {min_value}")
            if "interruptible" in transition_settings and not isinstance(transition_settings["interruptible"], bool):
                errors.append("transition_settings.interruptible must be a boolean")

    # Validate demo section if present
    demo = data.get("demo")
    if demo is not None:
        if not isinstance(demo, dict):
            errors.append("demo must be an object")
        elif "name" in demo or "template" in demo:
            # Old flat format
            if "name" not in demo:
                errors.append("demo missing required field: name")
            if "template" not in demo:
                errors.append("demo missing required field: template")
            elif not isinstance(demo["template"], list):
                errors.append("demo.template must be an array of strings")
            device_type = demo.get("device_type", "flagship")
            if device_type not in ("flagship", "note"):
                errors.append(f"demo.device_type must be 'flagship' or 'note', got '{device_type}'")
        else:
            # New keyed format: keys are device types
            for key, entry in demo.items():
                if key not in ("flagship", "note"):
                    errors.append(f"demo key must be 'flagship' or 'note', got '{key}'")
                    continue
                if not isinstance(entry, dict):
                    errors.append(f"demo.{key} must be an object")
                    continue
                if "name" not in entry:
                    errors.append(f"demo.{key} missing required field: name")
                if "template" not in entry:
                    errors.append(f"demo.{key} missing required field: template")
                elif not isinstance(entry["template"], list):
                    errors.append(f"demo.{key}.template must be an array of strings")

    # Validate board previews when present.
    #
    # Deliberately NOT required here: load_manifest() returns None whenever
    # validation fails, so requiring teaser/previews would stop every plugin
    # that has not yet adopted them from loading at all. Absence means "not
    # migrated"; only malformed values are errors. The authoring lane enforces
    # presence via validate_preview_completeness().
    is_transition = data.get("plugin_type", "data") == "transition"

    if "teaser" in data:
        if is_transition:
            errors.append("teaser is not supported for transition plugins — they have no board content to preview")
        else:
            errors.extend(validate_teaser(data["teaser"]))

    if "previews" in data:
        if is_transition:
            errors.append("previews is not supported for transition plugins — they have no board content to preview")
        else:
            errors.extend(validate_previews(data["previews"]))

    return len(errors) == 0, errors


def validate_preview_completeness(data: dict[str, Any]) -> list[str]:
    """Require board previews. For the authoring and registry lane only.

    Kept separate from :func:`validate_manifest` on purpose. A manifest with no
    ``teaser``/``previews`` is *valid* — it simply has not been migrated yet, and
    must keep loading for existing users. But a plugin being submitted to the
    registry, or shipped in this repo, is expected to carry both so the docs site
    can render it without a screenshot.

    Transition plugins are exempt: they have no data to display, and their whole
    purpose is animation, which previews deliberately do not render.

    Returns a list of human-readable errors (empty when complete).
    """
    if data.get("plugin_type", "data") == "transition":
        return []

    errors: list[str] = []
    if "teaser" not in data:
        errors.append("missing required field: teaser (one line, max 15 tiles, shown on plugin directory cards)")
    if "previews" not in data:
        errors.append("missing required field: previews (at least one literal board for the detail page)")
    return errors


def load_manifest(manifest_path: Path) -> tuple[PluginManifest | None, list[str]]:
    """Load and validate a manifest.json file.

    Args:
        manifest_path: Path to manifest.json

    Returns:
        Tuple of (PluginManifest or None, list_of_errors)
    """
    if not manifest_path.exists():
        return None, [f"Manifest not found: {manifest_path}"]

    try:
        # Use builtins.open (not Path.open) so existing tests can patch
        # builtins.open to inject fake JSON / raise read errors.
        with open(manifest_path, encoding="utf-8") as f:  # noqa: PTH123
            data = json.load(f)
    except json.JSONDecodeError as e:
        return None, [f"Invalid JSON in manifest: {e}"]
    except Exception as e:
        return None, [f"Failed to read manifest: {e}"]

    # Validate
    is_valid, validation_errors = validate_manifest(data)
    if not is_valid:
        return None, validation_errors

    # Parse
    try:
        manifest = PluginManifest.from_dict(data)
        return manifest, []
    except Exception as e:
        return None, [f"Failed to parse manifest: {e}"]
