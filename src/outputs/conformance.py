"""The output-plugin conformance suite (plan Phase 2.3).

One definition of "a well-behaved output plugin", shared by core and every
output plugin repository: FiestaBoard core runs it against its test kit
(``tests/fixtures/plugins/recording_output``), and a plugin repo runs it in
its own CI against the core tag it pins.

**Using it from a plugin repository.** The plugin's device traffic goes
through ``self.http`` (:mod:`src.outputs.http`), and the suite routes that
helper to its :class:`FakeTransport` itself, so the plugin's real request
code runs against a fake device. The factory just builds the plugin::

    # tests/test_conformance.py in fiestaboard-output--acme-sign
    from pathlib import Path

    from src.outputs.conformance import OutputConformanceSuite

    from plugins.acme_sign import AcmeSign   # however your repo imports it

    def make_plugin(board_id, config, transport):
        return AcmeSign(board_id, config)    # self.http -> the fake: the suite does it

    def test_conformance():
        OutputConformanceSuite(
            plugin_dir=Path(__file__).resolve().parent.parent,   # holds manifest.json
            factory=make_plugin,
            config={"host": "192.0.2.10", "token": "test_token_1234"},
            # Optional: turn one request's payload (its JSON body, else its
            # data) back into the CellFrame it carries (None for requests
            # that carry no frame). Enables the frame-level sequence rule.
            decode=lambda payload: payload.get("frame"),
        ).assert_conformant()

Each request is recorded, delayed by the configured latency, and answered
``200 {"ok": true}`` — or failed with :class:`TransportError` (a
``requests`` ``ConnectionError``, so an ``OSError``) when the suite makes
the device fail, so the plugin's own error handling is what is tested.
Pass ``config`` values for every secret field the board settings declare:
the suite checks none of them leaks into ``device_key()``.

A factory that replaces the plugin's own request seam with
``transport.send`` still records requests, but bypasses ``self.http``: the
``device_traffic`` rule fails it.

**The rules** (each a ``check_*`` method returning :class:`Violation` s;
:meth:`~OutputConformanceSuite.run` runs them all):

- ``manifest`` — ``manifest.json`` loads with no error (FiestaUI schemas,
  ``output_api``, ``$ref`` files) and is ``plugin_type: "output"``;
- ``character_set`` — a declared character set materialises non-empty, and
  so does every character set a device model embeds;
- ``geometry_floor`` — every declared device model reaches the 3×15 Note
  floor in cells (core refuses a smaller board);
- ``import_network`` — importing the plugin package makes no network call
  (no socket connect, no DNS lookup) and yields an ``OutputPluginBase``;
- ``device_key`` — a non-empty string, stable across calls and across
  instances built from the same settings, containing no secret value;
- ``floor`` — ``min_interval_ms`` is a non-negative integer; the plugin does
  not throttle itself (core does) nor talk to the device outside a write;
  with a floor, core keeps a second frame inside it off the device;
- ``device_traffic`` — writes, sequences and connection checks talk to the
  device only through ``self.http`` (the host fence, timeouts, cancel): no
  socket of their own, and no request that bypassed the helper;
- ``write_result`` — every write answers a well-formed ``WriteResult``; a
  device failure is reported, not raised; a write that landed on part of the
  board is ``partial`` with in-bounds ``failed_regions``. Requests marked
  ``setup=True`` (a reset, a brightness command) are not part of the board
  write: the scenario fails the first *board* request, and a lost setup
  request the plugin tolerates does not make a landed write partial;
- ``cancel`` — once the run's cancel token fires, ``write`` (and
  ``write_sequence``) start no further device request and return promptly;
- ``sequence`` — for ``animation: sequence`` outputs, ``write_sequence``
  uploads at most ``maxFrames`` frames and always ends on the target frame;
- ``check_connection`` — returns a ``ConnectionCheck`` and never raises,
  reporting a failure when the device fails.
"""

from __future__ import annotations

import importlib.util
import socket
import sys
import threading
import time
import uuid
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

from src.devices import MIN_GRID_COLS, MIN_GRID_ROWS
from src.led.charsets import CharacterSetError, materialize_character_set
from src.send_outcome import FrameRegion, WriteResult

from .geometry import model_cell_grid
from .hooks import ConnectionCheck
from .http import HttpRequest
from .plugin_base import CancelToken, CellFrame, OutputPluginBase, TimedFrame

