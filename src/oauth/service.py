"""OAuth for plugins: start a flow, finish it, keep the tokens fresh.

A plugin declares its provider in ``manifest.json`` (``src/oauth/provider.py``)
and asks for a token with ``self.get_oauth_token()``. Everything in between is
here.

Two flows, chosen per plugin:

``relay``
    Authorization code with PKCE. A board on a LAN cannot be an OAuth redirect
    target, so the provider redirects to a static page at a fixed public
    address, which passes the browser on to the board
    (https://github.com/Fiestaboard/auth). The relay learns which board from
    ``state``, where this module puts the address the user is browsing the
    board at. It sees the code but not the PKCE verifier, which never leaves
    this process.

``device``
    Device authorization grant (RFC 8628). The user types a short code on
    another device and the board polls for the result. No relay involved.

A connection belongs to one plugin instance and is keyed by its registry key,
so two plugins never share tokens even when they use the same provider.
"""

from __future__ import annotations

import logging
import os
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any, Protocol
from urllib.parse import urlencode, urlsplit, urlunsplit

from src.paths import get_data_dir

from . import pkce, plex
from .client import ProviderClient, TokenResponse
from .errors import (
    ConnectionNotConfigured,
    ConnectionNotFound,
    FlowNotSupported,
    InvalidBoardUrl,
    InvalidState,
    PastedCodeRejected,
    ProviderError,
    TokenEndpointError,
)
from .provider import (
    CLIENT_ID_FLOWS,
    FLOW_DEVICE,
    FLOW_KEY_EXCHANGE,
    FLOW_PLEX_PIN,
    FLOW_RELAY,
    Endpoints,
    OAuthProvider,
    parse_provider_block,
)
from .paste import parse_pasted
from .state import STATE_TTL_SECONDS, StatePayload, StateSigner, load_state_key
from .tokens import TokenSet, TokenStore

logger = logging.getLogger(__name__)

#: Where every provider is told to send the browser. Registered verbatim in
#: each OAuth app, so it must never change — see the relay repo's README.
#: 9.5.0 through 9.7.x sent this with ``.html`` on the end. The relay serves
#: both forms, and must keep doing so: apps registered by users of those
#: releases still name the old one.
DEFAULT_REDIRECT_URI = "https://fiestaboard.app/auth/oauth/redirect"
REDIRECT_URI_ENV = "FIESTABOARD_OAUTH_REDIRECT_URI"

#: Refresh this long before the access token actually expires, so a plugin is
#: never handed a token that dies mid-request.
REFRESH_MARGIN_SECONDS = 60
#: RFC 8628 §3.5: on ``slow_down``, add five seconds to the polling interval.
SLOW_DOWN_SECONDS = 5
#: Started-but-unfinished relay flows kept at once. A person starts one at a
#: time; the cap only bounds memory if something keeps starting them.
MAX_PENDING_AUTHORIZATIONS = 50

#: Refresh failures that mean the grant is gone and only the user can fix it.
_REAUTHORIZE_ERRORS = frozenset({"invalid_grant", "invalid_client", "unauthorized_client"})

STATUS_CONNECTED = "connected"
STATUS_DISCONNECTED = "disconnected"
STATUS_REAUTHORIZE = "reauthorization_required"

DEVICE_PENDING = "pending"
DEVICE_EXPIRED = "expired"
DEVICE_DENIED = "denied"
DEVICE_FAILED = "failed"


def configured_redirect_uri() -> str:
    """The redirect URI in force: the env override, else the public relay."""
    return os.environ.get(REDIRECT_URI_ENV, "").strip() or DEFAULT_REDIRECT_URI


MAX_BOARD_URL_LENGTH = 512


def normalize_board_url(board_url: str | None) -> str:
    """Return *board_url* in the plain form the relay expects, or raise.

    Only the shape is checked here: a web address with nothing after the path.
    Whether it is a *local* address is the relay's rule to enforce, in one
    place, for every board — duplicating that list here would let the two
    drift.
    """
    text = (board_url or "").strip()
    if not text or len(text) > MAX_BOARD_URL_LENGTH:
        raise InvalidBoardUrl("The board's own address is needed to finish a sign-in, and none was sent.")
    try:
        parts = urlsplit(text)
        has_host = bool(parts.hostname)
        _ = parts.port  # raises ValueError for a malformed port
    except ValueError as exc:
        raise InvalidBoardUrl("The board's own address is not a valid web address.") from exc
    plain = parts.scheme in ("http", "https") and has_host and not (parts.username or parts.password)
    if not plain or parts.query or parts.fragment or "?" in text or "#" in text:
        raise InvalidBoardUrl("The board's own address is not a plain web address.")
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def _with_query(url: str, params: dict[str, str]) -> str:
    """*url* with *params* appended, keeping any query it already has."""
    separator = "&" if urlsplit(url).query else "?"
    return f"{url}{separator}{urlencode(params)}"


