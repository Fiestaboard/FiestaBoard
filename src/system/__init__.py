"""System management module for Docker container control and mDNS discovery.

.. deprecated:: 2.0
    This package is **archived/legacy** (pre-2.0). The system management
    utilities here predate the Docker-based architecture introduced in v2.0.
    This package is retained only for backward-compatible functionality (e.g.
    mDNS discovery) and will be removed in a future major release.

See Also:
    - ``docs/development/TECHNICAL_DEBT.md`` for the full deprecation timeline
"""

import warnings

warnings.warn(
    "src.system is a legacy package (pre-2.0) and is scheduled for removal.",
    DeprecationWarning,
    stacklevel=2,
)

