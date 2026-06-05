"""Plugin manifest validation and parsing.

The manifest.json file is the heart of each plugin, defining:
- Plugin metadata (id, name, version, author, etc.)
- Settings schema (JSON Schema for configuration UI)
- Environment variables (required/optional)
- Template variables schema (simple, arrays, nested)
- Max lengths for template validation
- Color rules schema
"""

import copy
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
            "enum": ["art", "data", "transit", "weather", "entertainment", "utility", "home"],
            "description": "Plugin category for organization",
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
            "screenshots": [
                {
                    "src": s.src,
                    "alt": s.alt,
                    "caption": s.caption,
                    "primary": s.primary,
                }
                for s in self.screenshots
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

    return len(errors) == 0, errors


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
