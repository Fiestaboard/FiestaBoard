"""Persistence-callback support for mocked plugin lifecycle methods."""


def support_lifecycle_persistence(registry):
    """Keep each mock's acceptance result and run persistence only on success."""
    for name in ("enable_plugin", "disable_plugin"):
        method = getattr(registry, name)

        def change(_plugin_id, *, before_change=None, _method=method):
            accepted = _method.return_value
            if accepted and before_change is not None:
                before_change()
            return accepted

        method.side_effect = change
