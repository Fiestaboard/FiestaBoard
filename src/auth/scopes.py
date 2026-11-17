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
  management, installing code from a Git URL, the update channel, or settings
  that hold third-party secrets in the clear (MQTT, ``/config/board``).
  Registry plugin install, update and uninstall (H21c), and the hub's Wi-Fi
  changes, software update, restart, AI provider changes and backups (H21d)
  are tier 2. It may approve or deny a TV's sign-in code (H11), but
  never create pairing codes for other phones (``/auth/pairing``). It may
  list and sign out the account's TVs (H10b), never browsers or phones.

  Tier-2 routes (H21s) are listed separately in ``CONTROL_STEP_UP_RULES``. The
  phone reaches them only while its sign-in is stepped up: the password was
  re-entered on that phone in the last ten minutes (``src/auth/step_up.py``).
  Without that the middleware answers ``403 step_up_required``.
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
        # H21s: step up (re-enter the password) for tier-2 actions, read or end it.
        ("GET,POST,DELETE", "/auth/device/elevate"),
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
        ("POST", "/settings/temporary-override/undo"),
        ("GET,PUT", "/settings/active-page"),
        ("PUT", "/settings/silence-schedule"),
        ("POST", "/settings/board/{}/pause"),
        ("POST", "/settings/board/{}/identify"),
        # H21a tier 1: add, change and remove displays (every display type, MQTT
        # included), detect a board's size, and display settings. Changing a
        # display's connection while echoing a masked key is refused
        # (src/auth/phone_policy.py). Installing outputs stays browser-only.
        ("GET,PUT", "/settings/board"),
        ("POST", "/settings/board/add"),
        ("DELETE", "/settings/board/{}"),
        ("POST", "/settings/board/{}/detect-size"),
        ("POST", "/outputs/{}/boards"),
        ("GET,PUT", "/settings/display"),
        ("GET,PUT", "/settings/transitions"),
        ("GET,PUT", "/settings/polling"),
        ("GET,PUT", "/settings/location"),
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
        # H21c tier 1: ask the plugin sources whether updates exist. Changes no code.
        ("POST", "/plugins/updates/check"),
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
        ("GET,PUT", "/config/general"),
        ("GET", "/debug/network-diagnostics"),
        ("GET", "/debug/system-info"),
        ("POST", "/debug/test-connection"),
        ("POST", "/config/board/test"),
        ("GET", "/system/update-check"),
        ("GET", "/system/update/status"),
        # H21d tier 1: Wi-Fi reads and a scan; AI settings read (keys and header
        # values masked) and tested by provider id (src/auth/phone_policy.py).
        ("GET", "/network/wifi/capability"),
        ("GET", "/network/wifi/status"),
        ("GET", "/network/wifi/saved"),
        ("POST", "/network/wifi/scan"),
        ("GET", "/settings/ai"),
        ("GET", "/settings/ai/providers/{}/models"),
        ("POST", "/settings/ai/test"),
        # H21b: FiestaBot. Every tool and op the chat runs for a phone goes through
        # the default-deny table in src/ai/phone_tools.py, checked when it runs.
        ("POST", "/pages/ai/chat"),
        ("POST", "/pages/ai/generate"),
        ("POST", "/ai/operations"),
        ("GET,DELETE", "/ai/conversations"),
        ("GET,PUT,PATCH,DELETE", "/ai/conversations/{}"),
        ("GET", "/ai/conversations/{}/export"),
    ),
)

# H21s tier 2: reachable by ``control`` only with a live step-up elevation.
# Each ticket that widens the phone (H21c, H21d) adds its rows here, with a test.
CONTROL_STEP_UP_RULES: tuple[Rule, ...] = _rules(
    # H21c: plugin lifecycle from the curated registry. Install from a Git URL
    # (POST /plugins/install) runs arbitrary code and stays browser-only.
    ("POST", "/plugins/registry/{}/install"),
    ("POST", "/plugins/{}/update"),
    ("POST", "/plugins/updates/apply"),
    ("DELETE", "/plugins/{}/uninstall"),
    # H21d: the hub's network, software and AI provider. Changing a provider's
    # endpoint needs its key typed again. The update channel stays browser-only.
    ("POST", "/network/wifi/connect"),
    ("POST", "/network/wifi/disconnect"),
    ("DELETE", "/network/wifi/saved/{}"),
    ("PUT", "/settings/ai"),
    ("POST", "/system/update"),
    ("POST", "/system/restart"),
    ("POST", "/system/shutdown"),
    # A phone's export is redacted; its import never re-clones plugins.
    ("GET", "/backup/export"),
    ("POST", "/backup/import"),
)

_RULES = {TV_PANELS: TV_PANELS_RULES, CONTROL: CONTROL_RULES}


def _normalize(scope: str, path: str) -> str:
    # The control surface accepts the nginx ``/api`` double form, as ``/v1``
    # and ``/mcp`` already do. The TV scope never did; leave it as it was.
    if scope == CONTROL and (path == "/api" or path.startswith("/api/")):
        return path[len("/api") :] or "/"
    return path


def _step_up_rules(scope: str) -> tuple[Rule, ...]:
    # Read at call time so the module attribute is the one source of truth.
    return CONTROL_STEP_UP_RULES if scope == CONTROL else ()


def requires_step_up(scope: str, method: str, path: str) -> bool:
    """True when ``method path`` is a tier-2 route for *scope* (needs a step-up).

    A step-up rule wins over an ordinary rule that also matches, so a broad
    pattern can never let a tier-2 route through without the elevation.
    """
    path = _normalize(scope, path)
    return any(rule.matches(method.upper(), path) for rule in _step_up_rules(scope))


def permits(scope: str, method: str, path: str) -> bool:
    """True when *scope* may reach ``method path`` at all (tier 2 included).

    ``requires_step_up`` then says whether the route also needs an elevation.
    """
    rules = _RULES.get(scope, ())
    path = _normalize(scope, path)
    method = method.upper()
    return any(rule.matches(method, path) for rule in (*rules, *_step_up_rules(scope)))
