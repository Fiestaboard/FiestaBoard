"""Which routes a native Bearer credential may call, by scope.

Native sign-ins never become browser sessions. Each one carries a scope that
names an explicit allow-list here; anything not listed is refused with 403
before a handler runs. New routes are therefore denied to native clients until
someone adds them on purpose.

* ``tv_panels`` (``fb_tv_`` tokens, Apple TV and Android TV): the panel viewer
  routes only. The middleware further limits ``PATCH /panels/{id}`` to the
  screen presentation fields.
* ``control`` (``fb_mob_`` tokens, the iOS and Android apps): the consumer
  ``/v1`` API plus the internal routes the phone apps need to show and change
  what a display shows, edit pages and schedules, set up integrations, manage
  TVs and read diagnostics. It never reaches account and credential
  management, backups, the host (network, update, restart), installing or
  removing code, or settings that hold third-party secrets (AI keys, MQTT,
  ``/config/board``). It may approve or deny a TV's sign-in code (H11), but
  never create pairing codes for other phones (``/auth/pairing``). It may
  list and sign out the account's TVs (H10b), never browsers or phones.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

TV_PANELS = "tv_panels"
CONTROL = "control"

TV_CLIENTS = frozenset({"fiestaboard-tvos", "fiestaboard-androidtv"})
MOBILE_CLIENTS = frozenset({"fiestaboard-ios", "fiestaboard-android"})


def scope_for_client(client_id: str) -> str:
    if client_id in MOBILE_CLIENTS:
        return CONTROL
    if client_id in TV_CLIENTS:
        return TV_PANELS
    raise ValueError(f"unknown native client: {client_id}")


@dataclass(frozen=True)
class Rule:
    methods: frozenset[str]
    pattern: re.Pattern[str]

    @property
    def literal(self) -> bool:
        """True when the rule names one exact path (no ``{}`` segment, no catch-all)."""
        return _SEG not in self.pattern.pattern and ".*" not in self.pattern.pattern

    def matches(self, method: str, path: str) -> bool:
        return method in self.methods and self.pattern.fullmatch(path) is not None

    def __str__(self) -> str:
        return f"{','.join(sorted(self.methods))} {self.pattern.pattern}"


_SEG = "[^/]+"


def _rule(methods: str, path: str) -> Rule:
    """``path`` uses ``{}`` for one path segment and is otherwise literal."""
    pattern = "".join(_SEG if part == "{}" else re.escape(part) for part in re.split(r"(\{\})", path))
    return Rule(frozenset(methods.split(",")), re.compile(pattern))


def _rules(*rows: tuple[str, str]) -> tuple[Rule, ...]:
    return tuple(_rule(methods, path) for methods, path in rows)


TV_PANELS_RULES = _rules(
    ("GET", "/auth/status"),
    ("GET", "/panels"),
    ("GET", "/panel/{}"),
    ("GET", "/panel/{}/frame"),
    ("PATCH", "/panels/{}"),
    ("DELETE", "/auth/device/session"),
)

_ANY = "GET,POST,PUT,PATCH,DELETE"

CONTROL_RULES = (
    # The consumer API, whole: it is the surface a script with the API token gets.
    Rule(frozenset(_ANY.split(",")), re.compile(r"/v1(?:/.*)?")),
    *_rules(
        # Identity and signing this phone out.
        ("GET", "/auth/status"),
        ("DELETE", "/auth/device/session"),
        # Approving a TV from the phone (H11). The handler accepts TV codes only.
        ("POST", "/auth/device/inspect"),
        ("POST", "/auth/device/approve"),
        ("POST", "/auth/device/deny"),
        # Listing and signing out the account's TVs (H10b, Jev D14). TV sessions only;
        # /auth/sessions (browsers and phones) stays with the browser.
        ("GET", "/auth/device/tvs"),
        ("DELETE", "/auth/device/tvs/{}"),
        # Home: what each display shows, and its state.
        ("GET", "/status"),
        ("GET", "/version"),
        ("GET", "/silence-status"),
        ("GET", "/board/current-message"),
        ("DELETE", "/board/external-frame"),
        ("GET", "/displays"),
        ("GET", "/displays/{}"),
        ("GET,POST,DELETE", "/settings/temporary-override"),
        ("GET", "/settings/temporary-overrides"),
        ("GET,PUT", "/settings/active-page"),
        ("PUT", "/settings/silence-schedule"),
        ("POST", "/settings/board/{}/pause"),
        ("POST", "/settings/board/{}/identify"),
        ("GET", "/settings/location/sun-times"),
        ("GET", "/settings/location/sun-times-week"),
        ("GET", "/triggers"),
        ("GET", "/triggers/active"),
        ("POST", "/triggers/{}/dismiss"),
        # Compose and pages.
        ("GET,POST", "/pages"),
        ("GET,PUT,DELETE", "/pages/{}"),
        ("POST", "/pages/{}/preview"),
        ("POST", "/pages/{}/send"),
        ("GET", "/pages/{}/share"),
        ("POST", "/pages/preview/batch"),
        ("GET", "/pages/current-display"),
        # H9a: drafts, saved versions and restore. Page-content writes the phone
        # already has through PUT /pages/{}; restore writes the draft, never the page.
        ("GET", "/pages/drafts"),
        ("GET,PUT,DELETE", "/pages/{}/draft"),
        ("POST", "/pages/{}/draft/publish"),
        ("GET", "/pages/{}/revisions"),
        ("GET", "/pages/{}/revisions/{}"),
        ("POST", "/pages/{}/revisions/{}/restore"),
        # H9b: what happened when the page was sent. Read-only.
        ("GET", "/pages/{}/sends"),
        # H9c: copy a page for another display (a page create, as POST /pages), and the tag facet.
        ("POST", "/pages/{}/duplicate"),
        ("GET", "/pages/tags"),
        # Shape collision with POST /pages/{}/preview, listed on purpose: it decodes a
        # share string and saves nothing. POST /pages/import (which saves) stays denied.
        ("POST", "/pages/import/preview"),
        ("GET,POST", "/collections"),
        ("GET,PUT,DELETE", "/collections/{}"),
        # H8: the rule tester's dry run. Read-only; stores nothing.
        ("POST", "/collections/{}/dry-run"),
        ("POST", "/templates/render"),
        ("POST", "/templates/render/live"),
        ("POST", "/templates/validate"),
        ("GET", "/templates/variables"),
        ("GET", "/templates/formula-functions"),
        # Schedule.
        ("GET,POST", "/schedules"),
        ("GET,PUT,DELETE", "/schedules/{}"),
        ("GET", "/schedules/active/page"),
        ("GET,PUT", "/schedules/default-page"),
        ("GET,PUT", "/schedules/enabled"),
        ("GET,PUT", "/schedules/settings"),
        ("POST", "/schedules/validate"),
        # Integrations: configure what is installed; installing code is not here.
        ("GET", "/plugins"),
        ("GET", "/plugins/errors"),
        ("GET", "/plugins/updates"),
        ("GET", "/plugins/variables/all"),
        # Shape collision with GET /plugins/{}, listed on purpose: the read-only
        # marketplace listing. Installing from it stays denied.
        ("GET", "/plugins/registry"),
        ("GET", "/plugins/{}"),
        ("GET", "/plugins/{}/manifest"),
        ("GET", "/plugins/{}/variables"),
        ("GET", "/plugins/{}/data"),
        ("PUT", "/plugins/{}/config"),
        ("POST", "/plugins/{}/enable"),
        ("POST", "/plugins/{}/disable"),
        ("GET,POST", "/plugins/{}/instances"),
        ("DELETE", "/plugins/{}/instances/{}"),
        ("POST", "/plugins/{}/options/{}"),
        ("GET", "/home-assistant/entities"),
        ("GET", "/oauth/connections"),
        ("GET,DELETE", "/oauth/connections/{}"),
        ("POST", "/oauth/connections/{}/authorize"),
        ("POST", "/oauth/connections/{}/complete"),
        # Settings-form helpers that bundled plugins' schemas call.
        ("GET", "/muni/stops"),
        ("GET", "/muni/stops/nearby"),
        ("GET", "/muni/stops/search"),
        ("GET", "/baywheels/stations"),
        ("GET", "/baywheels/stations/nearby"),
        ("GET", "/baywheels/stations/search"),
        ("GET", "/stocks/search"),
        ("POST", "/stocks/validate"),
        ("POST", "/traffic/routes/geocode"),
        ("POST", "/traffic/routes/validate"),
        # Displays and their outputs: run device actions, not install outputs.
        ("GET", "/outputs"),
        ("GET", "/outputs/available"),
        ("GET", "/outputs/catalog"),
        ("POST", "/outputs/{}/actions/{}"),
        ("POST", "/boards/{}/actions/{}"),
        # TVs managed from the phone.
        ("GET,POST", "/panels"),
        ("PATCH,DELETE", "/panels/{}"),
        ("POST", "/panels/geometry"),
        ("GET", "/panel/{}"),
        ("GET", "/panel/{}/frame"),
        # Diagnostics and update status (read-only, plus a connection test).
        ("GET", "/config/general"),
        ("GET", "/debug/network-diagnostics"),
        ("GET", "/debug/system-info"),
        ("POST", "/debug/test-connection"),
        ("POST", "/config/board/test"),
        ("GET", "/system/update-check"),
        ("GET", "/system/update/status"),
    ),
)

_RULES = {TV_PANELS: TV_PANELS_RULES, CONTROL: CONTROL_RULES}


def _normalize(scope: str, path: str) -> str:
    # The control surface accepts the nginx ``/api`` double form, as ``/v1``
    # and ``/mcp`` already do. The TV scope never did; leave it as it was.
    if scope == CONTROL and (path == "/api" or path.startswith("/api/")):
        return path[len("/api") :] or "/"
    return path


def permits(scope: str, method: str, path: str) -> bool:
    rules = _RULES.get(scope, ())
    path = _normalize(scope, path)
    return any(rule.matches(method.upper(), path) for rule in rules)
