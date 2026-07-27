"""Template transition plugin.

Copy this directory to ``plugins/<your_id>/`` and update the manifest
and class below to build your own transition.  See
``docs/development/TRANSITION_PLUGIN_DEVELOPMENT.md`` for the full guide.
"""

from collections.abc import Iterator
from typing import Any

from src.plugins.base import TransitionPluginBase


class MyTransition(TransitionPluginBase):
    """Replace this with your transition's behavior."""

    @property
    def plugin_id(self) -> str:
        # Must match manifest "id".
        return "my_transition"

    def generate_frames(
        self,
        from_grid: list[list[int]],
        to_grid: list[list[int]],
        device: Any,
        config: dict[str, Any],
    ) -> Iterator[tuple[list[list[int]], int]]:
        """Yield (frame_grid, delay_ms_before_next) tuples.

        The runner sends each grid to the board then waits delay_ms
        (clamped to ``min_interval_ms`` from the manifest) before pulling
        the next frame.  After your generator exhausts, the runner
        unconditionally sends ``to_grid`` so the board lands on target.
        """
        speed_ms = int(config.get("speed_ms", 100))

        # Trivial example: emit a single intermediate frame, then yield
        # nothing more (runner snaps to target).  Replace with your
        # actual animation.
        intermediate = [list(row) for row in from_grid]
        yield intermediate, speed_ms
