"""A random, stable identifier for this install, for ``GET /discover``.

fiestaboard.app/find can reach one board at several addresses (its IP, its
``.local`` name, ``localhost``) and needs to list it once. The identifier is
random rather than derived from anything on the machine, so it says nothing
about the install beyond "the same one as before".
"""

from __future__ import annotations

import logging
import os
import re
import secrets
import stat
from pathlib import Path

logger = logging.getLogger(__name__)

_FILENAME = ".install_id"
_VALID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def load_install_id(data_dir: Path) -> str:
    """Return this install's identifier, creating it on first use.

    Returns "" when it can be neither read nor written (a read-only data
    directory, say): the find page then falls back to listing by address.
    """
    path = data_dir / _FILENAME
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat.S_IRUSR | stat.S_IWUSR)
    except FileExistsError:
        pass
    except OSError:
        logger.warning("Could not create %s; /discover will report no install id", path)
        return ""
    else:
        with os.fdopen(fd, "w", encoding="ascii") as handle:
            handle.write(secrets.token_urlsafe(16))
    try:
        value = path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeDecodeError):
        return ""
    return value if _VALID.match(value) else ""
