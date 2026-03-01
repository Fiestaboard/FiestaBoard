"""Message formatting modules for board display.

.. deprecated:: 2.0
    This package is **archived/legacy** (pre-2.0). The message formatting logic
    has been superseded by the template engine and plugin rendering pipeline
    introduced in v2.0. This package is retained only for backward-compatible
    code paths and will be removed in a future major release.

See Also:
    - ``src/templates/`` for the current template engine
    - ``docs/development/TECHNICAL_DEBT.md`` for the full deprecation timeline
"""

import warnings

warnings.warn(
    "src.formatters is a legacy package (pre-2.0) and is scheduled for removal. "
    "Use the template engine in src/templates/ instead.",
    DeprecationWarning,
    stacklevel=2,
)

