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


# ---------------------------------------------------------------------------
# The v1-superseded cohort (#1941)
# ---------------------------------------------------------------------------
#
# #1934 moved every web-client call that ``/v1`` supersedes onto ``/v1`` and
# left 33 internal endpoints with no product caller. #1936 then closed five of
# the ten places where a v1 route dropped something its internal twin carried.
#
# The 25 below are what survives both a caller audit (``src/mcp_server.py``,
# ``src/ops/executors.py``, ``src/mqtt/commands.py`` and the bundled plugins
# all reach their domains through *services*, not these paths) and an
# exactness audit: for each one, the successor named here answers every fact
# the legacy response carries, accepts every input the legacy route accepts,
# and refuses nothing the legacy route answered. The eight of the 33 that
# failed that test are listed in the PR and on #1941 and are deliberately
# **not** here — a ``successor-version`` link to a route that drops a field is
# worse than no link, because a caller who follows it loses data silently.
#
# These routes are already ``include_in_schema=False`` (#1935), so the notice
# is invisible to a reader of the published document by design. The audience
# is a caller who is *already calling them* — a script in another repo, a
# cron job — and the only place such a caller will ever see a deprecation is
# on the response it is already reading.

#: Removal date for the cohort. Deliberately the same date as the eleven
#: plugin-specific routes (``DEPRECATED_ROUTES_SUNSET`` in
#: ``src/api_server.py``): FiestaBoard cuts a minor release every few days —
#: v8.30.0 to v8.34.0 spans twelve days — so "two releases" is about a week
#: and is not a window an outside integrator can plan against. A quarter is.
#: Two clocks for one appliance would also mean an integrator has to track two
#: dates to find out when their script stops working, so this cohort joins the
#: existing one rather than starting a second countdown a few weeks later.
SUPERSEDED_BY_V1_SUNSET = "Tue, 01 Dec 2026 00:00:00 GMT"

#: ``"<METHOD> <path>"`` -> the ``/v1`` operation that supersedes it, as the
#: URI a caller would use (nginx strips ``/api``, so ``/api/v1/...`` is what
#: goes in the ``Link``). Spelled once here rather than inline at 25 decorators
#: so the cohort can be read, reviewed and deleted as one list.
#:
#: ``tests/test_superseded_route_headers.py`` pins this both ways: every key
#: must name a route the app actually serves and that route must carry the
#: notice, and every route carrying the notice must be a key.
SUPERSEDED_BY_V1: dict[str, str] = {
    # Pages — /v1 delegates to these very handlers.
    "GET /pages": "/api/v1/pages",
    "POST /pages": "/api/v1/pages",
    "GET /pages/{page_id}": "/api/v1/pages/{page_id}",
    "PUT /pages/{page_id}": "/api/v1/pages/{page_id}",
    "DELETE /pages/{page_id}": "/api/v1/pages/{page_id}",
    # Schedules — the five CRUD operations only. The four board-scoped
    # settings routes (enabled / default-page) are excluded: they accept a
    # request with no board at all and answer for the install, and
    # PATCH/GET /v1/boards/{board} has no board-less form.
    "GET /schedules": "/api/v1/schedules",
    "POST /schedules": "/api/v1/schedules",
    "GET /schedules/{schedule_id}": "/api/v1/schedules/{schedule_id}",
    "PUT /schedules/{schedule_id}": "/api/v1/schedules/{schedule_id}",
    "DELETE /schedules/{schedule_id}": "/api/v1/schedules/{schedule_id}",
    # Collections — /v1 delegates to these very handlers.
    "GET /collections": "/api/v1/collections",
    "POST /collections": "/api/v1/collections",
    "GET /collections/{collection_id}": "/api/v1/collections/{collection_id}",
    "PUT /collections/{collection_id}": "/api/v1/collections/{collection_id}",
    "DELETE /collections/{collection_id}": "/api/v1/collections/{collection_id}",
    # Plugins. The three writes collapse into one PATCH, which answers the
    # full PluginDetail — a superset of {plugin_id, config} and of
    # {plugin_id, enabled}, with the same masking.
    "GET /plugins/{plugin_id}": "/api/v1/plugins/{plugin_id}",
    "PUT /plugins/{plugin_id}/config": "/api/v1/plugins/{plugin_id}",
    "POST /plugins/{plugin_id}/enable": "/api/v1/plugins/{plugin_id}",
    "POST /plugins/{plugin_id}/disable": "/api/v1/plugins/{plugin_id}",
    "GET /plugins/{plugin_id}/data": "/api/v1/plugins/{plugin_id}/data",
    # The display read is the same fetch seen twice: v1 carries `lines` and
    # `text`, and `line_count` is len(lines).
    "GET /displays/{display_type}": "/api/v1/plugins/{plugin_id}/data",
    # Template vocabulary. GET /v1/variables is the merge of both of these:
    # both sides read PluginRegistry.get_all_variables() / get_all_max_lengths()
    # (TemplateEngine forwards to them verbatim), and v1 adds the fields
    # neither one had on its own.
    "GET /plugins/variables/all": "/api/v1/variables",
    "GET /templates/variables": "/api/v1/variables",
    "GET /templates/formula-functions": "/api/v1/functions",
    # Service state — same handler, same model.
    "GET /status": "/api/v1/status",
}


def superseded_by_v1(operation: str) -> Callable:
    """Deprecation notice for one of the :data:`SUPERSEDED_BY_V1` operations.

    *operation* is the ``"<METHOD> <path>"`` key, repeated at the decorator so
    a route and its entry in the table cannot drift apart unnoticed: a typo is
    a ``KeyError`` at import, and a route removed from the table without its
    decorator being removed fails the same way.

    Args:
        operation: ``"<METHOD> <path>"``, e.g. ``"GET /pages"``.

    Returns:
        A ``Depends(...)`` for the route's ``dependencies=`` list.
    """
    successor = SUPERSEDED_BY_V1[operation]
    dependency = deprecation_notice(successor=successor, sunset=SUPERSEDED_BY_V1_SUNSET)
    # Read back by tests/test_superseded_route_headers.py so the cohort can be
    # identified on the live route table rather than trusted from this file.
    dependency.dependency.superseded_operation = operation  # type: ignore[attr-defined]
    return dependency
