"""What this hub may say about itself to a caller who has not signed in.

``GET /discover`` (fiestaboard.app/find) and the mDNS TXT record (TV and
phone discovery, H13 PR 3) both answer anyone on the network. They share one
rule for the install's friendly name (``general.instance_name``): it is told
only while sign-in is off, so an unauthenticated caller learns nothing
``/health`` does not already tell them. Signed-in apps get the name from the
authenticated pairing offer instead.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Any

logger = logging.getLogger(__name__)


def _general() -> Mapping[str, Any]:
    from src.config_manager import get_config_manager

    return get_config_manager().get_general()


def public_instance_name(read_general: Callable[[], Mapping[str, Any]] | None = None) -> str:
    """``general.instance_name`` (stripped), or ``""`` while sign-in is required.

    *read_general* is only called when sign-in is off; it defaults to the
    config manager's general settings.
    """
    from src.auth.service import auth_mode

    if auth_mode() != "disabled":
        return ""
    return str((read_general or _general)().get("instance_name") or "").strip()
