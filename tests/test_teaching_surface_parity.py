"""Every language construct must be taught on every surface that teaches.

Formula *functions* were already generated from the live registry, so a new
function reached both the MCP instructions and the chat prompt for free. New
*syntax* did not: the prose lived in two hand-written copies
(``src.ops.teaching`` for MCP, ``src.ai.prompt_builder`` for FiestaBot), which
is how the MCP copy came to advertise filters that did not exist (#1764).

These tests are the lock. A construct added to ``LANGUAGE_CONSTRUCTS`` but left
out of a surface fails here rather than silently leaving FiestaBot unable to use
a feature the app shipped.
"""

from __future__ import annotations

import pytest

from src.ai.prompt_builder import build_prompt
from src.ops import teaching
from src.templates.expressions import function_signatures


def _bot_prompt() -> str:
    """The system prompt FiestaBot is actually sent."""
    return build_prompt(device_type="flagship", user_prompt="hi", variables={}).system_prompt


def _mcp_block() -> str:
    return teaching.template_syntax_block()


@pytest.fixture(scope="module")
def surfaces() -> dict[str, str]:
    return {"mcp": _mcp_block(), "bot": _bot_prompt()}


def test_there_is_at_least_one_construct_registered():
    assert teaching.LANGUAGE_CONSTRUCTS, "the construct registry drives every parity check below"


@pytest.mark.parametrize("construct", [c.name for c in teaching.LANGUAGE_CONSTRUCTS])
def test_every_construct_is_taught_on_every_surface(construct, surfaces):
    example = next(c.example for c in teaching.LANGUAGE_CONSTRUCTS if c.name == construct)
    for surface_name, text in surfaces.items():
        assert example in text, f"{construct} is missing from the {surface_name} teaching surface"


@pytest.mark.parametrize("function_name", sorted(function_signatures()))
def test_every_formula_function_is_listed_on_every_surface(function_name, surfaces):
    for surface_name, text in surfaces.items():
        assert function_name in text, f"{function_name} is missing from the {surface_name} teaching surface"


def test_array_iteration_is_taught_not_just_indexing(surfaces):
    # The gap issue #2050 reported: the prompt described indexing only, so the
    # model hand-unrolled lines the same way users had to.
    for surface_name, text in surfaces.items():
        assert "FOREACH" in text, f"{surface_name} does not teach iteration"
        assert "COUNT" in text, f"{surface_name} does not teach counting"


def test_the_bot_prompt_lists_array_variables_with_their_item_fields():
    # Array variables used to be dropped from the metadata catalog the prompt
    # renders, so FiestaBot could not name a single real array.
    variables = {
        "mlb": {
            "games": {
                "description": "Today's games",
                "type": "array",
                "item_fields": ["team1", "score1"],
                "label_field": "team1",
            },
            "updated": {"description": "Last refresh"},
        }
    }
    prompt = build_prompt(device_type="flagship", user_prompt="hi", variables=variables).system_prompt
    assert "mlb.games (ARRAY; item fields: score1, team1)" in prompt
    assert "COUNT(mlb.games)" in prompt
    # The example iterates the manifest's label_field, not just any field.
    assert "FOREACH(mlb.games, item.team1, 4)" in prompt

    # A plain variable is still offered as a substitution, not as an array.
    assert "{{mlb.updated}}" in prompt
