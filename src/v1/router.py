"""The single ``/v1`` router every v1 module attaches its routes to.

One tag, ``v1``, for the whole surface: the point of this API is that a
consumer sees one small coherent thing rather than twenty-two internal
domains. The tag is also what opts the surface into the conventions ratchet
(``tests/conventions_manifest.json``).
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/v1", tags=["v1"])
