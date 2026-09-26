"""Wire models for the ``/plugins`` API (Phase 2 §2, slice 4).

Why this domain does not alias its storage models the way ``collections``
does. A collection is the same object on disk and on the wire, so
``CollectionResponse = Collection`` is honest there. Nothing in the plugin
domain works like that:

* ``PluginDetail`` is **derived** — manifest fields, registry enablement,
  config-manager state and page-service state, assembled per request;
* its ``config`` is **masked** — every sensitive value is replaced by ``"***"``
  on the way out, so the wire model is deliberately *not* the stored model;
* ``env_overridden_keys`` exists only on the wire, and only to tell the client
  which keys it is looking at a placeholder for.

Aliasing a storage model here would have quietly declared the masked shape to
be the stored shape — the same conflation that let the #1743 masking
regression through. So the wire models are their own thing, and they say so.

Open-ended payloads (``PluginSummary``, ``RegistryEntry``,
``PluginManifestResponse``) set ``extra="allow"``: their contents are
plugin-authored and a strict model would silently *delete* fields a plugin
ships. The declared fields are the contract core knows about; the rest passes
through untouched.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ── Listing ─────────────────────────────────────────────────────────────────


class PluginSummary(BaseModel):
    """One row of ``GET /plugins``: registry metadata plus config status."""

    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    version: str = "unknown"
    description: str = ""
    author: str = "Unknown"
    enabled: bool = False
    icon: str | None = None
    category: str | None = None
    #: "data" or "transition" — the UI hides the enable toggle for transition
    #: plugins, which run whenever selected regardless of the flag.
    plugin_type: str = "data"
    fiestaboard_version: str = ""
    source: dict[str, Any] | None = None
    update_available: bool = False
    update_blocked_reason: str = ""
    supports_triggers: bool = False
    instance_label: str | None = None
    base_plugin_id: str | None = None
    settings_schema: dict[str, Any] = Field(default_factory=dict)
    #: Whether this plugin has a persisted configuration at all.
    configured: bool = False
    #: The stored configuration, **masked**. Never the raw secret.
    config: dict[str, Any] = Field(default_factory=dict)


class PluginListResponse(BaseModel):
    """``GET /plugins``."""

    plugins: list[PluginSummary]
    plugin_system_enabled: bool
    total: int
    enabled_count: int


# ── Variables ───────────────────────────────────────────────────────────────


class AllPluginVariablesResponse(BaseModel):
    """``GET /plugins/variables/all`` — the template editor's whole vocabulary."""

    variables: dict[str, Any]
    max_lengths: dict[str, Any]
    plugin_system_enabled: bool


class PluginVariablesResponse(BaseModel):
    """``GET /plugins/{plugin_id}/variables``."""

    plugin_id: str
    variables: dict[str, Any]
    max_lengths: dict[str, Any]
    color_rules_schema: dict[str, Any]


# ── Health ──────────────────────────────────────────────────────────────────


class FetchBreakerStatus(BaseModel):
    """One plugin's standing with the fetch circuit breaker.

    The breaker landed with the pool-starvation fix (#1884) and had no way to
    be observed until this slice: a plugin could be quarantined for minutes
    while the UI showed nothing but stale variables.
    """

    consecutive_timeouts: int
    quarantined: bool
    cooldown_remaining_seconds: float


class PluginErrorsResponse(BaseModel):
    """``GET /plugins/errors`` — why a plugin is not contributing data.

    Two independent reasons, deliberately in one payload because the UI asks
    one question ("what is wrong with my plugins?"): ``errors`` holds
    load-time failures (the plugin never imported), ``fetch_breakers`` holds
    run-time ones (it imported fine and then stopped answering).
    """

    errors: dict[str, list[str]]
    fetch_breakers: dict[str, FetchBreakerStatus] = Field(default_factory=dict)
    plugin_system_enabled: bool


# ── Marketplace registry ────────────────────────────────────────────────────


class RegistryEntry(BaseModel):
    """One entry of the curated plugin registry."""

    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    description: str = ""
    repository: str = ""
    branch: str = ""
    author: str = ""
    fiestaboard_version: str = ""
    icon: str = ""
    category: str = ""
    plugin_type: str = "data"
    installed: bool = False
    #: One-line board strip for the marketplace card, at most 15 tiles.
    teaser: str = ""
    #: Literal boards for the detail-page hero, one per declared shape.
    previews: list[dict[str, Any]] = Field(default_factory=list)


