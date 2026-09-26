"""The published API reference has to describe the API that exists.

``docs/reference/api-endpoints.md`` is what fiestaboard.app publishes, and
before ``scripts/generate_api_reference.py`` it was 324 hand-written lines that
had already drifted: they told consumers to call ``POST /send-message`` and
``POST /refresh`` — the two endpoints the product's own web UI never calls —
and said nothing about ``/v1`` or about how a script authenticates.

Generating it is only half the fix. These tests hold the failure modes a
generator can still have:

* the committed page falls behind the schema (the same check CI runs as
  ``--check``, kept here so it fails locally in the same run as the change
  that caused it);
* the page names a route that does not exist, which is worse than no page:
  a reader following it gets a 404 and concludes the product is broken;
* the worked ``curl`` stops being runnable — the exact failure
  ``tests/test_openapi_front_page.py`` already holds for the API description,
  which this page now reuses;
* an operation is published but silently missing from the page, or a
  deprecated alias loses the pointer to its successor.

The route-existence check deliberately mirrors ``_schema_path_for`` from
``tests/test_openapi_front_page.py``: ``/v1/boards/primary/message`` is served
by ``/v1/boards/{board}/message``, so a literal lookup would report the page's
own quick start as a route that does not exist.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from scripts.generate_api_reference import OUTPUT_PATH, build, iter_operations
from src.api_server import app
from src.v1.visibility import build_internal_openapi

REPO_ROOT = Path(__file__).resolve().parent.parent
PAGE = REPO_ROOT / OUTPUT_PATH


@pytest.fixture(scope="module")
def schema() -> dict:
    """The published document — the 33 consumer-facing operations."""
    return app.openapi()


@pytest.fixture(scope="module")
def internal_schema() -> dict:
    """Every route the app actually serves, published or not.

    The page's prose deliberately names internal routes — ``POST
    /auth/mcp-token`` is how you get the token the quick start uses, and the
    v1 descriptions say which internal endpoints they replace. Those mentions
    are correct and useful; what would be wrong is naming a path that answers
    404. So route existence is checked here, and *publication* is checked
    against the published document, per heading.
    """
    return build_internal_openapi(app)


@pytest.fixture(scope="module")
def page() -> str:
    return PAGE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def published_operations(schema) -> set[tuple[str, str]]:
    return {(method.upper(), path) for method, path, _ in iter_operations(schema)}


def _schema_path_for(concrete_path: str, schema: dict) -> str | None:
    """The templated schema path a concrete URL path resolves to."""
    if concrete_path in schema["paths"]:
        return concrete_path
    concrete_segments = concrete_path.strip("/").split("/")
    for candidate in schema["paths"]:
        segments = candidate.strip("/").split("/")
        if len(segments) != len(concrete_segments):
            continue
        if all(
            template.startswith("{") or template == actual
            for template, actual in zip(segments, concrete_segments, strict=True)
        ):
            return candidate
    return None


#: Every ``METHOD /path`` the page renders as inline code. The generator emits
#: operation headings in exactly this shape, and prose picks the same shape up
#: when it names a route.
_SIGNATURE = re.compile(r"`(?P<method>GET|PUT|POST|DELETE|PATCH|HEAD|OPTIONS) (?P<path>/[^`\s]*)`")


def test_the_committed_page_matches_the_generator(page):
    """A stale page is the failure this whole surface exists to prevent."""
    assert page == build(), f"{OUTPUT_PATH} is stale. Regenerate it: python scripts/generate_api_reference.py"


def test_every_route_the_page_names_is_a_route_the_app_serves(page, internal_schema):
    """A reference naming a path that 404s is worse than no reference."""
    named = {(m.group("method"), m.group("path")) for m in _SIGNATURE.finditer(page)}
    assert len(named) >= 33, f"only found {len(named)} route mentions — the extraction broke"

    missing = [
        f"{method} {path}"
        for method, path in sorted(named)
        if (resolved := _schema_path_for(path, internal_schema)) is None
        or method.lower() not in internal_schema["paths"][resolved]
    ]
    assert not missing, f"the page names routes the app does not serve: {missing}"


def test_the_page_documents_every_published_operation(page, published_operations):
    """33 published operations, 33 documented ones — no silent omissions."""
    documented = {
        (match.group("method"), match.group("path"))
        for line in page.splitlines()
        if line.startswith("### ")
        for match in [_SIGNATURE.match(line.removeprefix("### "))]
        if match
    }
    assert documented == published_operations


def test_the_quick_start_curl_calls_a_route_that_exists(page, schema):
    """The hello-world curl must stay executable, not become folklore."""
    match = re.search(r"curl -X (?P<method>[A-Z]+) https?://[^/]+/api(?P<path>/\S+)", page)
    assert match, "the page must carry a runnable curl example"
    path, method = match.group("path"), match.group("method").lower()
    schema_path = _schema_path_for(path, schema)
    assert schema_path is not None, f"the curl example calls {path}, which is not a published route"
    assert method in schema["paths"][schema_path], (
        f"the curl example uses {method.upper()} {path}; {schema_path} offers {sorted(schema['paths'][schema_path])}"
    )


def test_the_quick_start_curl_authenticates(page):
    """A script could not authenticate at all before /v1, and the old page never said so."""
    quick_start = page.split("## Quick start", 1)[1].split("\n## ", 1)[0]
    assert "Authorization: Bearer" in quick_start


def test_the_page_leads_with_the_front_door(page, schema):
    """`/v1` is the surface a consumer should build against, so it goes first."""
    first_curl = re.search(r"curl -X [A-Z]+ https?://[^/]+/api(?P<path>/\S+)", page)
    assert first_curl and first_curl.group("path").startswith("/v1/")
    # `primary` is the whole reason a single-board install never learns board ids.
    assert "/v1/boards/primary/message" in first_curl.group("path")


def test_every_deprecated_operation_names_its_successor(page, schema):
    """A deprecation with no forward pointer just strands the reader."""
    deprecated = [
        f"{method.upper()} {path}" for method, path, operation in iter_operations(schema) if operation.get("deprecated")
    ]
    assert deprecated, "expected the two published legacy aliases to be flagged deprecated"

    for signature in deprecated:
        section = page.split(f"### `{signature}`", 1)
        assert len(section) == 2, f"{signature} has no section on the page"
        body = section[1].split("\n### ", 1)[0]
        assert ":::warning Deprecated" in body, f"{signature} is not marked deprecated on the page"
        assert "Use `" in body and "` instead." in body, f"{signature} is marked deprecated but names no successor"


def test_the_page_reuses_the_api_description_rather_than_restating_it(page):
    """Two hand-written introductions is the drift this generator removes."""
    from src.api_server import API_DESCRIPTION

    # The first line of the front page, verbatim: the page's introduction is
    # that text, not a second one written next to it.
    assert API_DESCRIPTION.splitlines()[0] in page


def test_the_page_says_it_is_generated(page):
    """Without the banner the next person edits it by hand and CI rejects them."""
    assert "GENERATED FILE — DO NOT EDIT BY HAND" in page
    assert "scripts/generate_api_reference.py" in page
