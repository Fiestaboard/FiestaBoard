"""The device-side seam: what the platform asks of a board connection.

Every board FiestaBoard drives is backed by one of three clients —
:class:`~src.board_client.BoardClient` (Vestaboard local, RW Cloud and
note-array Cloud), :class:`~src.note_array_local_client.NoteArrayLocalClient`
(per-tile LAN fan-out) and :class:`~src.virtual_board_client.VirtualBoardClient`
(FiestaPanel TVs). Until now they were interchangeable only by convention.
:class:`OutputDriver` writes that convention down.

The surface is exactly what code *outside* the client modules uses today,
inventoried from the callers — not what the clients happen to define —
plus one member core declares for itself: ``device_key()``, the identity
the send floor (:mod:`src.outputs.floor`) is keyed by.

- ``send_text`` and ``would_send`` are left out: no caller outside the
  clients uses either, and the output-plugin contract drops ``send_text``.
- Vestaboard transport details (``host``, ``base_url``, ``headers``,
  ``api_key``) are left out: only Vestaboard-specific code reads them, and
  they move behind ``test_connection`` / ``diagnostics`` in a later layer.
- Private attributes (``_last_characters``, ``_cancel_transition``, …) are
  never part of the seam. What callers used to peek at — the dedupe cache,
  the last frame sent — lives on the board's
  :class:`~src.outputs.runtime.OutputRuntime`;
  ``tests/test_output_driver_protocol.py`` holds the peek count at zero.

The Protocol is ``runtime_checkable`` so tests can assert conformance, and
attribute members are declared as properties so ``Mock(spec=OutputDriver)``
exposes them (a bare annotation is invisible to ``dir()``, hence to ``spec``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .runtime import OutputRuntime


@runtime_checkable
class OutputDriver(Protocol):
    """One board's connection, as the display engine and API routes use it.

    Return values keep today's shapes: the send methods return the legacy
    ``(success, was_sent)`` pair, or a :class:`~src.send_outcome.SendOutcome`
    when the caller passes ``with_outcome=True``.
    """

    # --- state the callers read ------------------------------------------------

    @property
    def use_cloud(self) -> bool:
        """True for cloud-backed boards; selects the slower read-poll interval."""
        ...

    @property
    def is_virtual(self) -> bool:
        """True for in-memory boards (FiestaPanel) that drive no hardware."""
        ...

    @property
    def skip_unchanged(self) -> bool:
        """Whether an unchanged grid is acknowledged without a device write."""
        ...

    @skip_unchanged.setter
    def skip_unchanged(self, value: bool) -> None: ...

    @property
    def last_send_throttled(self) -> bool:
        """True when the most recent send was dropped by the send floor."""
        ...

    @property
    def min_send_interval_ms(self) -> int:
        """The device's send floor in milliseconds (0 = unfloored)."""
        ...

    # --- writes ------------------------------------------------------------------

    def send_characters(
        self,
        characters: list[list[int]],
        strategy: Any | None = None,
        step_interval_ms: int | None = None,
        step_size: int | None = None,
        force: bool = False,
        *,
        with_outcome: bool = False,
    ) -> Any:
        """Write one grid, with an optional device-native transition."""
        ...

    def render(
        self,
        characters: list[list[int]],
        *,
        strategy: str | None = None,
        step_interval_ms: int | None = None,
        step_size: int | None = None,
        force: bool = False,
        device_type: str | None = None,
        transition_config: dict | None = None,
        with_outcome: bool = False,
    ) -> Any:
        """Write one grid, driving a ``"plugin:<id>"`` transition when asked."""
        ...

    def set_transition_runner(self, runner: Any | None) -> None:
        """Attach (or detach) the runner that drives plugin transitions."""
        ...

    def set_output_runtime(self, runtime: OutputRuntime) -> None:
        """Take the send lock and cancel token from the board's core runtime."""
        ...

    def device_key(self) -> str:
        """Identity of the device this driver writes, for core state that must
        outlive a driver instance (the send floor). Stable across rebuilds of
        the same saved board; never contains a credential."""
        ...

    # --- reads and cache ---------------------------------------------------------

    def read_current_message(self, sync_cache: bool = False) -> list[list[int]] | None:
        """Read back what the device shows, optionally syncing the runtime's dedupe cache."""
        ...

    def clear_cache(self) -> None:
        """Forget the dedupe cache so the next send goes through."""
        ...

    def get_cache_status(self) -> dict:
        """Dedupe-cache summary for the debug endpoints."""
        ...

    def test_connection(self) -> bool:
        """True when the device answers."""
        ...
