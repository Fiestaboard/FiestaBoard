"""Clean up after the retired HTTPS (Beta) feature.

Up to settings schema v4, turning on Settings → Beta → HTTPS made the
container entrypoint generate a self-signed certificate into
``<data>/certs/`` and switch nginx over to it. The feature is gone (settings
v5 drops ``beta.https_enabled``), so those files are dead weight — and a
private key nothing uses any more should not sit on disk.

Only the two files FiestaBoard generated are removed. Anything else a user
put in ``certs/`` is left alone, and the directory is removed only when it is
empty afterwards. Best-effort: a failure is logged, never raised, because
cleanup must not stop the API from booting.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

#: The cert pair the HTTPS (Beta) entrypoint generated, by file name.
GENERATED_CERT_FILES = ("fiestaboard.crt", "fiestaboard.key")


def remove_legacy_https_certs(data_dir: Path) -> int:
    """Delete the generated cert pair under ``data_dir/certs``.

    Returns how many files were removed.
    """
    cert_dir = Path(data_dir) / "certs"
    if not cert_dir.is_dir():
        return 0

    removed = 0
    for name in GENERATED_CERT_FILES:
        path = cert_dir / name
        try:
            if path.is_file():
                path.unlink()
                removed += 1
        except OSError as e:
            logger.warning("Could not remove leftover HTTPS file %s: %s", path, e)

    try:
        if not any(cert_dir.iterdir()):
            cert_dir.rmdir()
    except OSError as e:
        logger.debug("Leaving %s in place: %s", cert_dir, e)

    if removed:
        logger.info("Removed %d leftover HTTPS (Beta) certificate file(s) from %s", removed, cert_dir)
    return removed
