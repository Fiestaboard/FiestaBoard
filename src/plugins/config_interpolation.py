"""Config variable interpolation for FiestaBoard plugins.

Provides runtime resolution of ``{{variable}}`` patterns in plugin
configuration values (URLs, headers, etc.).  This enables plugins to
use dynamic values such as the current date or data from other plugins
without hard-coding them.

Supported variable sources
--------------------------
* **Built-in** -- date/time components (``{{date}}``, ``{{year}}``, etc.)
* **Custom date formats** -- ``{{date:FORMAT}}`` using strftime syntax
* **Cross-plugin** -- ``{{plugin_id.field}}`` passed via *extra_variables*

The interpolation is intentionally **non-destructive**: unknown variables
are left as-is so plugins can still detect unresolved placeholders.
"""

import logging
import re
import time
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Match {{ variable_name }} with optional whitespace inside braces.
# The variable name can contain alphanumerics, underscores, dots, colons,
# percent signs, hyphens, and forward slashes (to support date format strings
# like date:%Y%m%d, dotted plugin references like weather.temperature, and
# date formats containing slashes like date:%m/%d/%Y).
_VAR_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_.:%/-]*)\s*\}\}")

# Common date formats that are pre-computed for convenience.
_COMMON_DATE_FORMATS: List[str] = [
    "%Y%m%d",       # 20250615
    "%m/%d/%Y",     # 06/15/2025
    "%m-%d",        # 06-15
    "%Y-%m",        # 2025-06
    "%d-%m-%Y",     # 15-06-2025
    "%Y/%m/%d",     # 2025/06/15
]


def get_builtin_variables(timezone: Optional[str] = None) -> Dict[str, str]:
    """Return a dictionary of built-in system variables.

    All values are returned as strings so they can be safely spliced
    into URL strings or other config values.

    Args:
        timezone: Optional IANA timezone name.  Falls back to the
                  system-configured timezone via ``Config.TIMEZONE``
                  or ``"America/Los_Angeles"`` as a last resort.

    Returns:
        Dictionary mapping variable names to their current string values.
    """
    try:
        if timezone:
            from ..utils.datetime import DateTimeSource
            source = DateTimeSource(timezone=timezone)
            now = source.time_service.get_current_time(timezone)
        else:
            from ..utils.datetime import get_datetime_source
            source = get_datetime_source()
            now = source.time_service.get_current_time(source.timezone)
    except Exception:
        # If the time service is unavailable fall back to UTC.
        now = datetime.utcnow()

    variables: Dict[str, str] = {
        "date": now.strftime("%Y-%m-%d"),
        "year": str(now.year),
        "month": str(now.month),
        "day": str(now.day),
        "hour": str(now.hour),
        "minute": str(now.minute),
        "timestamp": str(int(time.time())),
        "month_name": now.strftime("%B"),
        "day_of_week": now.strftime("%A"),
        "month_padded": now.strftime("%m"),
        "day_padded": now.strftime("%d"),
    }

    # Pre-compute common date format variables.
    for fmt in _COMMON_DATE_FORMATS:
        key = f"date:{fmt}"
        variables[key] = now.strftime(fmt)

    return variables


def interpolate_string(
    value: Any,
    variables: Dict[str, str],
) -> Any:
    """Replace ``{{variable}}`` patterns in *value* with resolved values.

    Only string values are processed; non-string values are returned
    unchanged.  Unknown variables are **preserved** (left as-is).

    Args:
        value: The value to interpolate.  If not a string, returned as-is.
        variables: Mapping of variable names to replacement strings.

    Returns:
        The interpolated string, or the original value if not a string.
    """
    if not isinstance(value, str):
        return value

    if "{{" not in value:
        return value

    def _replace(match: re.Match) -> str:
        var_name = match.group(1)
        if var_name in variables:
            return variables[var_name]
        # Check if it's a custom date format that wasn't pre-computed.
        if var_name.startswith("date:"):
            fmt = var_name[5:]  # strip "date:" prefix
            try:
                # Use the same time source as builtin variables.
                from ..utils.datetime import get_datetime_source
                source = get_datetime_source()
                now = source.time_service.get_current_time(source.timezone)
                return now.strftime(fmt)
            except Exception:
                try:
                    return datetime.utcnow().strftime(fmt)
                except Exception:
                    logger.debug("Could not format datetime with UTC fallback")
        return match.group(0)

    return _VAR_PATTERN.sub(_replace, value)


def interpolate_config(
    config: Dict[str, Any],
    variables: Dict[str, str],
) -> Dict[str, Any]:
    """Recursively interpolate all string values in a config dictionary.

    The original *config* is **not** mutated; a deep copy is returned.

    Args:
        config: Plugin configuration dictionary.
        variables: Mapping of variable names to replacement strings.

    Returns:
        A new dictionary with all ``{{variable}}`` patterns resolved.
    """
    return _interpolate_value(deepcopy(config), variables)


def _interpolate_value(value: Any, variables: Dict[str, str]) -> Any:
    """Recursively interpolate a value (string, dict, or list)."""
    if isinstance(value, str):
        return interpolate_string(value, variables)
    if isinstance(value, dict):
        return {k: _interpolate_value(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate_value(item, variables) for item in value]
    return value
