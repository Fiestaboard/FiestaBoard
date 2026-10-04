"""``OutputPluginBase.http``: the one way an output plugin talks to its device.

The helper is where core's safety reaches third-party code (plan D10):

- **The host fence.** ``FIESTABOARD_OUTPUTS_ALLOW_HOSTS`` refuses every
  request to a host outside the list *before* a socket opens, with the
  same :class:`~src.output_allowlist.OutputHostBlocked` the built-in
  Vestaboard clients raise;
- **Timeouts.** A request with no timeout gets core's ``(connect, read)``
  default, so a dead device cannot hang a write until the write budget;
- **Redirects.** Never followed: a redirect is a request to a host the
  fence never saw;
- **Cancel.** A request after the run's cancel token fired is refused
  without reaching the device — the token passed in, or the one core bound
  for the write in flight.

The default transport is a real ``requests`` session; the tests that prove
it talk to a loopback server (pytest-socket allows 127.0.0.1 only).
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from src.output_allowlist import ENV_VAR, OutputHostBlocked
from src.outputs.http import (
    DEFAULT_TIMEOUT,
    HttpRequest,
    OutputHttp,
    RequestCancelled,
)
from src.outputs.plugin_base import CancelToken, OutputPluginBase
from src.send_outcome import WriteResult


class Recorder:
    """A transport that records each request and answers 200 ``{}``."""

    def __init__(self) -> None:
        self.requests: list[HttpRequest] = []

    def __call__(self, request: HttpRequest) -> requests.Response:
        self.requests.append(request)
        response = requests.Response()
        response.status_code = 200
        response._content = b"{}"
        response.url = request.url
        return response


@pytest.fixture
def recorder() -> Recorder:
    return Recorder()


@pytest.fixture
def http(recorder) -> OutputHttp:
    helper = OutputHttp()
    helper.use_transport(recorder)
    return helper


class _Device:
    """A loopback HTTP device that records each POST body."""

    def __init__(self) -> None:
        self.bodies: list[dict] = []
        device = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # quiet
                pass

            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                device.bodies.append(json.loads(raw))
                body = b'{"error_code": 0}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        host, port = self.server.server_address[:2]
        return f"http://{host}:{port}/post"

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def device():
    d = _Device()
    yield d
    d.stop()


class TestTheFence:
    def test_a_request_to_an_unlisted_host_is_refused_before_the_transport(self, http, recorder, monkeypatch):
        monkeypatch.setenv(ENV_VAR, "fiestaboard-mock-pixoo")
        with pytest.raises(OutputHostBlocked, match=r"192\.0\.2\.10"):
            http.post("http://192.0.2.10/post", json={"Command": "Channel/GetAllConf"})
        assert recorder.requests == []

    def test_a_request_to_a_listed_host_goes_through(self, http, recorder, monkeypatch):
        monkeypatch.setenv(ENV_VAR, "fiestaboard-mock-pixoo")
        response = http.post("http://fiestaboard-mock-pixoo/post", json={"Command": "x"})
        assert response.status_code == 200
        assert [r.url for r in recorder.requests] == ["http://fiestaboard-mock-pixoo/post"]

    def test_the_refusal_is_a_requests_connection_error(self, http, monkeypatch):
        # Plugins already handle "device unreachable"; a fenced device degrades the same way.
        monkeypatch.setenv(ENV_VAR, "fiestaboard-mock-pixoo")
        with pytest.raises(requests.exceptions.ConnectionError):
            http.get("http://192.0.2.10/")

    def test_a_fenced_host_never_sees_a_connection_on_the_real_transport(self, device, monkeypatch):
        monkeypatch.setenv(ENV_VAR, "fiestaboard-mock-pixoo")
        with pytest.raises(OutputHostBlocked):
            OutputHttp().post(device.url, json={"Command": "x"})
        assert device.bodies == []

    def test_the_real_transport_reaches_an_allowed_device(self, device, monkeypatch):
        monkeypatch.setenv(ENV_VAR, "127.0.0.1")
        response = OutputHttp().post(device.url, json={"Command": "Channel/GetAllConf"})
        assert response.json() == {"error_code": 0}
        assert device.bodies == [{"Command": "Channel/GetAllConf"}]


class TestTimeoutsAndRedirects:
    def test_a_request_without_a_timeout_gets_cores_default(self, http, recorder):
        http.post("http://192.0.2.10/post", json={})
        assert recorder.requests[0].timeout == DEFAULT_TIMEOUT
        assert isinstance(DEFAULT_TIMEOUT, tuple) and len(DEFAULT_TIMEOUT) == 2

    def test_a_plugins_own_timeout_is_kept(self, http, recorder):
        http.post("http://192.0.2.10/post", json={}, timeout=(3.0, 5.0))
        assert recorder.requests[0].timeout == (3.0, 5.0)

    def test_redirects_are_never_followed(self, http, recorder):
        http.get("http://192.0.2.10/")
        assert recorder.requests[0].kwargs["allow_redirects"] is False

    def test_asking_to_follow_redirects_is_refused(self, http, recorder):
        with pytest.raises(ValueError, match="redirect"):
            http.get("http://192.0.2.10/", allow_redirects=True)
        assert recorder.requests == []


class TestCancel:
    def test_a_cancelled_token_refuses_the_request(self, http, recorder):
        event = threading.Event()
        event.set()
        with pytest.raises(RequestCancelled):
            http.post("http://192.0.2.10/post", json={}, cancel=CancelToken(event))
        assert recorder.requests == []

    def test_the_refusal_is_a_requests_exception(self):
        assert issubclass(RequestCancelled, requests.exceptions.RequestException)

    def test_a_live_token_lets_the_request_through(self, http, recorder):
        http.post("http://192.0.2.10/post", json={}, cancel=CancelToken())
        assert len(recorder.requests) == 1

    def test_the_token_core_bound_for_the_write_is_honoured(self, http, recorder):
        event = threading.Event()
        with http.cancel_scope(CancelToken(event)):
            http.post("http://192.0.2.10/post", json={})
            event.set()
            with pytest.raises(RequestCancelled):
                http.post("http://192.0.2.10/post", json={})
        assert len(recorder.requests) == 1

    def test_the_bound_token_ends_with_its_scope(self, http, recorder):
        event = threading.Event()
        event.set()
        with http.cancel_scope(CancelToken(event)):
            pass
        http.post("http://192.0.2.10/post", json={})
        assert len(recorder.requests) == 1


class TestSetupRequests:
    def test_a_request_is_a_board_write_unless_marked(self, http, recorder):
        http.post("http://192.0.2.10/post", json={"Command": "Draw/SendHttpGif"})
        http.post("http://192.0.2.10/post", json={"Command": "Channel/SetBrightness"}, setup=True)
        assert [r.setup for r in recorder.requests] == [False, True]

    def test_the_request_carries_its_body(self, http, recorder):
        http.post("http://192.0.2.10/post", json={"Command": "x"})
        assert recorder.requests[0].method == "POST"
        assert recorder.requests[0].json == {"Command": "x"}


class _Probe(OutputPluginBase):
    def write(self, frame, *, native, cancel):
        self.http.post("http://192.0.2.10/post", json={"frame": frame})
        return WriteResult(True, True)


class TestOnThePluginBase:
    def test_every_plugin_instance_has_its_own_helper(self):
        one, two = _Probe("a", {}), _Probe("b", {})
        assert isinstance(one.http, OutputHttp)
        assert one.http is one.http
        assert one.http is not two.http

    def test_core_binds_the_writes_cancel_token(self, recorder):
        """The driver runs each write inside the helper's cancel scope, so a
        plugin that forgets to pass ``cancel=`` still stops when preempted."""
        from src.outputs.plugin_driver import OutputPluginDriver

        plugin = _Probe("board", {})

        class Preempting(Recorder):
            def __call__(self, request):
                driver._output_runtime.preempt()  # a newer frame arrives mid-write
                return super().__call__(request)

        transport = Preempting()
        plugin.http.use_transport(transport)

        def write(frame, *, native, cancel):
            plugin.http.post("http://192.0.2.10/post", json={"n": 1})
            try:
                plugin.http.post("http://192.0.2.10/post", json={"n": 2})
            except RequestCancelled:
                return WriteResult(True, False)
            return WriteResult(True, True)

        plugin.write = write  # type: ignore[method-assign]
        plugin.capabilities = lambda: _caps()  # type: ignore[method-assign]
        driver = OutputPluginDriver(plugin)
        driver.send_characters([[1] * 15 for _ in range(3)])
        assert [r.json for r in transport.requests] == [{"n": 1}]


def _caps():
    from src.outputs.registry import OutputCapabilities

    return OutputCapabilities(
        technology="led_matrix", delivery="push", animation="stream", native_transitions=frozenset()
    )
