"""Page share string encoding and decoding.

A share string is a base64url-encoded JSON envelope:
  {"v": 1, "page": {<content fields>}}

The "v" field is the envelope version, independent of the internal
page schema_version. Grid pages encode with ``SHARE_VERSION`` (1) so
older builds keep importing them. Flexible pages encode with
``SHARE_VERSION_FLEXIBLE`` (2), so an older build refuses them with its
"requires FiestaBoard v2 or later" message instead of a validation error.
"""

import base64
import json

from .document import PAGE_SHARE_EXCLUDED
from .models import Page

SHARE_VERSION = 1
SHARE_VERSION_FLEXIBLE = 2


def encode_page(page: Page) -> str:
    """Encode a Page into a portable share string."""
    data = page.model_dump()
    page_content = {k: v for k, v in data.items() if k not in PAGE_SHARE_EXCLUDED}
    v = SHARE_VERSION_FLEXIBLE if page.type == "flexible" else SHARE_VERSION
    envelope = {"v": v, "page": page_content}
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
    if v > SHARE_VERSION_FLEXIBLE:
        raise ValueError(f"This share string requires FiestaBoard v{v} or later. Please update your installation.")

    page_data = envelope["page"]
    if not isinstance(page_data, dict):
        raise ValueError("Invalid share string — malformed page data.")

    return page_data