__all__ = [
    "MIN_COLS",
    "MIN_ROWS",
    "ConformanceReport",
    "FakeTransport",
    "OutputConformanceSuite",
    "Request",
    "TransportError",
    "Violation",
    "model_cell_grid",
]

#: The platform content floor: a Note, 3 rows × 15 columns (plan D5). Core
#: refuses a smaller board at creation (src/outputs/geometry.py), which sizes
#: models exactly as this suite does: model_cell_grid is that module's.
MIN_ROWS, MIN_COLS = MIN_GRID_ROWS, MIN_GRID_COLS

PluginFactory = Callable[[str | None, dict, "FakeTransport"], OutputPluginBase]


# --- the fake device ---------------------------------------------------------------------


class TransportError(requests.exceptions.ConnectionError):
    """The fake device failed this request (an ``OSError``, as every
    ``requests`` connection error is)."""


@dataclass
class Request:
    """One request the plugin made."""

    payload: Any
    started: float
    #: The frame the payload carries, when the suite was given a ``decode``.
    frame: CellFrame | None = None
    failed: bool = False
    #: Marked ``setup=True``: not part of the board write.
    setup: bool = False
    #: Arrived through the plugin's ``self.http`` (not a patched seam).
    via_http: bool = False


class FakeTransport:
    """The device side of a conformance run.

    Args:
        decode: Optional ``payload -> CellFrame | None``: the frame a
            request carries, in the plugin's own wire format.
    """

    def __init__(self, decode: Callable[[Any], CellFrame | None] | None = None) -> None:
        self.decode = decode
        self.requests: list[Request] = []
        self.latency = 0.0
        self._fails: Callable[[int], bool] = lambda index: False
        self._fails_board: Callable[[int], bool] = lambda index: False
        self._fail_setup = False
        self._lock = threading.Lock()

    def reset(
        self,
        *,
        latency: float = 0.0,
        fail: Callable[[int], bool] | None = None,
        fail_board: Callable[[int], bool] | None = None,
        fail_setup: bool = False,
    ) -> None:
        """Forget every request; set the latency and which requests fail:
        *fail* by 0-based index over every request, *fail_board* by index
        over board requests only (those not marked ``setup``), and with
        *fail_setup* every request marked ``setup``."""
        with self._lock:
            self.requests = []
            self.latency = latency
            self._fails = fail or (lambda index: False)
            self._fails_board = fail_board or (lambda index: False)
            self._fail_setup = fail_setup

    def _record(self, payload: Any, *, setup: bool, via_http: bool) -> None:
        with self._lock:
            index = len(self.requests)
            board_index = sum(1 for r in self.requests if not r.setup)
            frame = self.decode(payload) if self.decode is not None else None
            failed = self._fails(index) or (self._fail_setup if setup else self._fails_board(board_index))
            request = Request(payload, time.monotonic(), frame, failed=failed, setup=setup, via_http=via_http)
            self.requests.append(request)
            latency = self.latency
        if latency:
            time.sleep(latency)
        if request.failed:
            raise TransportError(f"fake device refused request {index}")

    def send(self, payload: Any) -> dict[str, Any]:
        """One device request made around ``self.http`` (a patched seam):
        recorded, delayed by the latency, maybe failed."""
        self._record(payload, setup=False, via_http=False)
        return {"ok": True}

    def http_send(self, request: HttpRequest) -> requests.Response:
        """One request from the plugin's ``self.http`` — the transport the
        suite routes the helper to. The recorded payload is the JSON body,
        else the data."""
        payload = request.json if request.json is not None else request.data
        self._record(payload, setup=request.setup, via_http=True)
        response = requests.Response()
        response.status_code = 200
        response._content = b'{"ok": true}'
        response.headers["Content-Type"] = "application/json"
        response.url = request.url
        return response


# --- the report --------------------------------------------------------------------------


@dataclass(frozen=True)
class Violation:
    """One rule broken."""

    rule: str
    message: str

    def __str__(self) -> str:
        return f"[{self.rule}] {self.message}"


@dataclass
class ConformanceReport:
    """Everything one run found. ``skipped`` names rules that did not apply."""

    plugin_id: str
    violations: list[Violation] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    def summary(self) -> str:
        if self.ok:
            return f"{self.plugin_id}: conformant" + (f" (skipped: {'; '.join(self.skipped)})" if self.skipped else "")
        lines = [f"{self.plugin_id}: {len(self.violations)} conformance violation(s)"]
        lines += [f"  {v}" for v in self.violations]
        return "\n".join(lines)


