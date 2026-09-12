"""Central resolution of FiestaBoard's writable data directory.

Every store historically resolved ``<repo>/data`` on its own via
``Path(__file__)`` gymnastics (eleven independent copies). This module is
the one seam: production resolves the same default, tests set
``FIESTABOARD_DATA_DIR`` to a tmp_path, and containers may pin it.
"""

import os
from pathlib import Path


def get_data_dir() -> Path:
    """Return the data directory, creating it if needed.

    Resolution: ``FIESTABOARD_DATA_DIR`` env var if set, else
    ``<repo-root>/data`` (this file's parent's parent / "data").
    Read fresh on every call — never cached at import time — so tests
    and runtime reconfiguration work without reload gymnastics.
    """
    env = os.environ.get("FIESTABOARD_DATA_DIR", "").strip()
    base = Path(env) if env else Path(__file__).resolve().parent.parent / "data"
    base.mkdir(parents=True, exist_ok=True)
    return base
