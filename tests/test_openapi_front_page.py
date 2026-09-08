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
"""

from __future__ import annotations

import re

import pytest

from src.api_server import API_DESCRIPTION, OPENAPI_TAGS, app


@pytest.fixture(scope="module")
def schema() -> dict:
    return app.openapi()


@pytest.fixture(scope="module")
def used_tags(schema) -> set[str]:
    tags: set[str] = set()
    for operations in schema["paths"].values():
        for operation in operations.values():
            tags.update(operation.get("tags", []))
    return tags


def test_every_tag_a_route_uses_is_described(used_tags):
    """An undescribed tag is a bare heading in the docs sidebar."""
    described = {tag["name"] for tag in OPENAPI_TAGS if tag.get("description")}
    assert used_tags <= described, (
        f"tags used by routes but not described in OPENAPI_TAGS: {sorted(used_tags - described)}"
    )


def test_no_described_tag_is_stale(used_tags):
    """A described tag no route uses renders an empty section."""
    declared = {tag["name"] for tag in OPENAPI_TAGS}
    assert declared <= used_tags, f"described tags no route uses: {sorted(declared - used_tags)}"


def test_the_tag_order_is_the_declared_order(schema):
    """Swagger renders tags in ``openapi_tags`` order; boards/content lead."""
    assert [tag["name"] for tag in schema["tags"]] == [tag["name"] for tag in OPENAPI_TAGS]
    assert schema["tags"][0]["name"] == "service"
    assert [t["name"] for t in schema["tags"]].index("pages") < [t["name"] for t in schema["tags"]].index("debug")


def test_the_front_page_worked_example_calls_a_route_that_exists():
    """The hello-world curl must stay executable, not become folklore."""
    match = re.search(r"curl -X (?P<method>[A-Z]+) https?://[^/]+/api(?P<path>/\S+)", API_DESCRIPTION)
    assert match, "the front page must carry a runnable curl example"
    path, method = match.group("path"), match.group("method").lower()
    operations = app.openapi()["paths"].get(path)
    assert operations is not None, f"front-page example calls {path}, which is not a route"
    assert method in operations, f"front-page example uses {method.upper()} {path}; route offers {sorted(operations)}"


def test_the_front_page_says_more_than_the_old_one_line():
    """A one-sentence description is a placeholder, not a front page."""
    assert "```bash" in API_DESCRIPTION
    assert "/api/docs" in API_DESCRIPTION
    assert "FIESTABOARD_AUTH_ENABLED" in API_DESCRIPTION