# ── What the service needs to know about plugins ────────────────────────────


@dataclass(frozen=True)
class ConnectionTarget:
    """One plugin instance that declares an OAuth connection."""

    connection_id: str
    plugin_id: str
    instance_label: str | None
    plugin_name: str
    provider: OAuthProvider
    config: dict[str, Any] = field(default_factory=dict)

    @property
    def client_id(self) -> str:
        return self.provider.resolve_client_id(self.config)

    @property
    def client_secret(self) -> str:
        return self.provider.resolve_client_secret(self.config)

    def endpoints(self) -> Endpoints:
        """The provider's endpoints for this instance; raises :class:`ConnectionNotConfigured`."""
        return self.provider.resolve_endpoints(self.config)

    @property
    def configured(self) -> bool:
        """Whether a flow can start: a client ID where one is needed, and usable endpoints."""
        if self.provider.needs_client_id and not self.client_id:
            return False
        try:
            self.endpoints()
        except ConnectionNotConfigured:
            return False
        return True


class ConnectionSource(Protocol):
    """Where connection targets come from. Production reads the plugin registry."""

    def get(self, connection_id: str) -> ConnectionTarget | None:
        """The target for *connection_id*, or ``None`` if no plugin declares one."""

    def all(self) -> list[ConnectionTarget]:
        """Every installed plugin instance that declares an OAuth connection."""

    def id_for(self, plugin: object) -> str | None:
        """The registry key *plugin* is installed under, or ``None``."""

    def invalidate(self, connection_id: str) -> None:
        """Drop the plugin's cached results, so its next fetch sees the new sign-in state."""


class RegistryConnectionSource:
    """Connection targets derived from installed plugins' manifests."""

    @staticmethod
    def _registry() -> Any:
        # Imported here: src.plugins.manifest imports this package to validate
        # the manifest block, so a module-level import would be circular.
        from src.plugins.registry import get_plugin_registry

        return get_plugin_registry()

    def get(self, connection_id: str) -> ConnectionTarget | None:
        registry = self._registry()
        manifest = registry.get_manifest(connection_id)
        if manifest is None:
            return None
        provider = parse_provider_block(manifest.raw.get("oauth"), manifest.name, manifest.settings_schema)
        if provider is None:
            return None
        plugin_id, instance_label = registry.parse_instance_key(connection_id)
        name = f"{manifest.name} ({instance_label})" if instance_label else manifest.name
        return ConnectionTarget(
            connection_id=connection_id,
            plugin_id=plugin_id,
            instance_label=instance_label,
            plugin_name=name,
            provider=provider,
            config=dict(registry.get_plugin_config(connection_id) or {}),
        )

    def all(self) -> list[ConnectionTarget]:
        targets = (self.get(connection_id) for connection_id in self._registry().plugins)
        return sorted((t for t in targets if t is not None), key=lambda t: t.plugin_name.lower())

    def id_for(self, plugin: object) -> str | None:
        # A plugin object does not know the key it is registered under (an
        # instance shares its class and manifest with the base plugin), so
        # find it by identity.
        for connection_id, candidate in self._registry().plugins.items():
            if candidate is plugin:
                return connection_id
        return None

    def invalidate(self, connection_id: str) -> None:
        plugin = self._registry().plugins.get(connection_id)
        if plugin is not None:
            plugin.clear_cache()


# ── What the service reports ────────────────────────────────────────────────


@dataclass(frozen=True)
class DeviceStatus:
    """A device-code flow as the UI needs to see it. Never the device code itself."""

    status: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    expires_at: float
    detail: str = ""


@dataclass(frozen=True)
class ConnectionStatus:
    """A connection as the UI needs to see it. Never a token."""

    id: str
    plugin_id: str
    instance_label: str | None
    plugin_name: str
    provider_name: str
    flows: tuple[str, ...]
    configured: bool
    #: Whether the user registers their own app with the provider (the plugin
    #: offers a client ID field). False when the plugin brings its own app.
    user_app: bool
    #: The settings keys the user's client ID and secret are saved under, when
    #: the plugin offers those fields. The UI renders them inside the guided
    #: setup instead of the general settings form.
    client_id_setting: str | None
    client_secret_setting: str | None
    #: The provider's developer page, where the user creates their app.
    app_setup_url: str
    status: str
    scopes: tuple[str, ...]
    expires_at: float | None
    connected_at: float | None
    device: DeviceStatus | None


