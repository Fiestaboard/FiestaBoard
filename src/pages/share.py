"""Page share string encoding and decoding.

A share string is a base64url-encoded JSON envelope:
  {"v": 1, "page": {<content fields>}}

The "v" field is the envelope version, independent of the internal
page schema_version. It only needs to bump when the envelope structure
itself changes.
"""

import base64
import json

from .models import Page

SHARE_VERSION = 1

# Fields included in the share envelope (excludes runtime-only fields:
# id, created_at, updated_at, demo_plugin_id).
_SHARE_FIELDS = (
    "name",
    "type",
    "device_type",
    "display_type",
    "rows",
    "template",
    "line_metadata",
    "duration_seconds",
    "transition_strategy",
    "transition_interval_ms",
    "transition_step_size",
)


def encode_page(page: Page) -> str:
    """Encode a Page into a portable share string."""
    data = page.model_dump()
    page_content = {k: data[k] for k in _SHARE_FIELDS if k in data}
    envelope = {"v": SHARE_VERSION, "page": page_content}
    json_bytes = json.dumps(envelope, separators=(",", ":")).encode()
    # Strip padding — urlsafe_b64decode accepts unpadded strings when we re-add it.
    return base64.urlsafe_b64encode(json_bytes).decode().rstrip("=")


def decode_page(share_string: str) -> dict:
    """Decode a share string into a page content dict.

    Raises ValueError with a user-friendly message on any parse failure.
    The returned dict can be passed directly to PageCreate(**dict).
    """
    padded = share_string + "=" * (-len(share_string) % 4)
    try:
        json_bytes = base64.urlsafe_b64decode(padded)
        envelope = json.loads(json_bytes)
    except Exception:
        raise ValueError("Invalid share string — could not decode.") from None

    if not isinstance(envelope, dict) or "v" not in envelope or "page" not in envelope:
        raise ValueError("Invalid share string — unrecognized format.")

    v = envelope["v"]
    if not isinstance(v, int) or v < 1:
        raise ValueError("Invalid share string — bad version field.")
    if v > SHARE_VERSION:
        raise ValueError(f"This share string requires FiestaBoard v{v} or later. Please update your installation.")

    page_data = envelope["page"]
    if not isinstance(page_data, dict):
        raise ValueError("Invalid share string — malformed page data.")

    return page_data
