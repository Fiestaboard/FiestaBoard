"""Plugin manifest validation and parsing.

The manifest.json file is the heart of each plugin, defining:
- Plugin metadata (id, name, version, author, etc.)
- Settings schema (JSON Schema for configuration UI)
- Environment variables (required/optional)
- Template variables schema (simple, arrays, nested)
- Max lengths for template validation
- Color rules schema
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# JSON Schema for validating manifest.json files
MANIFEST_SCHEMA = {
    "type": "object",
    "required": ["id", "name", "version"],
    "properties": {
        "id": {
            "type": "string",
            "pattern": "^[a-z][a-z0-9_]*$",
            "description": "Unique plugin identifier (lowercase, underscores allowed)"
        },
        "name": {
            "type": "string",
            "minLength": 1,
            "maxLength": 50,
            "description": "Human-readable plugin name"
        },
        "version": {
            "type": "string",
            "pattern": "^\\d+\\.\\d+\\.\\d+$",
            "description": "Semantic version (e.g., 1.0.0)"
        },
        "description": {
            "type": "string",
            "maxLength": 200,
            "description": "Short description of the plugin"
        },
        "author": {
            "type": "string",
            "description": "Plugin author or maintainer"
        },
        "repository": {
            "type": "string",
            "format": "uri",
            "description": "Source repository URL"
        },
        "documentation": {
            "type": "string",
            "description": "Path to documentation file (relative to plugin folder)"
        },
        "settings_schema": {
            "type": "object",
            "description": "JSON Schema for plugin configuration"
        },
        "env_vars": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string"},
                    "required": {"type": "boolean", "default": False},
                    "description": {"type": "string"},
                    "default": {"type": "string"}
                }
            },
            "description": "Environment variables used by the plugin"
        },
        "variables": {
            "type": "object",
            "properties": {
                "simple": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Simple key-value variables"
                },
                "arrays": {
                    "type": "object",
                    "additionalProperties": {
                        "type": "object",
                        "properties": {
                            "label_field": {"type": "string"},
                            "item_fields": {
                                "type": "array",
                                "items": {"type": "string"}
                            },
                            "sub_arrays": {
                                "type": "object",
                                "additionalProperties": {
                                    "type": "object",
                                    "properties": {
                                        "key_type": {"type": "string", "enum": ["index", "dynamic"]},
                                        "key_field": {"type": "string"},
                                        "item_fields": {
                                            "type": "array",
                                            "items": {"type": "string"}
                                        }
                                    }
                                }
                            }
                        }
                    },
                    "description": "Array variables with indexed access"
                }
            },
            "description": "Template variables exposed by the plugin"
        },
        "max_lengths": {
            "type": "object",
            "additionalProperties": {"type": "integer"},
            "description": "Maximum character lengths for variables"
        },
        "color_rules_schema": {
            "type": "object",
            "description": "Schema for configurable color rules"
        },
        "icon": {
            "type": "string",
            "description": "Icon name from Lucide icons"
        },
        "category": {
            "type": "string",
            "enum": ["art", "data", "transit", "weather", "entertainment", "utility", "home"],
            "description": "Plugin category for organization"
        },
        "fiestaboard_version": {
            "type": "string",
            "description": "Minimum FiestaBoard version required (semver constraint, e.g. '>=2.10.0')"
        }
    }
}


@dataclass
class VariableArraySchema:
    """Schema for array-type variables."""
    name: str
    label_field: str
    item_fields: List[str]
    sub_arrays: Dict[str, "VariableArraySchema"] = field(default_factory=dict)
    key_type: str = "index"  # "index" or "dynamic"
    key_field: Optional[str] = None


@dataclass
class VariablesSchema:
    """Complete variables schema from manifest."""
    simple: List[str] = field(default_factory=list)
    arrays: Dict[str, VariableArraySchema] = field(default_factory=dict)
    
    def get_all_variable_names(self, plugin_id: str) -> List[str]:
        """Get all variable names for template engine.
        
        Returns flattened list like:
        - plugin_id.simple_var
        - plugin_id.array_name (for aggregate access)
        - plugin_id.array_name.N.field (documented pattern)
        """
        names = []
        
        # Simple variables
        for var in self.simple:
            names.append(var)
        
        # Array variables
        for array_name, schema in self.arrays.items():
            names.append(array_name)
            for field_name in schema.item_fields:
                names.append(f"{array_name}.*.{field_name}")
            
            # Sub-arrays
            for sub_name, sub_schema in schema.sub_arrays.items():
                names.append(f"{array_name}.*.{sub_name}")
                for sub_field in sub_schema.item_fields:
                    names.append(f"{array_name}.*.{sub_name}.*.{sub_field}")
        
        return names


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
    settings_schema: Dict[str, Any] = field(default_factory=dict)
    env_vars: List[Dict[str, Any]] = field(default_factory=list)
    variables: VariablesSchema = field(default_factory=VariablesSchema)
    max_lengths: Dict[str, int] = field(default_factory=dict)
    color_rules_schema: Dict[str, Any] = field(default_factory=dict)
    icon: str = "puzzle"
    category: str = "utility"
    fiestaboard_version: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PluginManifest":
        """Create PluginManifest from dictionary."""
        # Parse variables schema
        variables_data = data.get("variables", {})
        variables = VariablesSchema(
            simple=variables_data.get("simple", []),
            arrays={}
        )
        
        # Parse array schemas
        for array_name, array_data in variables_data.get("arrays", {}).items():
            sub_arrays = {}
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
        
        return cls(
            id=data["id"],
            name=data["name"],
            version=data["version"],
            description=data.get("description", ""),
            author=data.get("author", "Unknown"),
            repository=data.get("repository", ""),
            documentation=data.get("documentation", "README.md"),
            settings_schema=data.get("settings_schema", {}),
            env_vars=data.get("env_vars", []),
            variables=variables,
            max_lengths=data.get("max_lengths", {}),
            color_rules_schema=data.get("color_rules_schema", {}),
            icon=data.get("icon", "puzzle"),
            category=data.get("category", "utility"),
            fiestaboard_version=data.get("fiestaboard_version", ""),
            raw=data,
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
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
        }


def validate_manifest(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
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
    elif not all(c.islower() or c.isdigit() or c == '_' for c in plugin_id):
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
            # Validate simple variables
            simple = variables.get("simple", [])
            if not isinstance(simple, list):
                errors.append("variables.simple must be an array")
            
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
    
    return len(errors) == 0, errors


def load_manifest(manifest_path: Path) -> Tuple[Optional[PluginManifest], List[str]]:
    """Load and validate a manifest.json file.
    
    Args:
        manifest_path: Path to manifest.json
        
    Returns:
        Tuple of (PluginManifest or None, list_of_errors)
    """
    errors = []
    
    if not manifest_path.exists():
        return None, [f"Manifest not found: {manifest_path}"]
    
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
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

