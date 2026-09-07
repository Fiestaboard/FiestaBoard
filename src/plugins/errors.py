"""Domain exceptions for the plugin subsystem (Phase 2 §2, slice 4).

Every other service in the tree raises a domain error and lets its router
decide the status code. ``PluginService`` was the exception: written during
Phase 1, it raised ``fastapi.HTTPException`` at 25 sites, so the one service
added while the layering rule was being written is the one that broke it. The
2026-09 audit called that out; these classes are the fix.

The rule this file exists to keep: **nothing here knows an HTTP status code.**
The mapping from exception class to status lives in ``src/plugins/routes.py``
(``_STATUS_BY_ERROR``), which is the only layer entitled to have an opinion
about HTTP. The MCP/ops layer catches the same exceptions and renders them as
its own error envelope without going near a status code at all.

``PluginConfigInvalid`` is the one error carrying structured data: schema
validation produces a *list* of per-field messages, and flattening it into one
string at the raise site would throw away what the settings form needs to
highlight the offending field.
"""

from __future__ import annotations


class PluginError(Exception):
    """Base for every failure the plugin domain reports to a caller.

    ``str(exc)`` is the human-readable message, and it is the whole contract
    for every subclass except :class:`PluginConfigInvalid`.
    """


class PluginNotFound(PluginError):
    """No plugin (or plugin source) is installed under this id."""


class PluginNotEnabled(PluginError):
    """The plugin is installed but currently disabled."""


class PluginConfigInvalid(PluginError):
    """Configuration failed the manifest's settings schema.

    Carries the per-field messages the registry produced so the settings form
    can point at the field that is wrong, rather than showing one flattened
    blob of text.
    """

    def __init__(self, message: str, errors: list[str]) -> None:
        super().__init__(message)
        self.errors = list(errors)


class PluginOperationRejected(PluginError):
    """The registry refused the operation and said why.

    Enable/disable that returned False, an invalid instance label, an install
    or uninstall the registry declined, a branch name that failed validation,
    a plugin path outside the external plugins directory.
    """


class PluginOperationFailed(PluginError):
    """The operation was legitimate but failed while running.

    A git fetch that errored, a plugin that would not re-import after an
    update. Distinct from :class:`PluginOperationRejected` because the caller
    did nothing wrong — this is a server-side fault.
    """


class PluginOptionsThrottled(PluginError):
    """A refresh of an options catalog came in faster than the throttle allows.

    Lives here rather than as an ``HTTPException(429)`` inside the options
    runtime for the same reason as everything else in this file: the runtime
    does not get to pick status codes.
    """
