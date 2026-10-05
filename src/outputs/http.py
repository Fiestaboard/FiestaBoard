"""``OutputPluginBase.http``: the one way an output plugin talks to its device.

Every output plugin instance has an :class:`OutputHttp` as ``self.http``.
It is a thin wrapper over a ``requests`` session that puts core's safety
in front of third-party code (plan D10):

- **The host fence.** :func:`~src.output_allowlist.check_output_url` runs
  before every request: with ``FIESTABOARD_OUTPUTS_ALLOW_HOSTS`` set, a
  request to any other host raises
  :class:`~src.output_allowlist.OutputHostBlocked` (a ``requests``
  ``ConnectionError``) and no socket opens. The dev stack sets the variable
  to its mocks, so a developer's real device stays unreachable while they
  work on something else.
- **Timeouts.** A request that names no ``timeout`` gets
  :data:`DEFAULT_TIMEOUT` ``(connect, read)``: a dead device fails one
  request in seconds instead of holding the write until core's budget.
- **No redirects.** A redirect is a request to a host the fence never saw,
  so none is followed (``allow_redirects=True`` is refused).
- **Cancel.** A request after the run's cancel token fired raises
  :class:`RequestCancelled` without reaching the device. The token is the
  ``cancel=`` passed in, else the one core bound for the write in flight:
  core runs every ``write`` / ``write_cells`` / ``write_sequence`` /
  ``write_transition`` inside :meth:`OutputHttp.cancel_scope`. A request
  already on the wire is not interrupted; its timeout bounds it.
- **Setup requests.** ``setup=True`` marks a request that is not the board
  write itself (a reset, a brightness command). Core's conformance suite
  leaves those out of the write's accounting: a write whose frame landed is
  a success even if a setup request it tolerates losing failed.

Usage, inside a plugin::

    response = self.http.post(f"http://{host}/post", json=payload)
    self.http.post(url, json={"Command": "Channel/SetBrightness"}, setup=True)

Any other keyword (``json``, ``data``, ``headers``, ``params``, ``auth``...)
is passed to ``requests`` unchanged; the return value is the
``requests.Response``. Errors are ``requests`` exceptions, so a plugin
handles a fenced, cancelled or unreachable device with one ``except``.

Tests replace the transport with :meth:`OutputHttp.use_transport`; the
output conformance suite does exactly that, so it exercises the plugin's
real request code against its fake device.

**First-party outputs** (the Vestaboard and FiestaPanel packages core seeds)
get :meth:`OutputHttp.for_first_party`: the same fence, cancel and default
timeout, but each request is the ``requests`` module call those outputs
made before they were plugins — ``requests.post(url, headers=..., json=...,
timeout=...)``, keywords in the caller's order, ``requests``' own redirect
default — so their wire goldens hold byte for byte. Only core chooses it,
when it builds a first-party output's instance; a plugin cannot.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Protocol

import requests

from src.output_allowlist import check_output_url

__all__ = [
    "DEFAULT_TIMEOUT",
    "HttpRequest",
    "OutputHttp",
    "RequestCancelled",
    "Transport",
]

#: ``(connect, read)`` seconds for a request that names no timeout.
DEFAULT_TIMEOUT: tuple[float, float] = (3.05, 10.0)


class _Cancellable(Protocol):
    @property
    def cancelled(self) -> bool: ...


class RequestCancelled(requests.exceptions.RequestException):
    """The run was cancelled (a newer frame preempted it) before this request."""

    def __init__(self, url: str) -> None:
        super().__init__(f"request to {url} not sent: the write was cancelled")
        self.url = url


@dataclass(frozen=True)
class HttpRequest:
    """One request, as a transport receives it (after the fence passed it)."""

    method: str
    url: str
    #: Everything else for ``requests`` (``json``, ``data``, ``headers``...),
    #: ``allow_redirects=False`` included.
    kwargs: dict[str, Any] = field(default_factory=dict)
    timeout: Any = DEFAULT_TIMEOUT
    #: Not the board write itself (a reset, a brightness command).
    setup: bool = False

    @property
    def json(self) -> Any:
        return self.kwargs.get("json")

    @property
    def data(self) -> Any:
        return self.kwargs.get("data")


Transport = Callable[[HttpRequest], requests.Response]


class OutputHttp:
    """One plugin instance's device HTTP client (see the module docstring)."""

    def __init__(self, *, module_requests: bool = False) -> None:
        self._transport: Transport | None = None
        self._session: requests.Session | None = None
        self._session_lock = threading.Lock()
        self._local = threading.local()
        self._module_requests = module_requests

    @classmethod
    def for_first_party(cls) -> OutputHttp:
        """The first-party outputs' client (see the module docstring)."""
        return cls(module_requests=True)

    # --- seams -------------------------------------------------------------------------

    def use_transport(self, transport: Transport | None) -> None:
        """Send every request through *transport* instead of the network
        (tests; the conformance suite's fake device). ``None`` restores it."""
        self._transport = transport

    @contextmanager
    def cancel_scope(self, cancel: _Cancellable | None) -> Iterator[None]:
        """Bind *cancel* as this thread's token for the requests inside.

        Core wraps each write in one, so a plugin that does not pass
        ``cancel=`` still stops at its next request once preempted.
        """
        outer = getattr(self._local, "cancel", None)
        self._local.cancel = cancel
        try:
            yield
        finally:
            self._local.cancel = outer

    @property
    def current_cancel(self) -> _Cancellable | None:
        """The token core bound for the write on this thread, if any."""
        return getattr(self._local, "cancel", None)

    # --- requests ----------------------------------------------------------------------

    def request(
        self,
        method: str,
        url: str,
        *,
        setup: bool = False,
        cancel: _Cancellable | None = None,
        **kwargs: Any,
    ) -> requests.Response:
        """Send one request to the device, under core's fence and defaults.

        ``timeout`` (``(connect, read)`` seconds) defaults to
        :data:`DEFAULT_TIMEOUT`; every other keyword goes to ``requests``.

        Raises:
            RequestCancelled: the run's token fired before the request.
            OutputHostBlocked: the host is outside FIESTABOARD_OUTPUTS_ALLOW_HOSTS.
            ValueError: ``allow_redirects=True`` (redirects are never followed).
            requests.RequestException: whatever the request itself raised.
        """
        if kwargs.pop("allow_redirects", False):
            raise ValueError("Output requests never follow a redirect: it would reach a host the fence never saw.")
        token = cancel if cancel is not None else self.current_cancel
        if token is not None and token.cancelled:
            raise RequestCancelled(url)
        check_output_url(url)
        # The caller's keywords in the caller's order, the timeout where it
        # gave one (or last): a first-party request is the call it always was.
        ordered = dict(kwargs)
        if ordered.get("timeout") is None:
            ordered["timeout"] = DEFAULT_TIMEOUT
        timeout = ordered["timeout"]
        body = {key: value for key, value in ordered.items() if key != "timeout"}
        request = HttpRequest(
            method.upper(),
            url,
            body if self._module_requests else {**body, "allow_redirects": False},
            timeout,
            setup,
        )
        transport = self._transport
        if transport is not None:
            return transport(request)
        if self._module_requests:
            send = getattr(requests, method.lower(), None)
            if send is None:
                return requests.request(request.method, url, **ordered)
            return send(url, **ordered)
        return self._session_for().request(request.method, request.url, timeout=request.timeout, **request.kwargs)

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> requests.Response:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> requests.Response:
        return self.request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> requests.Response:
        return self.request("DELETE", url, **kwargs)

    # --- lifetime ----------------------------------------------------------------------

    def _session_for(self) -> requests.Session:
        with self._session_lock:
            if self._session is None:
                self._session = requests.Session()
            return self._session

    def close(self) -> None:
        """Release pooled connections. Core calls it after the plugin's ``close``."""
        with self._session_lock:
            session, self._session = self._session, None
        if session is not None:
            session.close()