# --- secrets and network -------------------------------------------------------------------


def _secret_values(schema: Mapping[str, Any], value: Any) -> list[str]:
    """Every string in *value* at a field *schema* marks secret."""
    found: list[str] = []
    if isinstance(value, Mapping):
        for name, prop in (schema.get("properties") or {}).items():
            if name not in value or not isinstance(prop, Mapping):
                continue
            item = value[name]
            if (prop.get("secret") is True or prop.get("ui:widget") == "password") and isinstance(item, str):
                found.append(item)
            else:
                found += _secret_values(prop, item)
    elif isinstance(value, list) and isinstance(schema.get("items"), Mapping):
        for item in value:
            found += _secret_values(schema["items"], item)
    return found


class _NetworkBlocked(OSError):
    pass


@contextmanager
def _no_network(attempts: list[str], during: str = "import") -> Iterator[None]:
    """Refuse (and record) every socket connect and DNS lookup inside."""

    def refuse(name: str) -> Callable[..., Any]:
        def blocked(*args: Any, **kwargs: Any) -> Any:
            target = args[1] if name.startswith("socket.connect") and len(args) > 1 else (args[0] if args else "")
            attempts.append(f"{name}({target!r})")
            raise _NetworkBlocked(f"network access during {during}: {name}({target!r})")

        return blocked

    sock_cls = socket.socket
    originals = {
        (sock_cls, "connect"): sock_cls.connect,
        (sock_cls, "connect_ex"): sock_cls.connect_ex,
        (socket, "create_connection"): socket.create_connection,
        (socket, "getaddrinfo"): socket.getaddrinfo,
    }
    for owner, attr in originals:
        setattr(owner, attr, refuse(f"socket.{attr}"))
    try:
        yield
    finally:
        for (owner, attr), original in originals.items():
            setattr(owner, attr, original)


# --- the suite ----------------------------------------------------------------------------


def _grid(rows: int, cols: int, code: int) -> CellFrame:
    return [[code] * cols for _ in range(rows)]