class RegistryListResponse(BaseModel):
    """``GET /plugins/registry``."""

    entries: list[RegistryEntry]
    plugin_system_enabled: bool


class PluginUpdatesResponse(BaseModel):
    """``GET /plugins/updates``.

    ``blocked`` maps plugin ids to the reason an upstream commit was *not*
    offered; those plugins appear in ``updates`` as ``False``, and the reason
    is what lets the UI say so rather than looking stuck.
    """

    updates: dict[str, bool]
    blocked: dict[str, str]


class PluginUpdateCheckResponse(BaseModel):
    """``POST /plugins/updates/check``."""

    checked: int
    updates_available: list[str]


class PluginUpdatesApplyResponse(BaseModel):
    """``POST /plugins/updates/apply`` — deliberately partial-success.

    A bulk update of N plugins can succeed for some and fail for others;
    collapsing that into one status code would throw away which was which.
    """

    updated: list[str]
    failed: dict[str, str]
    message: str


# ── Detail ──────────────────────────────────────────────────────────────────


class PluginInstanceInfo(BaseModel):
    """One named instance of a plugin."""

    model_config = ConfigDict(extra="allow")

    label: str
    key: str | None = None
    enabled: bool = False
    has_config: bool = False


class PluginDetail(BaseModel):
    """``GET /plugins/{plugin_id}`` — derived, masked, and its own model.

    ``config`` is the **stored** configuration with sensitive values masked,
    deliberately *without* the env-var overlay: this response feeds the
    settings form, and any value baked in here comes straight back in the next
    save, so serving the overlay would freeze env values into ``config.json``
    (#1864 review). Which keys the environment currently controls is reported
    separately in ``env_overridden_keys``, values excluded.
    """

    id: str
    name: str
    version: str
    description: str = ""
    author: str = ""
    icon: str | None = None
    category: str | None = None
    plugin_type: str = "data"
    enabled: bool
    #: Stored config, masked. Never the raw secret, never the env value.
    config: dict[str, Any]
    #: Config keys whose live value currently comes from an env var. The
    #: values themselves are deliberately NOT in ``config``.
    env_overridden_keys: list[str]
    settings_schema: dict[str, Any]
    variables: dict[str, Any]
    max_lengths: dict[str, Any]
    env_vars: list[Any]
    documentation: str | None = None
    has_demo: bool
    demo_page_id: str | None = None
    instance_label: str | None = None
    base_plugin_id: str | None = None
    instances: list[PluginInstanceInfo]


class PluginManifestResponse(BaseModel):
    """``GET /plugins/{plugin_id}/manifest`` — the raw manifest, passed through.

    Manifests are plugin-authored and open-ended, so this declares the fields
    core relies on and lets everything else through untouched.
    """

    model_config = ConfigDict(extra="allow")

    name: str | None = None
    version: str | None = None
    settings_schema: dict[str, Any] = Field(default_factory=dict)
    variables: dict[str, Any] = Field(default_factory=dict)
    max_lengths: dict[str, Any] = Field(default_factory=dict)


# ── Config / enablement ─────────────────────────────────────────────────────


class PluginConfigRequest(BaseModel):
    """Body of ``PUT /plugins/{plugin_id}/config``.

    ``config`` stays a free-form map on purpose: its schema is the *plugin's*
    ``settings_schema``, validated by the registry against that manifest, and
    a typed model here could only be a lie. It is also the field that carries
    the ``"***"`` sentinel back from the settings form, which any tightening
    would have to keep accepting.
    """

    config: dict[str, Any]


class PluginConfigUpdateResponse(BaseModel):
    """``PUT /plugins/{plugin_id}/config`` — the stored config, re-masked."""

    plugin_id: str
    config: dict[str, Any]


class PluginEnablementResponse(BaseModel):
    """``POST /plugins/{plugin_id}/enable`` and ``/disable``."""

    plugin_id: str
    enabled: bool


# ── Data ────────────────────────────────────────────────────────────────────


class PluginDataResponse(BaseModel):
    """``GET /plugins/{plugin_id}/data``."""

    plugin_id: str
    available: bool
    data: dict[str, Any] | None = None
    formatted_lines: list[str] | None = None
    error: str | None = None


