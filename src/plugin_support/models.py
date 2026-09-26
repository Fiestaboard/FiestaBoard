"""Wire models for the plugin-support endpoints (Phase 2, Task 8)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class HomeAssistantEntity(BaseModel):
    """One entity as the picker consumes it.

    Flattened from Home Assistant's ``/api/states``: ``friendly_name`` is
    lifted out of ``attributes`` (falling back to the entity id) so the picker
    always has a label, and ``attributes`` is normalized to ``{}`` because HA
    may send it as null.
    """

    entity_id: str
    state: str
    attributes: dict[str, Any] = {}
    friendly_name: str


class HomeAssistantEntitiesResponse(BaseModel):
    """``GET /home-assistant/entities``."""

    entities: list[HomeAssistantEntity]


class HeaderPair(BaseModel):
    """One request header for the test fetch, before interpolation."""

    name: str | None = None
    value: str | None = None


class GenericDataTestFetchRequest(BaseModel):
    """Body of ``POST /generic-data/test-fetch``.

    Mirrors what the JSON-path mapper's "Test & Preview" button sends. Every
    field but ``url`` is optional and keeps the default the hand-rolled
    ``request.get(...)`` chain used before this model existed.
    """

    url: str = ""
    format: str = "json"
    method: str = "GET"
    headers: list[HeaderPair] = []
    body: str | None = None


class GenericDataTestFetchResponse(BaseModel):
    """``POST /generic-data/test-fetch`` — the parsed document to map against.

    ``ok`` is always ``True``: every failure path is a status code
    (400/500/502/504), never a body with ``ok: false``. It is kept because the
    web client reads it and the endpoint is a preview surface a third-party
    integration may also poll.
    """

    ok: bool = True
    data: Any
