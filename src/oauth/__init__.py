"""OAuth sign-in for plugins.

Start at ``service.py``. This package's ``__init__`` imports nothing on
purpose: ``src/plugins/manifest.py`` imports ``src.oauth.provider`` to
validate manifests, and must not drag the service (and through it the plugin
registry) in with it.
"""
