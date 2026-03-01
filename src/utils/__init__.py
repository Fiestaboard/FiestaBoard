"""Utility modules for fetching information and shared functionality.

.. deprecated:: 2.0
    This package is **archived/legacy** (pre-2.0). All feature utilities in this
    directory have been superseded by the plugin architecture introduced in v2.0.
    Use the corresponding plugins under ``plugins/`` instead. This package is
    retained only for backward-compatible API endpoints and will be removed in a
    future major release.

See Also:
    - ``plugins/`` for the current plugin-based data sources
    - ``docs/development/TECHNICAL_DEBT.md`` for the full deprecation timeline
"""

import warnings

warnings.warn(
    "src.utils is a legacy package (pre-2.0) and is scheduled for removal. "
    "Use the plugin system under plugins/ instead.",
    DeprecationWarning,
    stacklevel=2,
)