@dataclass(frozen=True)
class AuthorizationStart:
    """What the UI needs to carry a just-started flow forward."""

    flow: str
    authorization_url: str = ""
    device: DeviceStatus | None = None
    #: The sign-in will not come back on its own; the user pastes what the
    #: provider shows them (``complete_pasted``).
    paste_expected: bool = False
    paste_hint: str = ""


@dataclass(frozen=True)
class CallbackOutcome:
    """How a relay callback ended. ``reason`` is a slug safe for a URL."""

    connected: bool
    connection_id: str | None = None
    reason: str = ""


# ── In-memory flow state ────────────────────────────────────────────────────


@dataclass(frozen=True)
class _PendingAuthorization:
    """A relay flow between "sent to the provider" and "came back"."""

    connection_id: str
    code_verifier: str
    redirect_uri: str
    token_url: str
    client_id: str
    client_secret: str
    scopes: tuple[str, ...]
    expires_at: float
    client_id_param: str = "client_id"
    flow: str = FLOW_RELAY
    #: Whether a pasted code with no ``state`` may finish this flow. Only a
    #: flow that never sent a ``state`` (headless key_exchange) sets it.
    allow_bare_code: bool = False
    #: Whether a ``client_id`` in the pasted address replaces ours (providers
    #: that issue a client during sign-in). Never from a callback query.
    accept_issued_client_id: bool = False
    #: Extra fields for the code exchange (a ``resource`` indicator, say).
    extra_token_params: dict[str, str] = field(default_factory=dict)


@dataclass
class _DeviceFlow:
    """A device flow being polled. Mutated only under the service lock."""

    connection_id: str
    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    token_url: str
    client_id: str
    client_secret: str
    scopes: tuple[str, ...]
    expires_at: float
    interval: int
    status: str = DEVICE_PENDING
    detail: str = ""
    client_id_param: str = "client_id"
    #: Extra fields every token poll sends (Twitch: the scopes again).
    poll_form: dict[str, str] = field(default_factory=dict)
    #: ``device`` (RFC 8628) or ``plex_pin`` (``device_code`` is the PIN id,
    #: ``client_id`` the install's Plex client identifier).
    kind: str = FLOW_DEVICE
    plex_product: str = ""

    def to_status(self) -> DeviceStatus:
        return DeviceStatus(
            status=self.status,
            user_code=self.user_code,
            verification_uri=self.verification_uri,
            verification_uri_complete=self.verification_uri_complete,
            expires_at=self.expires_at,
            detail=self.detail,
        )


