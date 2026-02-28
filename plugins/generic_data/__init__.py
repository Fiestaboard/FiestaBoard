"""Generic Data plugin for FiestaBoard.

Fetches data from any URL (JSON or XML) and maps response fields to
template variables using dot-notation paths.  This allows users to
integrate simple data sources without writing a custom plugin.
"""

import logging
import os
import re
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree

import requests

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)

# Maximum response size to prevent memory issues (1 MB)
MAX_RESPONSE_BYTES = 1_048_576

# Request timeout in seconds
REQUEST_TIMEOUT = 30


def _resolve_path(data: Any, path: str) -> Any:
    """Resolve a dot-notation path against a data structure.

    Supports:
      - Dot-separated keys:  ``"current.temp_f"``
      - Array indices:        ``"items[0].name"``

    Args:
        data: Parsed JSON data (dicts, lists, scalars).
        path: Dot-notation path string.

    Returns:
        The resolved value, or ``None`` if the path cannot be followed.
    """
    # Split on dots, but keep bracket indices attached to their segment
    # e.g. "items[0].name" -> ["items[0]", "name"]
    segments = path.split(".")
    current = data
    for segment in segments:
        if current is None:
            return None

        # Check for array index: segment like "items[0]"
        match = re.match(r"^([^\[]*)\[(\d+)\]$", segment)
        if match:
            key, idx = match.group(1), int(match.group(2))
            if key:
                if isinstance(current, dict):
                    current = current.get(key)
                else:
                    return None
            if isinstance(current, list) and 0 <= idx < len(current):
                current = current[idx]
            else:
                return None
        else:
            if isinstance(current, dict):
                current = current.get(segment)
            else:
                return None

    return current


def _xml_to_dict(element: ElementTree.Element) -> Any:
    """Convert an XML element tree into a nested dict/list structure.

    Leaf elements become ``{"tag": "text"}``.  Elements with children are
    nested dicts.  Repeated sibling tags are collected into lists.
    """
    children = list(element)
    if not children:
        return element.text or ""

    result: Dict[str, Any] = {}
    for child in children:
        child_data = _xml_to_dict(child)
        tag = child.tag
        if tag in result:
            # Convert to list for repeated tags
            existing = result[tag]
            if isinstance(existing, list):
                existing.append(child_data)
            else:
                result[tag] = [existing, child_data]
        else:
            result[tag] = child_data

    return result


