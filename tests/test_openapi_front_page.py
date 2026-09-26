"""`/api/docs` has to be readable by someone who has never seen this API.

Before this, ``description`` was 71 characters ("REST API for controlling and
monitoring the FiestaBoard Display Service") and ``openapi_tags`` was absent,
so Swagger rendered 22 bare tag names in first-appearance-in-the-paths-object
order: MQTT, AI, system updates and Wi-Fi configuration all scrolled past
before anything about a board, with ``pages`` fourteenth — below ``debug``.

These tests hold the two failure modes that silently return:

* a new router lands with a tag nobody described, and Swagger grows another
  bare heading at the bottom;
* the front page's worked example drifts away from a route that exists.

Two documents, and which one each test reads is load-bearing. Since
``src/v1/visibility.py`` hid the internal surface, the **published** document
carries 33 operations across three tags, and the **internal** one
(``/api/internal/openapi.json``) carries all ~230 across all twenty-three.
The "nobody described this tag" failure lives in the internal document — that
is where a new router's tag first appears — so checking it against the
published one would go quietly vacuous the moment a router is internal, which
is every router.
"""

from __future__ import annotations

import re

import pytest

from src.api_server import API_DESCRIPTION, OPENAPI_TAGS, app
from src.v1.visibility import build_internal_openapi


@pytest.fixture(scope="module")
def schema() -> dict:
    """The published, consumer-facing document — 33 operations."""
    return app.openapi()


@pytest.fixture(scope="module")
def internal_schema() -> dict:
    """Every operation the app serves, including the hidden ones."""
    return build_internal_openapi(app)


def _tags_used_by(schema: dict) -> set[str]:
    tags: set[str] = set()
    for operations in schema["paths"].values():
        for operation in operations.values():
            tags.update(operation.get("tags", []))
    return tags


@pytest.fixture(scope="module")
def used_tags(internal_schema) -> set[str]:
    """Tags used by *any* route, hidden or not — where the failure lands."""
    return _tags_used_by(internal_schema)


def test_every_tag_a_route_uses_is_described(used_tags, internal_schema):
    """An undescribed tag is a bare heading in the docs sidebar.

    Checked against the schema, not ``OPENAPI_TAGS``: `v1` describes itself in
    ``src/v1/openapi.py`` and is prepended there, so the constant is only one
    of the document's two inputs.
    """
    described = {tag["name"] for tag in internal_schema["tags"] if tag.get("description")}
    assert used_tags <= described, (
        f"tags used by routes but not described in the schema: {sorted(used_tags - described)}"
    )


def test_no_described_tag_is_stale(used_tags, internal_schema):
    """A described tag no route uses renders an empty section."""
    declared = {tag["name"] for tag in internal_schema["tags"]}
    assert declared <= used_tags, f"described tags no route uses: {sorted(declared - used_tags)}"


def test_the_published_document_describes_only_the_tags_it_publishes(schema):
    """Twenty stale headings would be exactly the noise this surface removed.

    ``build_openapi`` filters the declared tag list down to the tags the
    document's own operations use, so hiding the internal surface takes its
    tag descriptions with it.
    """
    assert {tag["name"] for tag in schema["tags"]} == _tags_used_by(schema)
    assert len(schema["tags"]) < len(OPENAPI_TAGS)


def test_the_tag_order_is_the_declared_order(schema, internal_schema):
    """Swagger renders tags in schema order; the consumer surface leads.

    Asserted against the schema rather than ``OPENAPI_TAGS``. That constant is
    only one input: ``src/v1/openapi.py`` prepends the ``v1`` tag, because v1
    owns its own description and cannot be imported this early in
    ``api_server``. Comparing to the input would have pinned a list the
    document does not actually publish.
    """
    declared_order = ["v1"] + [tag["name"] for tag in OPENAPI_TAGS]
    published = [tag["name"] for tag in schema["tags"]]

    # The published list is the declared list filtered to what it uses, so it
    # must be a subsequence of it — same order, no reshuffling.
    assert published == [name for name in declared_order if name in set(published)]
    assert published[0] == "v1", "the consumer surface must be the first thing a newcomer sees"

    internal = [tag["name"] for tag in internal_schema["tags"]]
    assert internal == declared_order
    assert internal.index("pages") < internal.index("debug")


def _schema_path_for(concrete_path: str, schema: dict) -> str | None:
    """The templated schema path a concrete URL path resolves to.

    ``/v1/boards/primary/message`` is served by ``/v1/boards/{board}/message``,
    so a literal dictionary lookup would report the front page's own worked
    example as a route that does not exist.
    """
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


def test_the_front_page_worked_example_calls_a_route_that_exists(schema):
    """The hello-world curl must stay executable, not become folklore."""
    match = re.search(r"curl -X (?P<method>[A-Z]+) https?://[^/]+/api(?P<path>/\S+)", API_DESCRIPTION)
    assert match, "the front page must carry a runnable curl example"
    path, method = match.group("path"), match.group("method").lower()
    schema_path = _schema_path_for(path, schema)
    assert schema_path is not None, f"front-page example calls {path}, which is not a published route"
    operations = schema["paths"][schema_path]
    assert method in operations, (
        f"front-page example uses {method.upper()} {path}; {schema_path} offers {sorted(operations)}"
    )


def test_the_front_page_leads_with_the_consumer_surface():
    """The whole point of hiding 198 operations is that /v1 is what is found.

    A front page whose worked example is one of the two deprecated legacy
    paths would leave the newcomer exactly where they started.
    """
    match = re.search(r"curl -X [A-Z]+ https?://[^/]+/api(?P<path>/\S+)", API_DESCRIPTION)
    assert match and match.group("path").startswith("/v1/")


def test_the_front_page_says_where_the_hidden_surface_went():
    """A reader must not take "undocumented" for "removed"."""
    assert "/api/internal/openapi.json" in API_DESCRIPTION


def test_the_front_page_says_more_than_the_old_one_line():
    """A one-sentence description is a placeholder, not a front page."""
    assert "```bash" in API_DESCRIPTION
    assert "/api/docs" in API_DESCRIPTION
    assert "FIESTABOARD_AUTH_ENABLED" in API_DESCRIPTION