class OAuthService:
    """Runs OAuth flows for plugins and hands out fresh access tokens."""

    def __init__(
        self,
        *,
        source: ConnectionSource,
        store: TokenStore,
        signer: StateSigner,
        client: ProviderClient | None = None,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
        redirect_uri: str | None = None,
        poll_in_background: bool = True,
        plex_client_identifier: Callable[[], str] | None = None,
    ) -> None:
        self._source = source
        self._store = store
        self._signer = signer
        self._client = client or ProviderClient()
        self._clock = clock
        self._sleep = sleep
        self._redirect_uri = redirect_uri
        self._poll_in_background = poll_in_background
        self._plex_client_identifier = plex_client_identifier or (
            lambda: plex.load_client_identifier(get_data_dir())
        )
        self._lock = threading.RLock()
        self._pending: dict[str, _PendingAuthorization] = {}
        self._device: dict[str, _DeviceFlow] = {}
        self._refresh_locks: dict[str, threading.Lock] = {}

    # ── reads ───────────────────────────────────────────────────────────

    @property
    def redirect_uri(self) -> str:
        return self._redirect_uri or configured_redirect_uri()

    def _target(self, connection_id: str) -> ConnectionTarget:
        target = self._source.get(connection_id)
        if target is None:
            raise ConnectionNotFound(f"No OAuth connection for plugin: {connection_id}")
        return target

    def _status(self, target: ConnectionTarget) -> ConnectionStatus:
        tokens = self._store.get(target.connection_id)
        with self._lock:
            flow = self._device.get(target.connection_id)
            device = flow.to_status() if flow else None
        if tokens is None:
            status = STATUS_DISCONNECTED
        elif tokens.needs_reauthorization:
            status = STATUS_REAUTHORIZE
        else:
            status = STATUS_CONNECTED
        return ConnectionStatus(
            id=target.connection_id,
            plugin_id=target.plugin_id,
            instance_label=target.instance_label,
            plugin_name=target.plugin_name,
            provider_name=target.provider.name,
            flows=target.provider.flows,
            configured=target.configured,
            user_app=target.provider.user_client_id,
            client_id_setting=target.provider.client_id_setting if target.provider.user_client_id else None,
            client_secret_setting=(
                target.provider.client_secret_setting
                if target.provider.client_secret_setting and target.provider.user_client_secret
                else None
            ),
            app_setup_url=target.provider.app_setup_url,
            status=status,
            scopes=tokens.scopes if tokens else target.provider.scopes,
            expires_at=tokens.expires_at if tokens else None,
            connected_at=tokens.obtained_at if tokens else None,
            device=device,
        )

    def list_connections(self) -> list[ConnectionStatus]:
        """Every installed plugin that declares an OAuth connection."""
        return [self._status(target) for target in self._source.all()]

    def get_connection(self, connection_id: str) -> ConnectionStatus:
        return self._status(self._target(connection_id))

    # ── starting a flow ─────────────────────────────────────────────────

    def start(
        self,
        connection_id: str,
        flow: str | None = None,
        board_url: str | None = None,
        headless: bool = False,
    ) -> AuthorizationStart:
        """Start connecting *connection_id*, with its preferred flow unless told otherwise.

        *board_url* is the address the user is browsing this board at. The
        relay flow needs it (it is where the browser must come back to); the
        device flow ignores it. ``key_exchange`` without one, or with
        *headless*, asks the provider to show a code for the user to paste.
        """
        target = self._target(connection_id)
        chosen = flow or target.provider.flows[0]
        if chosen not in target.provider.flows:
            raise FlowNotSupported(f"{target.plugin_name} does not support the {chosen!r} sign-in flow.")
        if chosen in CLIENT_ID_FLOWS and not target.client_id:
            raise ConnectionNotConfigured(
                f"{target.plugin_name} needs a client ID before it can connect. "
                f"Enter one in the plugin's settings and save."
            )
        endpoints = target.endpoints()
        if chosen == FLOW_DEVICE:
            return self._start_device(target, endpoints)
        if chosen == FLOW_KEY_EXCHANGE:
            headless = headless or board_url is None
            return self._start_key_exchange(target, None if headless else normalize_board_url(board_url), endpoints)
        if chosen == FLOW_PLEX_PIN:
            return self._start_plex(target, normalize_board_url(board_url) if board_url else "")
        return self._start_relay(target, normalize_board_url(board_url), endpoints)

    def _start_relay(self, target: ConnectionTarget, board_url: str, endpoints: Endpoints) -> AuthorizationStart:
        now = self._clock()
        verifier = pkce.generate_verifier()
        nonce = secrets.token_urlsafe(16)
        expires_at = int(now) + STATE_TTL_SECONDS
        redirect_uri = self.redirect_uri
        provider = target.provider

        pending = _PendingAuthorization(
            connection_id=target.connection_id,
            code_verifier=verifier,
            redirect_uri=redirect_uri,
            token_url=endpoints.token_url,
            client_id=target.client_id,
            client_secret=target.client_secret,
            scopes=provider.scopes,
            expires_at=expires_at,
            client_id_param=provider.client_id_param,
        )
        with self._lock:
            self._prune_pending(now)
            self._pending[nonce] = pending

        params = {
            **provider.authorization_params,
            "response_type": "code",
            provider.client_id_param: target.client_id,
            "redirect_uri": redirect_uri,
            "state": self._signer.sign(StatePayload(nonce, target.connection_id, expires_at, board_url)),
            "code_challenge": pkce.challenge_for(verifier),
            "code_challenge_method": pkce.CHALLENGE_METHOD,
        }
        if provider.scopes:
            params["scope"] = provider.joined_scopes()
        return AuthorizationStart(flow=FLOW_RELAY, authorization_url=_with_query(endpoints.authorization_url, params))

    def _start_key_exchange(
        self, target: ConnectionTarget, board_url: str | None, endpoints: Endpoints
    ) -> AuthorizationStart:
        """PKCE for an API key (OpenRouter). No client ID; *board_url* ``None`` means headless."""
        now = self._clock()
        verifier = pkce.generate_verifier()
        nonce = secrets.token_urlsafe(16)
        expires_at = int(now) + STATE_TTL_SECONDS
        headless = board_url is None
        pending = _PendingAuthorization(
            connection_id=target.connection_id,
            code_verifier=verifier,
            redirect_uri=self.redirect_uri,
            token_url=endpoints.token_url,
            client_id="",
            client_secret="",
            scopes=(),
            expires_at=expires_at,
            flow=FLOW_KEY_EXCHANGE,
            allow_bare_code=headless,
        )
        with self._lock:
            self._prune_pending(now)
            self._pending[nonce] = pending

        params = dict(target.provider.authorization_params)
        if not headless:
            params["callback_url"] = self.redirect_uri
        params["code_challenge"] = pkce.challenge_for(verifier)
        params["code_challenge_method"] = pkce.CHALLENGE_METHOD
        if not headless:
            params["state"] = self._signer.sign(StatePayload(nonce, target.connection_id, expires_at, board_url))
        return AuthorizationStart(
            flow=FLOW_KEY_EXCHANGE,
            authorization_url=_with_query(endpoints.authorization_url, params),
            paste_expected=headless,
            paste_hint=(
                f"After you approve, {target.provider.name} shows a code. Copy it and paste it here."
                if headless
                else ""
            ),
        )

    def _start_plex(self, target: ConnectionTarget, board_url: str) -> AuthorizationStart:
        """Create a Plex PIN, send the browser to approve it, and poll for its token."""
        client_identifier = self._plex_client_identifier()
        product = target.provider.plex_product
        now = self._clock()
        pin = plex.create_pin(self._client.http, client_identifier, product, now)
        forward_url = f"{board_url}/integrations?{urlencode({'plugin': target.connection_id})}" if board_url else ""
        url = plex.auth_url(client_identifier, pin.code, product, forward_url)
        flow = _DeviceFlow(
            connection_id=target.connection_id,
            device_code=pin.id,
            user_code="",
            verification_uri=url,
            verification_uri_complete="",
            token_url="",
            client_id=client_identifier,
            client_secret="",
            scopes=(),
            expires_at=now + pin.expires_in,
            interval=plex.POLL_INTERVAL_SECONDS,
            kind=FLOW_PLEX_PIN,
            plex_product=product,
        )
        self._begin_polling(flow)
        return AuthorizationStart(flow=FLOW_PLEX_PIN, authorization_url=url, device=flow.to_status())

    def _begin_polling(self, flow: _DeviceFlow) -> None:
        with self._lock:
            # Replacing the entry retires any earlier flow: its poller sees it
            # is no longer the current one and stops.
            self._device[flow.connection_id] = flow
        if self._poll_in_background:
            threading.Thread(
                target=self._poll_device_until_done,
                args=(flow,),
                name=f"oauth-device-{flow.connection_id}",
                daemon=True,
            ).start()

    def _prune_pending(self, now: float) -> None:
        """Drop expired flows, then the oldest beyond the cap. Caller holds the lock."""
        for nonce in [n for n, p in self._pending.items() if now >= p.expires_at]:
            del self._pending[nonce]
        while len(self._pending) >= MAX_PENDING_AUTHORIZATIONS:
            del self._pending[next(iter(self._pending))]

    def _start_device(self, target: ConnectionTarget, endpoints: Endpoints) -> AuthorizationStart:
        provider = target.provider
        authorization = self._client.start_device_authorization(
            endpoints.device_authorization_url,
            client_id=target.client_id,
            scopes=provider.scopes,
            client_id_param=provider.client_id_param,
            scope_param=provider.device_scope_param,
            scope_separator=provider.scope_separator,
        )
        poll_form = (
            {provider.device_scope_param: provider.joined_scopes()}
            if provider.device_poll_scope and provider.scopes
            else {}
        )
        flow = _DeviceFlow(
            connection_id=target.connection_id,
            device_code=authorization.device_code,
            user_code=authorization.user_code,
            verification_uri=authorization.verification_uri,
            verification_uri_complete=authorization.verification_uri_complete,
            token_url=endpoints.token_url,
            client_id=target.client_id,
            client_secret=target.client_secret,
            scopes=provider.scopes,
            expires_at=self._clock() + authorization.expires_in,
            interval=authorization.interval,
            client_id_param=provider.client_id_param,
            poll_form=poll_form,
        )
        self._begin_polling(flow)
        return AuthorizationStart(flow=FLOW_DEVICE, device=flow.to_status())

    # ── finishing the relay flow ────────────────────────────────────────

    def complete_authorization(self, *, state: str | None, code: str | None, error: str | None) -> CallbackOutcome:
        """Finish a relay flow from the query the provider sent back.

        Never raises for a bad callback: the caller is a browser mid-redirect
        and the only useful thing to do is send it somewhere that explains.
        """
        now = self._clock()
        try:
            payload = self._signer.verify(state, now)
        except InvalidState as exc:
            logger.warning("Rejected OAuth callback: %s", exc)
            return CallbackOutcome(connected=False, reason=exc.reason)

        # Popping is what makes a state single-use: a second callback with the
        # same value finds nothing, whatever happened to the first.
        with self._lock:
            pending = self._pending.pop(payload.nonce, None)
        if pending is None or pending.connection_id != payload.connection_id:
            logger.warning("Rejected OAuth callback for %s: state already used or unknown", payload.connection_id)
            return CallbackOutcome(connected=False, connection_id=payload.connection_id, reason="invalid_state")

        connection_id = pending.connection_id
        if error:
            reason = "access_denied" if error == "access_denied" else "provider_error"
            logger.info("OAuth sign-in for %s was not completed: %s", connection_id, reason)
            return CallbackOutcome(connected=False, connection_id=connection_id, reason=reason)
        if not code:
            return CallbackOutcome(connected=False, connection_id=connection_id, reason="provider_error")

        try:
            self._finish_pending(pending, code)
        except (TokenEndpointError, ProviderError) as exc:
            logger.error("OAuth code exchange for %s failed: %s", connection_id, exc)
            return CallbackOutcome(connected=False, connection_id=connection_id, reason="exchange_failed")
        return CallbackOutcome(connected=True, connection_id=connection_id)

    def _finish_pending(self, pending: _PendingAuthorization, code: str, issued_client_id: str = "") -> None:
        """Trade *code* for tokens and store them. Raises the provider's error."""
        connection_id = pending.connection_id
        issued = issued_client_id if pending.accept_issued_client_id else ""
        if pending.flow == FLOW_KEY_EXCHANGE:
            response = self._client.exchange_key(pending.token_url, code=code, code_verifier=pending.code_verifier)
        else:
            response = self._client.exchange_code(
                pending.token_url,
                code=code,
                redirect_uri=pending.redirect_uri,
                client_id=issued or pending.client_id,
                code_verifier=pending.code_verifier,
                client_secret=pending.client_secret,
                client_id_param=pending.client_id_param,
                extra_form=pending.extra_token_params,
            )
        self._store_tokens(connection_id, response, pending.scopes, previous=None, client_id=issued)
        self._source.invalidate(connection_id)
        logger.info("OAuth connection established for %s", connection_id)

    # ── finishing from a paste ──────────────────────────────────────────

    def complete_pasted(self, connection_id: str, pasted: str) -> ConnectionStatus:
        """Finish a flow for *connection_id* from the address or code the user pasted.

        Raises :class:`PastedCodeRejected` with a reason slug when it cannot.
        """
        target = self._target(connection_id)
        parsed = parse_pasted(pasted)
        pending = self._take_pending_for_paste(connection_id, parsed.state)
        if parsed.error:
            reason = "access_denied" if parsed.error == "access_denied" else "provider_error"
            logger.info("OAuth sign-in for %s was not completed: %s", connection_id, reason)
            raise PastedCodeRejected(reason, f"{target.provider.name} did not complete the sign-in.")
        try:
            self._finish_pending(pending, parsed.code, parsed.issued_client_id)
        except (TokenEndpointError, ProviderError) as exc:
            logger.error("OAuth code exchange for %s failed: %s", connection_id, exc)
            raise PastedCodeRejected(
                "exchange_failed", f"{target.provider.name} did not accept that code. Start the sign-in again."
            ) from exc
        return self._status(target)

    def _take_pending_for_paste(self, connection_id: str, state: str) -> _PendingAuthorization:
        """Pop the started flow a paste belongs to, or raise :class:`PastedCodeRejected`."""
        now = self._clock()
        if state:
            try:
                payload = self._signer.verify(state, now)
            except InvalidState as exc:
                raise PastedCodeRejected("expired" if exc.reason == "expired" else "invalid_state", str(exc)) from exc
            mismatch = PastedCodeRejected(
                "invalid_state", "That address belongs to a different or finished sign-in. Start again."
            )
            if payload.connection_id != connection_id:
                raise mismatch
            with self._lock:
                pending = self._pending.pop(payload.nonce, None)
            if pending is None or pending.connection_id != connection_id:
                raise mismatch
            return pending
        with self._lock:
            # Newest first: a user who started twice pastes the latest code.
            for nonce, pending in reversed(list(self._pending.items())):
                if pending.connection_id == connection_id and pending.allow_bare_code and now < pending.expires_at:
                    del self._pending[nonce]
                    return pending
        raise PastedCodeRejected(
            "no_pending", "There is no sign-in waiting for a code. Paste the whole address, or start again."
        )

    def _store_tokens(
        self,
        connection_id: str,
        response: TokenResponse,
        requested: tuple[str, ...],
        previous: TokenSet | None,
        client_id: str = "",
    ) -> TokenSet:
        now = self._clock()
        tokens = TokenSet(
            access_token=response.access_token,
            token_type=response.token_type,
            # Providers that do not rotate refresh tokens omit it on refresh.
            refresh_token=response.refresh_token or (previous.refresh_token if previous else ""),
            expires_at=now + response.expires_in if response.expires_in else None,
            scopes=response.scopes or (previous.scopes if previous else requested),
            obtained_at=previous.obtained_at if previous else now,
            client_id=client_id or (previous.client_id if previous else ""),
        )
        self._store.put(connection_id, tokens)
        with self._lock:
            self._device.pop(connection_id, None)
        return tokens

    # ── the device flow ─────────────────────────────────────────────────

    def _poll_device_until_done(self, flow: _DeviceFlow) -> None:
        while True:
            self._sleep(flow.interval)
            with self._lock:
                if self._device.get(flow.connection_id) is not flow:
                    return
            if not self.poll_device(flow.connection_id):
                return

    def _finish_device(self, flow: _DeviceFlow, status: str, detail: str = "") -> bool:
        with self._lock:
            flow.status = status
            flow.detail = detail
        logger.info("OAuth device flow for %s ended: %s", flow.connection_id, status)
        return False

    def poll_device(self, connection_id: str) -> bool:
        """Ask the provider once whether the device code was approved.

        Returns whether the flow is still pending and worth polling again.
        """
        with self._lock:
            flow = self._device.get(connection_id)
        if flow is None or flow.status != DEVICE_PENDING:
            return False
        if self._clock() >= flow.expires_at:
            return self._finish_device(flow, DEVICE_EXPIRED)
        if flow.kind == FLOW_PLEX_PIN:
            return self._poll_plex(flow)

        try:
            response = self._client.poll_device_token(
                flow.token_url,
                device_code=flow.device_code,
                client_id=flow.client_id,
                client_secret=flow.client_secret,
                client_id_param=flow.client_id_param,
                extra_form=flow.poll_form,
            )
        except TokenEndpointError as exc:
            if exc.error == "authorization_pending":
                return True
            if exc.error == "slow_down":
                with self._lock:
                    flow.interval += SLOW_DOWN_SECONDS
                return True
            if exc.error == "expired_token":
                return self._finish_device(flow, DEVICE_EXPIRED)
            if exc.error == "access_denied":
                return self._finish_device(flow, DEVICE_DENIED)
            return self._finish_device(flow, DEVICE_FAILED, exc.error)
        except ProviderError as exc:
            # A dropped connection is not a verdict; keep asking until the
            # code itself expires.
            logger.warning("OAuth device poll for %s failed, will retry: %s", connection_id, exc)
            return True

        return self._device_approved(flow, response)

    def _device_approved(self, flow: _DeviceFlow, response: TokenResponse) -> bool:
        with self._lock:
            if self._device.get(flow.connection_id) is not flow:
                # Superseded or disconnected while the request was in flight.
                return False
        self._store_tokens(flow.connection_id, response, flow.scopes, previous=None)
        self._source.invalidate(flow.connection_id)
        logger.info("OAuth connection established for %s", flow.connection_id)
        return False

    def _poll_plex(self, flow: _DeviceFlow) -> bool:
        try:
            token = plex.check_pin(self._client.http, flow.device_code, flow.client_id, flow.plex_product)
        except plex.PinGone:
            return self._finish_device(flow, DEVICE_EXPIRED)
        except ProviderError as exc:
            logger.warning("Plex PIN poll for %s failed, will retry: %s", flow.connection_id, exc)
            return True
        if not token:
            return True
        # Plex tokens do not expire and there is no refresh.
        return self._device_approved(
            flow, TokenResponse(access_token=token, token_type="Bearer", refresh_token="", expires_in=None, scopes=())
        )

    # ── disconnecting ───────────────────────────────────────────────────

    def forget(self, connection_id: str) -> bool:
        """Drop every trace of a connection. Safe for ids that no longer exist."""
        with self._lock:
            self._device.pop(connection_id, None)
            for nonce in [n for n, p in self._pending.items() if p.connection_id == connection_id]:
                del self._pending[nonce]
        return self._store.delete(connection_id)

    def disconnect(self, connection_id: str) -> ConnectionStatus:
        """Delete the stored tokens for *connection_id* and report its new status."""
        target = self._target(connection_id)
        self.forget(connection_id)
        # Results are cached for the plugin's refresh interval. Without this
        # the board would keep showing the account's data after the user
        # asked for it to stop.
        self._source.invalidate(connection_id)
        return self._status(target)

    # ── handing tokens to plugins ───────────────────────────────────────

    def _is_fresh(self, tokens: TokenSet) -> bool:
        return tokens.expires_at is None or self._clock() < tokens.expires_at - REFRESH_MARGIN_SECONDS

    def _still_valid(self, tokens: TokenSet) -> str | None:
        """The access token if it has not actually expired yet, else ``None``."""
        if tokens.expires_at is None or self._clock() < tokens.expires_at:
            return tokens.access_token
        return None

    def get_access_token(self, connection_id: str) -> str | None:
        """A usable access token for *connection_id*, refreshed if needed.

        ``None`` means the plugin is not connected (or must be reconnected);
        it should report itself unavailable rather than call the provider.
        """
        tokens = self._store.get(connection_id)
        if tokens is None or tokens.needs_reauthorization:
            return None
        if self._is_fresh(tokens):
            return tokens.access_token
        if not tokens.refresh_token:
            return self._still_valid(tokens)

        with self._lock:
            refresh_lock = self._refresh_locks.setdefault(connection_id, threading.Lock())
        with refresh_lock:
            # Another thread may have refreshed while this one waited.
            tokens = self._store.get(connection_id)
            if tokens is None or tokens.needs_reauthorization:
                return None
            if self._is_fresh(tokens):
                return tokens.access_token
            return self._refresh(connection_id, tokens)

    def _refresh(self, connection_id: str, tokens: TokenSet) -> str | None:
        target = self._source.get(connection_id)
        client_id = tokens.client_id or (target.client_id if target else "")
        if target is None or not client_id:
            return self._still_valid(tokens)
        try:
            token_url = target.endpoints().token_url
        except ConnectionNotConfigured as exc:
            logger.warning("OAuth refresh for %s skipped: %s", connection_id, exc)
            return self._still_valid(tokens)
        try:
            response = self._client.refresh(
                token_url,
                refresh_token=tokens.refresh_token,
                client_id=client_id,
                client_secret=target.client_secret,
                client_id_param=target.provider.client_id_param,
            )
        except TokenEndpointError as exc:
            if exc.error in _REAUTHORIZE_ERRORS:
                logger.warning("OAuth refresh for %s was refused (%s); reconnect required", connection_id, exc.error)
                self._store.put(connection_id, replace(tokens, needs_reauthorization=True))
                return None
            logger.error("OAuth refresh for %s failed: %s", connection_id, exc.error)
            return self._still_valid(tokens)
        except ProviderError as exc:
            logger.warning("OAuth refresh for %s failed, will retry: %s", connection_id, exc)
            return self._still_valid(tokens)
        return self._store_tokens(connection_id, response, tokens.scopes, previous=tokens).access_token

    def access_token_for(self, plugin: object) -> str | None:
        """A usable access token for the given plugin object, or ``None``."""
        connection_id = self._source.id_for(plugin)
        return self.get_access_token(connection_id) if connection_id else None


# ── Singleton ───────────────────────────────────────────────────────────────

_service: OAuthService | None = None
_service_lock = threading.Lock()


def get_oauth_service() -> OAuthService:
    """The process-wide :class:`OAuthService`."""
    global _service
    with _service_lock:
        if _service is None:
            _service = OAuthService(
                source=RegistryConnectionSource(),
                store=TokenStore(),
                signer=StateSigner(load_state_key(get_data_dir())),
            )
        return _service


def reset_oauth_service() -> None:
    """Drop the singleton so the next call rebuilds it (tests)."""
    global _service
    with _service_lock:
        _service = None
