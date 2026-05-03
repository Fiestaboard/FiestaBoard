"""Tiny CLI shim used by entrypoint.sh to manage the HTTPS (Beta) cert.

Usage:
    python -m src.system.https_certs_cli ensure
    python -m src.system.https_certs_cli remove

``ensure`` generates the self-signed cert if it isn't already present;
``remove`` deletes it. Exit code is non-zero on failure.
"""

from __future__ import annotations

import logging
import sys

from . import https_certs


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="[https_certs_cli] %(levelname)s %(message)s",
    )


def main(argv: list[str] | None = None) -> int:
    _setup_logging()
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: https_certs_cli {ensure|remove}", file=sys.stderr)
        return 2

    cmd = args[0]
    if cmd == "ensure":
        try:
            https_certs.generate_cert()
        except Exception as e:  # noqa: BLE001 - surface to shell
            print(f"failed to generate cert: {e}", file=sys.stderr)
            return 1
        return 0
    if cmd == "remove":
        https_certs.remove_cert()
        return 0
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
