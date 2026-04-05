"""Generic Data plugin for FiestaBoard.

Fetches data from any URL (JSON or XML) and maps response fields to
template variables using dot-notation paths.  This allows users to
integrate simple data sources without writing a custom plugin.

Supports multiple feeds — each with its own URL, format, headers, and
mappings — so users can pull data from several APIs at once.
"""

import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import defusedxml.ElementTree as ElementTree
import requests

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)

MAX_RESPONSE_BYTES = 1_048_576  # 1 MB
REQUEST_TIMEOUT = 30
DISPLAY_WIDTH = 22
MAX_FEEDS = 10


def _resolve_path(data: Any, path: str) -> Any:
    """Resolve a dot-notation path against a data structure.

    Supports:
      - Dot-separated keys:  ``"current.temp_f"``
      - Array indices:        ``"items[0].name"``

    Returns the resolved value, or ``None`` if the path cannot be followed.
    """
    segments = path.split(".")
    current = data
    for segment in segments:
        if current is None:
            return None

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


def _xml_to_dict(element: Any) -> Any:
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
            existing = result[tag]
            if isinstance(existing, list):
                existing.append(child_data)
            else:
                result[tag] = [existing, child_data]
        else:
            result[tag] = child_data

    return result


def _build_feeds(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalise config into a list of feed dicts.

    If the config contains a ``feeds`` array, return it directly.
    Otherwise build a single-feed list from the top-level fields
    (backward-compatible with the original single-URL config).
    """
    if config.get("feeds"):
        return list(config["feeds"])

    url = config.get("url") or os.getenv("GENERIC_DATA_URL")
    mappings = config.get("mappings", [])
    if not url and not mappings:
        return []

    return [
        {
            "name": config.get("name", ""),
            "url": url or "",
            "format": config.get("format", "json"),
            "method": config.get("method", "GET"),
            "headers": config.get("headers", []),
            "body": config.get("body"),
            "mappings": mappings,
        }
    ]


class GenericDataPlugin(PluginBase):
    """Generic data consumer plugin.

    Fetches one or more URLs, parses each response as JSON or XML, and
    exposes user-defined variable mappings to the template engine.
    """

    @property
    def plugin_id(self) -> str:
        return "generic_data"

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate generic data configuration."""
        errors: List[str] = []

        feeds = _build_feeds(config)
        if not feeds:
            errors.append("At least one data feed is required (set a URL and mappings, or add feeds)")
            return errors

        if len(feeds) > MAX_FEEDS:
            errors.append(f"Maximum {MAX_FEEDS} feeds allowed")

        seen_vars: set = set()
        for fi, feed in enumerate(feeds):
            prefix = f"Feed {fi + 1}" if len(feeds) > 1 else ""
            errors.extend(self._validate_feed(feed, prefix, seen_vars))

        refresh = config.get("refresh_seconds", 300)
        if isinstance(refresh, (int, float)) and refresh < 30:
            errors.append("Refresh interval must be at least 30 seconds")

        return errors

    @staticmethod
    def _validate_feed(
        feed: Dict[str, Any],
        prefix: str,
        seen_vars: set,
    ) -> List[str]:
        """Validate a single feed definition."""
        errors: List[str] = []
        label = f"{prefix}: " if prefix else ""

        url = feed.get("url") or ""
        if not url:
            errors.append(f"{label}Data URL is required")
        elif not url.startswith(("http://", "https://")):
            errors.append(f"{label}URL must start with http:// or https://")

        fmt = feed.get("format", "json")
        if fmt not in ("json", "xml"):
            errors.append(f"{label}Unsupported format: {fmt}. Use 'json' or 'xml'")

        method = feed.get("method", "GET")
        if method not in ("GET", "POST"):
            errors.append(f"{label}Unsupported HTTP method: {method}")

        mappings = feed.get("mappings", [])
        if not mappings:
            errors.append(f"{label}At least one variable mapping is required")
        else:
            for i, mapping in enumerate(mappings):
                var = mapping.get("variable", "")
                path = mapping.get("path", "")
                if not var:
                    errors.append(f"{label}Mapping {i + 1}: variable name is required")
                elif not re.match(r"^[a-z][a-z0-9_]*$", var):
                    errors.append(
                        f"{label}Mapping {i + 1}: variable name '{var}' must be "
                        "lowercase with underscores only"
                    )
                if not path:
                    errors.append(f"{label}Mapping {i + 1}: data path is required")
                if var in seen_vars:
                    errors.append(f"{label}Mapping {i + 1}: duplicate variable name '{var}'")
                seen_vars.add(var)

        headers = feed.get("headers", [])
        for i, header in enumerate(headers):
            if not header.get("name"):
                errors.append(f"{label}Header {i + 1}: name is required")
            if not header.get("value"):
                errors.append(f"{label}Header {i + 1}: value is required")

        return errors

    # ------------------------------------------------------------------
    # Data fetching
    # ------------------------------------------------------------------

    def fetch_data(self) -> PluginResult:
        """Fetch data from all configured feeds and merge mappings."""
        # Resolve {{date}}, {{year}}, etc. in URLs, headers, and bodies (FiestaBoard #537).
        resolved_config = self.resolve_config_variables()
        feeds = _build_feeds(resolved_config)

        if not feeds:
            return PluginResult(available=False, error="No data feeds configured")

        all_mappings: List[Dict[str, str]] = []
        data: Dict[str, Any] = {}
        errors: List[str] = []

        for fi, feed in enumerate(feeds):
            feed_data, feed_mappings, err = self._fetch_feed(feed, fi)
            if err:
                errors.append(err)
            else:
                data.update(feed_data)
                all_mappings.extend(feed_mappings)

        if not data and errors:
            return PluginResult(
                available=False,
                error="; ".join(errors),
            )

        data["feed_count"] = str(len(feeds))

        return PluginResult(
            available=True,
            data=data,
            formatted_lines=self._format_display(data, all_mappings),
        )

    def _fetch_feed(
        self,
        feed: Dict[str, Any],
        index: int,
    ) -> Tuple[Dict[str, Any], List[Dict[str, str]], Optional[str]]:
        """Fetch and parse a single feed, returning (data, mappings, error)."""
        url = feed.get("url", "")
        if not url:
            return {}, [], "Data URL not configured"

        fmt = feed.get("format", "json")
        method = feed.get("method", "GET")
        mappings = feed.get("mappings", [])

        if not mappings:
            return {}, [], "No variable mappings configured"

        headers: Dict[str, str] = {
            "Accept": "application/json" if fmt == "json" else "application/xml",
        }
        for h in feed.get("headers", []):
            name = h.get("name", "")
            value = h.get("value", "")
            if name and value:
                headers[name] = value

        try:
            kwargs: Dict[str, Any] = {
                "headers": headers,
                "timeout": REQUEST_TIMEOUT,
            }
            body = feed.get("body")
            if method == "POST" and body:
                kwargs["data"] = body

            response = requests.request(method, url, **kwargs)
            response.raise_for_status()

            if len(response.content) > MAX_RESPONSE_BYTES:
                return {}, [], f"Response too large (exceeds 1 MB limit)"

            parsed = self._parse_response(response, fmt)
            if parsed is None:
                return {}, [], f"Failed to parse response as {fmt.upper()}"

            data: Dict[str, Any] = {}
            for mapping in mappings:
                var_name = mapping.get("variable", "")
                path = mapping.get("path", "")
                default = mapping.get("default", "")
                if not var_name or not path:
                    continue
                value = _resolve_path(parsed, path)
                data[var_name] = str(value) if value is not None else default

            return data, list(mappings), None

        except requests.exceptions.Timeout:
            logger.error("Timeout fetching %s", url)
            return {}, [], "Request timed out"
        except requests.exceptions.ConnectionError:
            logger.error("Connection error fetching %s", url)
            return {}, [], "Connection error"
        except requests.exceptions.HTTPError as e:
            logger.error("HTTP error fetching %s: %s", url, e)
            return {}, [], f"HTTP error: {e}"
        except Exception as e:
            logger.exception("Error fetching generic data from %s", url)
            return {}, [], str(e)

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
        lines: List[str] = ["GENERIC DATA".center(DISPLAY_WIDTH), ""]

        for mapping in mappings[:4]:
            var = mapping.get("variable", "")
            value = data.get(var, "")
            label = var.replace("_", " ").upper()
            line = f"{label}: {value}"
            lines.append(line[:DISPLAY_WIDTH])

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


Plugin = GenericDataPlugin
