"""Core's board-settings action runner for the ``vestaboard`` output.

The Vestaboard itself — transport, connection probe, discovery,
diagnostics, the Local API enablement exchange — is an output plugin now
(``first_party_outputs/vestaboard``, loaded by :mod:`src.outputs.first_party`).
What stays here is :mod:`.actions`: core's dispatcher for the board settings
screen's actions on a Vestaboard board, which resolves the board's live or
draft driver, refuses what it must before a device is contacted, and asks
the plugin for every device conversation. It goes when the Vestaboard
settings screen moves onto the plugin renderer (Phase 4, P4d).

``tests/test_vestaboard_output_hooks.py`` counts the Vestaboard transport
literals left in ``src/``; Phase 4 drives it to zero.
"""
