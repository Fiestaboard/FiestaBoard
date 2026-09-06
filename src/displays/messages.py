"""Ad-hoc board message rendering — the shared core of ``POST /send-message``.

Issue #1765: the MCP surface needed a ``send_message`` equivalent, and the
wrap/convert/render core lived only inside the REST handler in
``src.api_server``. It lives here now; the REST handler and the
``send_message`` executor (:mod:`src.ops.executors`) both call it, so the
two surfaces render a message identically: word-wrap to the board's tile
width, honor real newlines (issue #1793), and keep full character/color
marker support (``{red}``, ``{63}``).

Backslashes are deliberately left alone: a JSON body can carry a real
newline, so rewriting a literal ``\\n`` here would only corrupt legitimate
text like ``C:\\new``.
"""

from __future__ import annotations

from typing import Any

from src.text_to_board import text_to_board_array, wrap_message_text


def render_message(
    client: Any,
    text: str,
    *,
    rows: int,
    cols: int,
    strategy: str,
    step_interval_ms: int,
    step_size: int,
) -> tuple[bool, bool]:
    """Wrap ``text`` to a ``rows``×``cols`` grid and render it through ``client``.

    Returns the client's ``(success, was_sent)`` pair unchanged.
    """
    wrapped = wrap_message_text(text, rows=rows, cols=cols)
    board_array = text_to_board_array(wrapped, rows=rows, cols=cols)
    return client.render(
        board_array,
        strategy=strategy,
        step_interval_ms=step_interval_ms,
        step_size=step_size,
    )