# ── Remote options ──────────────────────────────────────────────────────────


class PluginOption(BaseModel):
    """One selectable choice returned by a plugin's ``get_options()``."""

    value: str | int | float | bool
    label: str
    description: str | None = None
    group: str | None = None
    preview: str | None = None
    disabled: bool = False
    meta: dict[str, Any] | None = None


class PluginOptionsRequest(BaseModel):
    """Body for ``POST /plugins/{plugin_id}/options/{options_id}``.

    POST rather than GET on purpose: ``parent`` holds arbitrary JSON, and
    ``draft_config`` carries credentials that must never reach a URL, an
    access log, or browser history.
    """

    parent: dict[str, Any] = Field(default_factory=dict)
    query: str = ""
    limit: int = 200
    cursor: str | None = None
    refresh: bool = False
    draft_config: dict[str, Any] = Field(default_factory=dict)


class PluginOptionsResponse(BaseModel):
    """``POST /plugins/{plugin_id}/options/{options_id}``.

    ``error`` is a *hint*, not an incident: "no API key yet" is the expected
    state while a settings form is still being filled in, so it rides along
    with a 200 and the widget shows it inline next to the field. That is the
    documented ``no_200_on_failure`` exception for this route.
    """

    plugin_id: str
    options_id: str
    options: list[PluginOption]
    has_more: bool
    cursor: str | None
    total: int | None
    error: str | None
    cached: bool
    stale: bool
    cache_seconds: int


# ── Demo pages ──────────────────────────────────────────────────────────────


class PluginDemoPageResponse(BaseModel):
    """``GET /plugins/{plugin_id}/demo-page``."""

    exists: bool
    page_id: str | None
    has_demo_template: bool


class PluginDemoPageCreateResponse(BaseModel):
    """``POST /plugins/{plugin_id}/demo-page``.

    ``recreated`` replaces the old ``status: "created" | "recreated"`` string:
    the demo page is a singleton per plugin + device type, so a second call
    replaces the first, and the caller needs the verb for its toast. A boolean
    says that without a status envelope.
    """

    recreated: bool
    page: dict[str, Any]


# ── Instances ───────────────────────────────────────────────────────────────


class PluginInstanceCreateRequest(BaseModel):
    """Body of ``POST /plugins/{plugin_id}/instances``."""

    label: str


class PluginInstancesResponse(BaseModel):
    """``GET /plugins/{plugin_id}/instances``."""

    plugin_id: str
    instances: list[PluginInstanceInfo]
    total: int


class PluginInstanceResponse(BaseModel):
    """``POST``/``DELETE`` on ``/plugins/{plugin_id}/instances``.

    ``instance_label`` is the *normalized* label — the one the registry holds
    and the one ``{{plugin:label.field}}`` template references must use, which
    is not always the string the caller sent.
    """

    plugin_id: str
    instance_label: str
    instance_key: str


# ── Webhooks ────────────────────────────────────────────────────────────────


class PluginReceiveResponse(BaseModel):
    """``POST /plugins/{plugin_id}/receive``.

    The ``status`` key survives the conventions pass on purpose: this endpoint
    is a **webhook target for third-party systems** (CI pipelines, home
    automations) that this repo does not control and cannot update in lockstep.
    "Deprecation, never deletion" applies to it more literally than to any
    browser-facing route. ``plugin_id`` is added so the ack names what it
    acked.
    """

    status: Literal["ok"] = "ok"
    plugin_id: str


# ── Install / uninstall / update ────────────────────────────────────────────


class ExternalPluginInstallRequest(BaseModel):
    """Body of ``POST /plugins/install``."""

    repository: str
    plugin_id: str | None = None
    branch: str = ""


class PluginInstallResponse(BaseModel):
    """``POST /plugins/install`` and ``POST /plugins/registry/{id}/install``."""

    plugin_id: str
    message: str


class PluginUninstallResponse(BaseModel):
    """``DELETE /plugins/{plugin_id}/uninstall``."""

    plugin_id: str
    message: str


class PluginUpdateResponse(BaseModel):
    """``POST /plugins/{plugin_id}/update``."""

    plugin_id: str
    message: str
