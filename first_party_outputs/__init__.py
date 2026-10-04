"""FiestaBoard's first-party output plugins, staged in-repo (plan Phase 4).

Each directory here is an output plugin package laid out exactly as its own
repository will be (``Fiestaboard/fiestaboard-output--<name>``): a root
``__init__.py`` exporting the ``OutputPluginBase`` subclass, ``manifest.json``
with its ``output`` block, ``output/device-models.json``, ``tests/``,
``README.md`` and ``docs/SETUP.md``. The packages import FiestaBoard only
through the output-plugin author API (``src.plugins``);
``tests/test_first_party_output_imports.py`` holds them to it.

Core loads them through the output-plugin path as first-party outputs
(:mod:`src.outputs.first_party`): never beta-gated, never replaceable by an
installed copy. They are deliberately **not** in ``plugins/``: a plugin
bundled there always wins over an installed copy, so the externally
released versions could never update them (plan D8). The next step moves
each into its own repository and seeds the image from the pinned commit
(``outputs.lock.json``), at which point this directory goes away.
"""