class GenericDataPlugin(PluginBase):
    """Generic data consumer plugin.

    Fetches a URL, parses the response as JSON or XML, and exposes
    user-defined variable mappings to the template engine.
    """

    @property
    def plugin_id(self) -> str:
        """Return plugin identifier."""
        return "generic_data"

    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate generic data configuration."""
        errors: List[str] = []

        url = config.get("url") or os.getenv("GENERIC_DATA_URL")
        if not url:
            errors.append("Data URL is required")
        elif not url.startswith(("http://", "https://")):
            errors.append("URL must start with http:// or https://")

        fmt = config.get("format", "json")
        if fmt not in ("json", "xml"):
            errors.append(f"Unsupported format: {fmt}. Use 'json' or 'xml'")

        method = config.get("method", "GET")
        if method not in ("GET", "POST"):
            errors.append(f"Unsupported HTTP method: {method}")

        mappings = config.get("mappings", [])
        if not mappings:
            errors.append("At least one variable mapping is required")
        else:
            seen_vars: set = set()
            for i, mapping in enumerate(mappings):
                var = mapping.get("variable", "")
                path = mapping.get("path", "")
                if not var:
                    errors.append(f"Mapping {i + 1}: variable name is required")
                elif not re.match(r"^[a-z][a-z0-9_]*$", var):
                    errors.append(
                        f"Mapping {i + 1}: variable name '{var}' must be "
                        "lowercase with underscores only"
                    )
                if not path:
                    errors.append(f"Mapping {i + 1}: data path is required")
                if var in seen_vars:
                    errors.append(
                        f"Mapping {i + 1}: duplicate variable name '{var}'"
                    )
                seen_vars.add(var)

        headers = config.get("headers", [])
        for i, header in enumerate(headers):
            if not header.get("name"):
                errors.append(f"Header {i + 1}: name is required")
            if not header.get("value"):
                errors.append(f"Header {i + 1}: value is required")

        refresh = config.get("refresh_seconds", 300)
        if isinstance(refresh, (int, float)) and refresh < 30:
            errors.append("Refresh interval must be at least 30 seconds")

        return errors

    def fetch_data(self) -> PluginResult:
        """Fetch data from the configured URL and apply mappings."""
        url = self.config.get("url") or os.getenv("GENERIC_DATA_URL")
        if not url:
            return PluginResult(
                available=False,
                error="Data URL not configured",
            )

        fmt = self.config.get("format", "json")
        method = self.config.get("method", "GET")
        mappings = self.config.get("mappings", [])

        if not mappings:
            return PluginResult(
                available=False,
                error="No variable mappings configured",
            )

        # Build request headers
        headers: Dict[str, str] = {"Accept": "application/json" if fmt == "json" else "application/xml"}
        for h in self.config.get("headers", []):
            name = h.get("name", "")
            value = h.get("value", "")
            if name and value:
                headers[name] = value

        try:
            kwargs: Dict[str, Any] = {
                "headers": headers,
                "timeout": REQUEST_TIMEOUT,
            }
            body = self.config.get("body")
            if method == "POST" and body:
                kwargs["data"] = body

            response = requests.request(method, url, **kwargs)
            response.raise_for_status()

            # Enforce response size limit
            if len(response.content) > MAX_RESPONSE_BYTES:
                return PluginResult(
                    available=False,
                    error="Response too large (exceeds 1 MB limit)",
                )

            # Parse response
            parsed = self._parse_response(response, fmt)
            if parsed is None:
                return PluginResult(
                    available=False,
                    error=f"Failed to parse response as {fmt.upper()}",
                )

            # Apply variable mappings
            data: Dict[str, Any] = {}
            for mapping in mappings:
                var_name = mapping.get("variable", "")
                path = mapping.get("path", "")
                default = mapping.get("default", "")

                if not var_name or not path:
                    continue

                value = _resolve_path(parsed, path)
                data[var_name] = str(value) if value is not None else default

            # Include a truncated raw response for debugging
            raw = str(parsed)
            data["raw_response"] = raw[:22] if len(raw) > 22 else raw

            return PluginResult(
                available=True,
                data=data,
                formatted_lines=self._format_display(data, mappings),
            )

        except requests.exceptions.Timeout:
            logger.error("Timeout fetching %s", url)
            return PluginResult(
                available=False,
                error="Request timed out",
            )
        except requests.exceptions.ConnectionError:
            logger.error("Connection error fetching %s", url)
            return PluginResult(
                available=False,
                error="Connection error",
            )
        except requests.exceptions.HTTPError as e:
            logger.error("HTTP error fetching %s: %s", url, e)
            return PluginResult(
                available=False,
                error=f"HTTP error: {e}",
            )
        except Exception as e:
            logger.exception("Error fetching generic data")
            return PluginResult(
                available=False,
                error=str(e),
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(response: requests.Response, fmt: str) -> Any:
        """Parse an HTTP response according to *fmt*."""
        try:
            if fmt == "json":
                return response.json()
            if fmt == "xml":
                root = ElementTree.fromstring(response.text)
                return _xml_to_dict(root)
        except Exception:
            logger.exception("Failed to parse response as %s", fmt)
        return None

    @staticmethod
    def _format_display(
        data: Dict[str, Any],
        mappings: List[Dict[str, str]],
    ) -> List[str]:
        """Format mapped data for the 6-line board display."""
        lines: List[str] = ["GENERIC DATA".center(22), ""]

        for mapping in mappings[:4]:  # Show up to 4 mappings
            var = mapping.get("variable", "")
            value = data.get(var, "")
            label = var.replace("_", " ").upper()
            line = f"{label}: {value}"
            lines.append(line[:22])

        # Pad to 6 lines
        while len(lines) < 6:
            lines.append("")

        return lines[:6]

    def get_formatted_display(self) -> Optional[List[str]]:
        """Return default formatted generic data display."""
        result = self.fetch_data()
        if not result.available or not result.data:
            return None
        return result.formatted_lines

    def cleanup(self) -> None:
        """Cleanup when plugin is disabled."""
        logger.info("Plugin %s cleanup", self.plugin_id)


# Export the plugin class
Plugin = GenericDataPlugin
