"""Platform helpers that back a plugin's configuration form.

``CLAUDE.md`` is explicit that plugin-specific code does not belong in
``src/``, and thirteen platform routes serving individual plugins predate that
rule. This slice (Phase 2, Task 8) audited each for a live consumer rather
than converting them by reflex: eleven had none and are deprecated in place
(#1915); the two here are load-bearing for the web client and were converted.

Both are on the path to becoming plugin ``options`` providers (the mechanism
``GET /plugins/{id}/options/{options_id}`` already gives every other plugin),
at which point this package goes away — tracked in #1916.
"""
