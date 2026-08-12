"""The mock LLM's provider rules must match the canonical emulators.

``tests/ai/provider_emulators.py`` encodes what each provider rejects and is
where the source citations live. ``integration-tests/mock-llm/server.py``
re-states a subset of those rules, because it runs in its own container as a
stdlib-only script and cannot import from ``tests/``.

Two copies of a rule drift. When they do, the E2E suite silently stops
emulating the provider it claims to — which is exactly the failure that let
#1560 ship, one level up. This module fails when they disagree.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from tests.ai.provider_emulators import BY_NAME

MOCK_LLM = Path(__file__).resolve().parent.parent / "integration-tests" / "mock-llm" / "server.py"


@pytest.fixture(scope="module")
def mock_server():
    """Import the mock server by path — it is not an installed package."""
    spec = importlib.util.spec_from_file_location("mock_llm_server", MOCK_LLM)
    assert spec and spec.loader, f"could not load {MOCK_LLM}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_mock_llm_source_exists():
    assert MOCK_LLM.is_file(), f"{MOCK_LLM} is missing; the E2E provider tests depend on it"


def test_every_mock_provider_except_permissive_has_an_emulator(mock_server):
    named = set(mock_server.PROVIDERS) - {"permissive"}
    missing = sorted(named - set(BY_NAME))
    assert not missing, f"mock-llm emulates providers with no canonical emulator: {missing}"


def test_response_format_rules_match_the_canonical_emulators(mock_server):
    """The #1560 rule specifically, plus every other provider's."""
    mismatches: list[str] = []
    for name, rules in sorted(mock_server.PROVIDERS.items()):
        if name == "permissive":
            continue
        emulator = BY_NAME[name]
        canonical = set(getattr(emulator, "allowed_response_formats", frozenset()))
        mock_allowed = set(rules["response_formats"] or set())
        if canonical != mock_allowed:
            mismatches.append(f"{name}: emulator={sorted(canonical)} mock-llm={sorted(mock_allowed)}")
    assert not mismatches, "mock-llm response_format rules have drifted:\n  " + "\n  ".join(mismatches)


def test_auth_requirements_match_the_canonical_emulators(mock_server):
    mismatches: list[str] = []
    for name, rules in sorted(mock_server.PROVIDERS.items()):
        if name == "permissive":
            continue
        canonical = bool(getattr(BY_NAME[name], "requires_auth", False))
        if canonical != bool(rules["requires_auth"]):
            mismatches.append(f"{name}: emulator={canonical} mock-llm={rules['requires_auth']}")
    assert not mismatches, "mock-llm auth rules have drifted:\n  " + "\n  ".join(mismatches)


def test_lmstudio_flat_error_envelope_is_modelled_in_both(mock_server):
    """LM Studio reports errors as {"error": "..."}; both copies must agree."""
    assert mock_server.PROVIDERS["lmstudio"]["flat_error"] is True
    assert BY_NAME["lmstudio"].error_body("x") == {"error": "x"}


def test_permissive_is_the_default_so_existing_specs_keep_their_meaning(mock_server):
    state = mock_server.MockLLMState()
    assert state.provider == "permissive"
    assert state.scenario == "ok"


def test_script_scenario_renders_ops_as_fenced_tool_blocks(mock_server):
    """The fence format is the contract src/ai/chat_ops.py parses."""
    content = mock_server._scripted_content(
        {"prose": "On it.", "ops": [{"op": "navigate_to_page", "args": {"page_id": "new"}}]}
    )
    assert "On it." in content
    assert "```fiestaboard" in content
    assert '"op": "navigate_to_page"' in content


def test_script_with_no_ops_still_returns_text(mock_server):
    assert mock_server._scripted_content(None).strip()


def test_provider_rejection_reproduces_1560(mock_server):
    """Meta-test: the mock must be able to say no, or it emulates nothing."""
    rejection = mock_server._provider_rejection(
        "lmstudio",
        {"model": "m", "messages": [], "response_format": {"type": "json_object"}},
        {},
    )
    assert rejection is not None
    status, body = rejection
    assert status == 400
    assert "json_schema" in body["error"]


def test_permissive_provider_accepts_what_lmstudio_rejects(mock_server):
    assert (
        mock_server._provider_rejection(
            "permissive",
            {"model": "m", "messages": [], "response_format": {"type": "json_object"}},
            {},
        )
        is None
    )
