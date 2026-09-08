"""Deprecation notices on the wire, in one place.

``deprecated=True`` on a route only greys the operation out in Swagger. The
callers a deprecation actually exists for — a script in another repo, a
plugin's SETUP guide, someone's cron job — never open Swagger. RFC 9745
(``Deprecation``) and RFC 8594 (``Sunset``), plus an RFC 8288 ``Link`` naming
the replacement, put the notice where those callers will see it: on every
response.

``src/api_server.py`` grew the first copy of this for the eleven deprecated
plugin-specific routes (#1932). This module is that machinery lifted out so
the second and third users — ``POST /send-message`` and ``POST /refresh``,
the two legacy operations the published docs name and which therefore stay
in the consumer schema after everything else is hidden — reuse it rather than
growing a parallel mechanism.

Which headers get sent is a deliberate per-caller choice:

``Deprecation``
    Always. It is the whole point.
``Link: rel="successor-version"``
    Whenever a replacement exists. Omitted where one genuinely does not
    (``GET /transit/cache/status``).
``Sunset``
    Only where a removal date has actually been agreed. The eleven plugin
    routes have one (#1915). ``/send-message`` and ``/refresh`` do not:
    they are the endpoints the published documentation recommends, and
    stamping a date on them would announce a removal nobody has scheduled.
    An unbacked ``Sunset`` is worse than none — it teaches integrators that
    the header is noise.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Response


def successor_link(uri: str) -> str:
    """An RFC 8288 ``Link`` value naming *uri* as the replacement.

    *uri* may be a URI Template (RFC 6570) — ``/api/v1/boards/{board}/message``
    — because the successor of a flat legacy route is frequently a
    parameterised one, and a caller can read the template.
    """
    return f'<{uri}>; rel="successor-version"'


def deprecation_notice(
    *,
    successor: str | None = None,
    sunset: str | None = None,
) -> Callable:
    """A FastAPI dependency that stamps the deprecation headers on a response.

    Args:
        successor: URI (or URI Template) of the replacement, sent as
            ``Link: rel="successor-version"``. ``None`` sends no ``Link``.
        sunset: An HTTP-date at which the route is scheduled to be removed,
            sent as ``Sunset``. ``None`` sends no ``Sunset`` — see the module
            docstring for why that is the default rather than an oversight.

    Returns:
        A ``Depends(...)`` to put in a route's ``dependencies=`` list.
    """
    link = successor_link(successor) if successor else None

    def _set_deprecation_headers(response: Response) -> None:
        response.headers["Deprecation"] = "true"
        if sunset is not None:
            response.headers["Sunset"] = sunset
        if link is not None:
            response.headers["Link"] = link

    # Read back by tests so a route's advertised successor can be pinned
    # without calling the successor.
    _set_deprecation_headers.successor_uri = successor  # type: ignore[attr-defined]
    _set_deprecation_headers.sunset = sunset  # type: ignore[attr-defined]
    return Depends(_set_deprecation_headers)


#: The v1 replacement for both legacy write operations. ``POST`` puts content
#: on the board (``/send-message``); ``DELETE`` reverts it to whatever the
#: schedule says and re-drives the board, which is what ``POST /refresh``
#: does — ``src/v1/routes_boards.py`` calls ``refresh_display`` outright. A
#: ``Link`` relation names a resource, not a method, so the two share one.
V1_BOARD_MESSAGE_SUCCESSOR = "/api/v1/boards/{board}/message"
