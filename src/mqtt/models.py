"""Wire models for the ``/mqtt`` endpoints (Phase 2, Task 8)."""

from __future__ import annotations

from pydantic import BaseModel


class MqttStatusResponse(BaseModel):
    """``GET /mqtt/status``.

    ``enabled: false`` is a real answer — "MQTT is switched off" — so it must
    never double as "we could not tell". The two were indistinguishable before
    #1887; the unknown case is now a 500.
    """

    enabled: bool
    connected: bool
    running: bool


class MqttRepublishResponse(BaseModel):
    """``POST /mqtt/republish-discovery``."""

    message: str
