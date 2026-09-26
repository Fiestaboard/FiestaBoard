"""FastAPI router for the two ``/mqtt`` endpoints.

``GET /mqtt/status`` (is the live client connected and processing commands)
and ``POST /mqtt/republish-discovery`` (make Home Assistant re-read the entity
set after the page list changed).

Phase 2, Task 8 — the last untagged routes. Moved out of ``src/api_server.py``
and converted to ``docs/internal/reference/API_CONVENTIONS.md``: a declared
``response_model`` on both routes, the ``{"status": "ok"}`` envelope replaced
by a bare body, and the failure codes declared in ``responses=``.

The MQTT client singleton already had a canonical home
(``src.mqtt.get_mqtt_client``), so this module imports nothing from
``src.api_server``. ``_apply_mqtt_config`` deliberately stayed there: it is
boot/settings wiring that the settings surface calls, not an endpoint.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from src.api_errors import errors

from .models import MqttRepublishResponse, MqttStatusResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["mqtt"])


@router.get("/mqtt/status", response_model=MqttStatusResponse, responses=errors(500))
async def get_mqtt_status():
    """Return the current MQTT connection status.

    Useful for UI display and for tests to determine whether the live MQTT
    client (not just the one-off discovery script) is connected and able to
    process commands.
    """
    from . import get_mqtt_client

    try:
        client = get_mqtt_client()
        if client is None:
            return MqttStatusResponse(enabled=False, connected=False, running=False)
        return MqttStatusResponse(
            enabled=True,
            connected=client.is_connected(),
            running=client.is_running(),
        )
    except Exception as e:
        # ``enabled: False`` is a real answer ("MQTT is switched off"), so it
        # must never double as "we could not tell" — the two were identical
        # before #1887 and an operator debugging a broken broker saw the
        # same body as one who had simply not enabled MQTT.
        logger.error(f"Failed to read MQTT status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to read MQTT status.") from e


@router.post("/mqtt/republish-discovery", response_model=MqttRepublishResponse, responses=errors(500, 503))
async def mqtt_republish_discovery():
    """Re-publish MQTT discovery messages for all entities.

    Useful when the page list changes after the MQTT client first connected,
    or to force HA to refresh entity options (e.g. Active Page select options).
    Returns 503 if MQTT is not connected.
    """
    from . import get_mqtt_client

    try:
        client = get_mqtt_client()
    except Exception as e:
        logger.error(f"Failed to resolve the MQTT client: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to resolve the MQTT client.") from e

    if client is None or not client.is_connected():
        raise HTTPException(status_code=503, detail="MQTT client not connected")

    try:
        client.publish_discovery()
    except Exception as e:
        logger.error(f"Failed to republish MQTT discovery: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to republish discovery messages.") from e
    return MqttRepublishResponse(message="Discovery messages republished")
