"""The app's own service surface: liveness, status, and the display loop's
start/stop/refresh controls.

Named ``service_api`` rather than ``service`` because ``src/<domain>/service.py``
already means "the orchestration layer of a domain" everywhere else in this
tree; ``src/config_api/`` was named the same way for the same reason.
"""