class OutputConformanceSuite:
    """Checks one output plugin against the output contract (module docstring).

    Args:
        plugin_dir: The plugin's directory (holds ``manifest.json``).
        factory: ``(board_id, output_config, transport) -> plugin`` — a fresh
            instance whose device I/O goes through *transport*.
        config: A board's ``output_config`` for the plugin (give every secret
            field a value).
        decode: Optional ``payload -> CellFrame | None`` for frame-level rules.
        latency: Seconds each request takes in the ``cancel`` rule.
        budget: Seconds a write may take beyond the device's own latency.
    """

    def __init__(
        self,
        plugin_dir: Path,
        factory: PluginFactory,
        config: dict[str, Any],
        *,
        decode: Callable[[Any], CellFrame | None] | None = None,
        latency: float = 0.25,
        budget: float = 1.0,
    ) -> None:
        self.plugin_dir = Path(plugin_dir)
        self.factory = factory
        self.config = dict(config)
        self.decode = decode
        self.latency = latency
        self.budget = budget
        self.transport = FakeTransport(decode)
        self._manifest: Any = None
        self._manifest_errors: list[str] | None = None
        self._skipped: list[str] = []

    # --- plumbing ----------------------------------------------------------------------------

    @property
    def manifest(self) -> Any:
        """The parsed manifest, or ``None`` when it does not load."""
        if self._manifest_errors is None:
            from src.plugins.manifest import load_manifest

            self._manifest, self._manifest_errors = load_manifest(self.plugin_dir / "manifest.json")
        return self._manifest

    @property
    def plugin_id(self) -> str:
        return self.manifest.id if self.manifest is not None else self.plugin_dir.name

    def _skip(self, rule: str, why: str) -> list[Violation]:
        self._skipped.append(f"{rule}: {why}")
        return []

    def _plugin(self, board_id: str | None = "conformance") -> OutputPluginBase:
        plugin = self.factory(board_id, dict(self.config), self.transport)
        if self.manifest is not None and self.manifest.output is not None:
            plugin.bind_manifest(self.manifest.output)
        plugin.http.use_transport(self.transport.http_send)
        plugin.open()
        return plugin

    def _shape(self) -> tuple[int, int]:
        """The board shape writes use: the first declared model's cell grid."""
        output = self.manifest.output if self.manifest is not None else None
        if output is not None:
            try:
                grid = model_cell_grid(output.model(0), output.character_set)
            except (ValueError, KeyError):
                grid = None
            if grid is not None:
                return grid
        return 6, 22

    def _frame(self, code: int) -> CellFrame:
        return _grid(*self._shape(), code)

    def _write(self, plugin: OutputPluginBase, frame: CellFrame, cancel: CancelToken | None = None) -> Any:
        return plugin.write(frame, native=None, cancel=cancel or CancelToken())

    # --- rules -------------------------------------------------------------------------------

    def check_manifest(self) -> list[Violation]:
        manifest = self.manifest
        if manifest is None or self._manifest_errors:
            return [Violation("manifest", e) for e in (self._manifest_errors or ["manifest.json did not load"])]
        if manifest.plugin_type != "output" or manifest.output is None:
            return [
                Violation("manifest", f"plugin_type is {manifest.plugin_type!r}; an output plugin declares 'output'")
            ]
        return []

    def check_character_set(self) -> list[Violation]:
        output = self.manifest.output if self.manifest is not None else None
        if output is None:
            return self._skip("character_set", "no output block")
        violations: list[Violation] = []
        declared = output.character_set
        if declared is not None and not declared.get("chars"):
            violations.append(Violation("character_set", f"character set {declared.get('id')!r} materialised empty"))
        # The schema accepts a model's embedded CharacterSet on its shape
        # alone; it must also materialise (its parent exists, the result is
        # whole), or no board of that model can draw text.
        for index in range(len(output.device_models)):
            model = output.model(index)
            charset = model.get("charset")
            if isinstance(charset, Mapping):
                try:
                    materialize_character_set(charset)
                except CharacterSetError as exc:
                    violations.append(Violation("character_set", f"device model {model['id']!r}: {exc}"))
        return violations

    def check_geometry_floor(self) -> list[Violation]:
        output = self.manifest.output if self.manifest is not None else None
        if output is None:
            return self._skip("geometry_floor", "no output block")
        violations: list[Violation] = []
        for index in range(len(output.device_models)):
            model = output.model(index)
            try:
                grid = model_cell_grid(model, output.character_set)
            except ValueError as exc:
                violations.append(Violation("geometry_floor", f"cannot size {exc}"))
                continue
            if grid is None:
                continue
            rows, cols = grid
            if rows < MIN_ROWS or cols < MIN_COLS:
                violations.append(
                    Violation(
                        "geometry_floor",
                        f"device model {model['id']!r} shows {rows}x{cols} cells, below the "
                        f"{MIN_ROWS}x{MIN_COLS} floor: core refuses a board this small",
                    )
                )
        return violations

    def check_import_network(self) -> list[Violation]:
        init = self.plugin_dir / "__init__.py"
        if not init.is_file():
            init = self.plugin_dir / "plugins" / self.plugin_dir.name / "__init__.py"
        if not init.is_file():
            return [Violation("import_network", f"no __init__.py in {self.plugin_dir}")]
        name = f"_fiestaboard_conformance_{uuid.uuid4().hex}"
        spec = importlib.util.spec_from_file_location(name, init, submodule_search_locations=[str(init.parent)])
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        attempts: list[str] = []
        try:
            with _no_network(attempts):
                spec.loader.exec_module(module)
        except Exception as exc:
            if not attempts:
                return [Violation("import_network", f"importing the plugin failed: {exc!r}")]
        finally:
            for loaded in [m for m in sys.modules if m == name or m.startswith(f"{name}.")]:
                sys.modules.pop(loaded, None)
        if attempts:
            return [Violation("import_network", f"importing the plugin touched the network: {', '.join(attempts)}")]
        classes = [
            value
            for value in vars(module).values()
            if isinstance(value, type) and issubclass(value, OutputPluginBase) and value is not OutputPluginBase
        ]
        if not classes:
            return [Violation("import_network", "the package defines no OutputPluginBase subclass")]
        return []

    def check_device_key(self) -> list[Violation]:
        one, two = self._plugin("conformance-a"), self._plugin("conformance-b")
        key = one.device_key()
        if not isinstance(key, str) or not key:
            return [Violation("device_key", f"device_key() returned {key!r}; it must be a non-empty string")]
        violations: list[Violation] = []
        if one.device_key() != key:
            violations.append(Violation("device_key", "device_key() changed between two calls"))
        if two.device_key() != key:
            violations.append(
                Violation(
                    "device_key",
                    f"two instances with the same settings answered {key!r} and {two.device_key()!r}: the key "
                    "must name the device, so a rebuilt board keeps its send floor",
                )
            )
        schema = self.manifest.output.settings_schema if self.manifest is not None and self.manifest.output else {}
        secrets = [s for s in _secret_values(schema, self.config) if len(s) >= 4]
        if not secrets:
            self._skipped.append("device_key: no secret values in the config to look for")
        for secret in secrets:
            if secret in key:
                violations.append(Violation("device_key", "device_key() contains a secret setting; hash it instead"))
        return violations

    def check_floor(self) -> list[Violation]:
        from .plugin_driver import OutputPluginDriver

        plugin = self._plugin()
        floor_ms = plugin.capabilities().min_interval_ms
        if not isinstance(floor_ms, int) or isinstance(floor_ms, bool) or floor_ms < 0:
            return [Violation("floor", f"min_interval_ms is {floor_ms!r}; declare a non-negative integer")]
        violations: list[Violation] = []

        # The plugin never spaces writes itself: core's floor does.
        self.transport.reset()
        started = time.monotonic()
        self._write(plugin, self._frame(1))
        self._write(plugin, self._frame(2))
        took = time.monotonic() - started
        if took > self.budget:
            violations.append(
                Violation("floor", f"two writes took {took:.2f}s on an instant device: leave spacing to core's floor")
            )
        # ...and talks to the device only inside a write.
        settled = len(self.transport.requests)
        time.sleep(0.2)
        if len(self.transport.requests) != settled:
            violations.append(Violation("floor", "the plugin sent device requests after write() returned"))

        if floor_ms == 0:
            return violations + self._skip("floor", "min_interval_ms is 0 (no floor to keep)")
        # Core keeps the floor: a second frame inside it never reaches the
        # device. The run uses a private device key, so the process-wide
        # floor of the plugin's real key is never touched.
        driven = self._plugin()
        key = f"conformance-floor:{uuid.uuid4().hex}"
        driven.device_key = lambda: key  # type: ignore[method-assign]
        now = [1_000.0]
        driver = OutputPluginDriver(driven, clock=lambda: now[0])
        self.transport.reset()
        driver.send_characters(self._frame(1))
        sent = len(self.transport.requests)
        now[0] += max(0.0, floor_ms / 1000.0 - 0.5)
        outcome = driver.send_characters(self._frame(2), with_outcome=True)
        if not outcome.throttled or len(self.transport.requests) != sent:
            violations.append(Violation("floor", "a frame inside the declared floor reached the device"))
        return violations

    def _well_formed(self, result: Any, where: str) -> list[Violation]:
        if not isinstance(result, WriteResult):
            return [Violation("write_result", f"{where} returned {type(result).__name__}, not a WriteResult")]
        violations: list[Violation] = []
        if not isinstance(result.success, bool) or not isinstance(result.was_sent, bool):
            violations.append(Violation("write_result", f"{where}: success and was_sent must be bools"))
        if result.throttled or result.retry_after_seconds is not None or result.floor_seconds is not None:
            violations.append(Violation("write_result", f"{where}: throttled/retry_after/floor_seconds are core's"))
        if result.failed_regions and not result.partial:
            violations.append(Violation("write_result", f"{where}: failed_regions without partial"))
        if result.partial and result.success:
            violations.append(Violation("write_result", f"{where}: a partial write is not a success"))
        rows, cols = self._shape()
        for region in result.failed_regions:
            if (
                not isinstance(region, FrameRegion)
                or region.row < 0
                or region.col < 0
                or region.rows < 1
                or region.cols < 1
                or region.row + region.rows > rows
                or region.col + region.cols > cols
            ):
                violations.append(
                    Violation("write_result", f"{where}: region {region!r} is outside the {rows}x{cols} board")
                )
        return violations

    def _guarded_write(self, plugin: OutputPluginBase, frame: CellFrame, where: str) -> tuple[Any, list[Violation]]:
        try:
            return self._write(plugin, frame), []
        except Exception as exc:
            return None, [Violation("write_result", f"{where} raised {exc!r}; report a failed write instead")]

    def check_write_result(self) -> list[Violation]:
        violations: list[Violation] = []
        plugin = self._plugin()

        self.transport.reset()
        result, raised = self._guarded_write(plugin, self._frame(1), "a healthy write")
        violations += raised
        if result is not None:
            violations += self._well_formed(result, "a healthy write")
            if isinstance(result, WriteResult) and not (result.success and result.was_sent and not result.partial):
                violations.append(Violation("write_result", f"a healthy device's write answered {result!r}"))

        self.transport.reset(fail=lambda index: True)
        result, raised = self._guarded_write(plugin, self._frame(2), "a write to a failing device")
        violations += raised
        if result is not None:
            violations += self._well_formed(result, "a write to a failing device")
            if isinstance(result, WriteResult) and (result.success or result.partial or result.was_sent):
                violations.append(Violation("write_result", f"a write that reached nothing answered {result!r}"))

        for code, where, reset in (
            (3, "a write whose first board request failed", {"fail_board": lambda index: index == 0}),
            (4, "a write whose setup requests failed", {"fail_setup": True}),
        ):
            self.transport.reset(**reset)
            result, raised = self._guarded_write(plugin, self._frame(code), where)
            violations += raised
            if result is not None and isinstance(result, WriteResult):
                violations += self._well_formed(result, where) + self._board_accounting(result)
        return violations

    def _board_accounting(self, result: WriteResult) -> list[Violation]:
        """The write's verdict against the board requests that landed.

        Setup requests (marked ``setup=True``) are not the board write: a
        lost one neither makes a landed write partial nor counts as reaching
        the board.
        """
        board = [r for r in self.transport.requests if not r.setup]
        landed = [r for r in board if not r.failed]
        if landed and len(landed) < len(board) and not (result.partial and result.failed_regions):
            return [
                Violation(
                    "write_result",
                    f"{len(landed)} of {len(board)} board requests landed but the write answered {result!r}: "
                    "report partial=True with the failed_regions (mark a request that is not the board "
                    "write itself setup=True)",
                )
            ]
        if board and not landed and (result.success or result.partial):
            return [Violation("write_result", f"a write that reached nothing answered {result!r}")]
        return []

    def check_device_traffic(self) -> list[Violation]:
        plugin = self._plugin()
        self.transport.reset()
        attempts: list[str] = []
        calls: list[Callable[[], Any]] = [lambda: self._write(plugin, self._frame(1)), plugin.check_connection]
        if plugin.capabilities().animation == "sequence":
            frames = self._sequence_frames(min(plugin.capabilities().max_frames or 4, 4))
            calls.append(lambda: plugin.write_sequence(frames, cancel=CancelToken()))
        with _no_network(attempts, "a write"):
            for call in calls:
                # Other rules judge errors; this one judges traffic.
                with suppress(Exception):
                    call()
        violations: list[Violation] = []
        if attempts:
            violations.append(
                Violation(
                    "device_traffic",
                    f"the plugin opened its own connection ({', '.join(sorted(set(attempts)))}): send every device "
                    "request through self.http, which applies FIESTABOARD_OUTPUTS_ALLOW_HOSTS, timeouts and the "
                    "cancel token",
                )
            )
        bypassed = [r for r in self.transport.requests if not r.via_http]
        if bypassed:
            violations.append(
                Violation(
                    "device_traffic",
                    f"{len(bypassed)} device request(s) bypassed self.http (a test factory that patches the "
                    "plugin's request seam hides its real traffic; the suite routes self.http itself)",
                )
            )
        if not attempts and not self.transport.requests:
            return self._skip("device_traffic", "the plugin made no device request")
        return violations

    def _cancel_run(self, call: Callable[[CancelToken], Any], what: str) -> list[Violation]:
        self.transport.reset(latency=self.latency)
        event = threading.Event()
        done = threading.Event()
        errors: list[BaseException] = []

        def run() -> None:
            try:
                call(CancelToken(event))
            except BaseException as exc:  # reported below
                errors.append(exc)
            finally:
                done.set()

        threading.Thread(target=run, name="conformance-cancel", daemon=True).start()
        deadline = time.monotonic() + self.budget + self.latency * 4
        while not self.transport.requests and not done.is_set() and time.monotonic() < deadline:
            time.sleep(0.005)
        if not self.transport.requests:
            return self._skip("cancel", f"{what} made no device request")
        cancelled_at = time.monotonic()
        event.set()
        violations: list[Violation] = []
        if not done.wait(self.latency + self.budget):
            violations.append(
                Violation("cancel", f"{what} kept running {self.latency + self.budget:.2f}s after cancel")
            )
        late = [r for r in self.transport.requests if r.started > cancelled_at]
        if late:
            violations.append(
                Violation("cancel", f"{what} started {len(late)} device request(s) after it was cancelled")
            )
        if errors:
            violations.append(Violation("cancel", f"{what} raised {errors[0]!r} when cancelled"))
        return violations

    def _sequence_frames(self, count: int) -> list[TimedFrame]:
        return [TimedFrame(self._frame(code), 100) for code in range(1, count + 1)]

    def check_cancel(self) -> list[Violation]:
        plugin = self._plugin()
        violations = self._cancel_run(lambda token: self._write(plugin, self._frame(5), token), "write()")
        if plugin.capabilities().animation == "sequence":
            frames = self._sequence_frames(min(plugin.capabilities().max_frames or 8, 8))
            violations += self._cancel_run(
                lambda token: plugin.write_sequence(frames, cancel=token), "write_sequence()"
            )
        return violations

    def check_sequence(self) -> list[Violation]:
        plugin = self._plugin()
        capabilities = plugin.capabilities()
        if capabilities.animation != "sequence":
            return self._skip("sequence", f"animation is {capabilities.animation!r}")
        max_frames = capabilities.max_frames
        frames = self._sequence_frames(min(max_frames or 8, 8))
        target = frames[-1].frame
        self.transport.reset()
        try:
            result = plugin.write_sequence(frames, cancel=CancelToken())
        except Exception as exc:
            return [Violation("sequence", f"write_sequence raised {exc!r}")]
        violations = self._well_formed(result, "write_sequence")
        if isinstance(result, WriteResult) and not result.success:
            violations.append(Violation("sequence", f"a healthy device's write_sequence answered {result!r}"))
        if self.decode is not None:
            uploaded = [r.frame for r in self.transport.requests if r.frame is not None]
            if max_frames is not None and len(uploaded) > max_frames:
                violations.append(
                    Violation("sequence", f"uploaded {len(uploaded)} frames; the device model allows {max_frames}")
                )
            if not uploaded or uploaded[-1] != target:
                violations.append(Violation("sequence", "the upload does not end on the target frame"))
        elif capabilities.read_back.supported:
            if plugin.read_current() != target:
                violations.append(Violation("sequence", "after write_sequence the device does not show the target"))
        else:
            self._skipped.append("sequence: frame order unchecked (no decode, no read-back)")
        return violations

    def check_check_connection(self) -> list[Violation]:
        plugin = self._plugin()
        violations: list[Violation] = []
        for fails, label in ((False, "a healthy device"), (True, "a failing device")):
            self.transport.reset(fail=(lambda index: True) if fails else None)
            try:
                result = plugin.check_connection()
            except Exception as exc:
                violations.append(Violation("check_connection", f"check_connection raised {exc!r} on {label}"))
                continue
            if not isinstance(result, ConnectionCheck):
                violations.append(
                    Violation("check_connection", f"check_connection returned {type(result).__name__} on {label}")
                )
            elif fails and self.transport.requests and result.success:
                violations.append(
                    Violation("check_connection", "check_connection reported success on a failing device")
                )
        return violations

    # --- running -----------------------------------------------------------------------------

    RULES: tuple[str, ...] = (
        "manifest",
        "character_set",
        "geometry_floor",
        "import_network",
        "device_key",
        "floor",
        "device_traffic",
        "write_result",
        "cancel",
        "sequence",
        "check_connection",
    )

    def run(self, rules: tuple[str, ...] | None = None) -> ConformanceReport:
        """Run *rules* (default: all) and report. A rule that crashes is a
        violation of that rule, never an aborted run."""
        self._skipped = []
        violations: list[Violation] = []
        manifest_violations = self.check_manifest()
        for rule in rules or self.RULES:
            if rule == "manifest":
                violations += manifest_violations
                continue
            if manifest_violations and rule != "import_network":
                self._skipped.append(f"{rule}: the manifest does not load")
                continue
            try:
                violations += getattr(self, f"check_{rule}")()
            except Exception as exc:
                violations.append(Violation(rule, f"the check crashed: {exc!r}"))
        return ConformanceReport(self.plugin_id, violations, list(self._skipped))

    def assert_conformant(self, rules: tuple[str, ...] | None = None) -> ConformanceReport:
        """:meth:`run`, raising ``AssertionError`` with every violation."""
        report = self.run(rules)
        assert report.ok, report.summary()
        return report
