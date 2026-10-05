"""The ``vestaboard`` output's hooks: Vestaboard knowledge core no longer holds.

Core asks the output (:mod:`src.outputs.hooks`); these modules answer for a
Vestaboard. They are the in-tree half of what becomes the
``fiestaboard-output--vestaboard`` plugin in Phase 4, alongside the driver
modules (``src/board_client.py``, ``src/note_array_local_client.py``):

- :mod:`.discovery` — ``discover(timeout)``: mDNS browse plus a subnet probe
  of the Local API port (was ``src/system/mdns.py``).
- :mod:`.diagnostics` — the board section of the network diagnostics and its
  troubleshooting advice (was ``src/network_diagnostics.py``).
- :mod:`.connection` — the connection probe's status → verdict mapping behind
  ``BoardClient.check_connection`` (was ``src/config_api/service.py``).
- :mod:`.local_api` — the ``enable_local_api`` custom action, the
  enablement-token exchange with its CodeQL-recognised SSRF block moved
  whole (was ``src/config_api/service.py``).

Each is imported lazily by the registry entry (``src/outputs/registry.py``),
so this package's ``__init__`` stays import-free.

``tests/test_vestaboard_output_hooks.py`` counts the Vestaboard transport
literals left in ``src/`` outside these modules; Phase 4 drives it to zero.
"""

#: The diagnostics summary when every check passed.
ALL_CLEAR_SUMMARY = "All checks passed — your Vestaboard connection is healthy"
