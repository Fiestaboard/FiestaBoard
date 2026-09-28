"""Filters that were documented but absent, and validation that stayed silent.

Three silent failures an author could not diagnose from the board:

* ``|upper`` / ``|lower`` were advertised in the engine's own module docstring
  but never implemented — an unknown filter is a no-op, so the value rendered
  unchanged and nothing said why.
* Filter chains (``|upper|pad:3``) were documented as chainable but the whole
  remaining chain was parsed as one filter name, so every chain was a no-op.
* ``validate_template`` checked only the plugin id, so a misspelled field
  (``{{weather.temperatur}}``) validated clean and rendered ``???``.
"""

import json
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

from src.templates.engine import TemplateEngine

REPO_ROOT = Path(__file__).resolve().parents[1]

CTX = {"weather": {"condition": "sunny", "temperature": 72}}

KNOWN = {"weather": ["condition", "temperature", "forecast", "forecast.*.high"]}


@contextmanager
def catalog(variables: dict[str, list[str]], extra_sources: set[str] | None = None):
    """Pin the variable catalog so validation has a known world.

    ``extra_sources`` mirrors what the registry really reports: an instanced
    plugin is a source under its instance key (``weather:sf``) while its
    variables stay catalogued under the base id.
    """
    with (
        patch.object(TemplateEngine, "get_available_variables", return_value=variables),
        patch.object(
            TemplateEngine,
            "get_all_known_sources",
            return_value=set(variables) | (extra_sources or set()),
        ),
    ):
        yield


@pytest.fixture
def engine() -> TemplateEngine:
    return TemplateEngine()


class TestCaseFilters:
    def test_upper_filter_uppercases(self):
        engine = TemplateEngine()
        assert engine.render("{{weather.condition|upper}}", CTX) == "SUNNY"

    def test_lower_filter_lowercases(self):
        engine = TemplateEngine()
        assert engine.render("{{weather.condition|lower}}", {"weather": {"condition": "SUNNY"}}) == "sunny"

    def test_filters_chain_left_to_right(self):
        engine = TemplateEngine()
        assert engine.render("{{weather.condition|upper|truncate:3}}", CTX) == "SUN"

    def test_chain_of_argument_filters(self):
        engine = TemplateEngine()
        assert engine.render("{{weather.temperature|zeropad:4|truncate:2}}", CTX) == "00"

    def test_unknown_filter_leaves_the_value_alone(self):
        # Still a no-op at render time (the board must show something), but
        # validation now reports it — see TestFilterValidation.
        engine = TemplateEngine()
        assert engine.render("{{weather.condition|shout}}", CTX) == "sunny"


class TestFilterValidation:
    def test_unknown_filter_is_reported(self):
        engine = TemplateEngine()
        messages = [e.message for e in engine.validate_template("{{weather.condition|shout}}")]
        assert any("shout" in m for m in messages)

    def test_known_filters_are_not_reported(self):
        engine = TemplateEngine()
        for spelling in ("upper", "lower", "wrap", "pad:3", "truncate:3", "zeropad:2"):
            messages = [e.message for e in engine.validate_template(f"{{{{weather.condition|{spelling}}}}}")]
            assert not any("filter" in m.lower() for m in messages), spelling


class TestFieldValidation:
    def test_misspelled_field_is_reported(self, engine):
        with catalog(KNOWN):
            messages = [e.message for e in engine.validate_template("{{weather.temperatur}}")]
        assert any("temperatur" in m for m in messages)

    def test_known_field_is_accepted(self, engine):
        with catalog(KNOWN):
            assert engine.validate_template("{{weather.temperature}}") == []

    def test_array_index_path_is_accepted(self, engine):
        with catalog(KNOWN):
            assert engine.validate_template("{{weather.forecast.0.high}}") == []

    def test_color_suffix_is_accepted(self, engine):
        with catalog(KNOWN):
            assert engine.validate_template("{{weather.temperature_color}}") == []

    def test_plugin_instance_key_uses_the_base_catalog(self, engine):
        with catalog(KNOWN, extra_sources={"weather:sf"}):
            assert engine.validate_template("{{weather:sf.temperature}}") == []

    def test_misspelled_field_on_an_instance_is_still_reported(self, engine):
        with catalog(KNOWN, extra_sources={"weather:sf"}):
            messages = [e.message for e in engine.validate_template("{{weather:sf.temperatur}}")]
        assert any("temperatur" in m for m in messages)

    def test_home_assistant_entity_paths_are_never_flagged(self, engine):
        with catalog({"home_assistant": ["state"]}):
            assert engine.validate_template("{{home_assistant.sensor_porch_temp.state}}") == []

    def test_plugin_with_no_declared_variables_is_not_flagged(self, engine):
        # auto_discover plugins can have an empty catalog when the discovery
        # fetch failed; guessing would flag every field they expose.
        with catalog({"mystery": []}):
            assert engine.validate_template("{{mystery.whatever}}") == []


class TestListRendering:
    def test_a_list_valued_variable_renders_the_missing_marker(self):
        # Previously rendered the Python repr: "[{'high': 70}]".
        engine = TemplateEngine()
        rendered = engine.render("{{weather.forecast}}", {"weather": {"forecast": [{"high": 70}]}})
        assert rendered == "???"

    def test_a_dict_valued_variable_renders_the_missing_marker(self):
        engine = TemplateEngine()
        rendered = engine.render("{{weather.detail}}", {"weather": {"detail": {"high": 70}}})
        assert rendered == "???"


class TestRowEmittingFormulaLength:
    def test_foreach_line_is_not_flagged_as_too_long(self):
        engine = TemplateEngine()
        line = 'NEXT: {{= FOREACH(transit.stops, item.eta & " " & item.name) }}'
        messages = [e.message for e in engine.validate_template(line, cols=22)]
        assert not any("too long" in m for m in messages)


class TestFiltersOnAWrappedVariable:
    """The wrap path is the engine's *second* filter call site.

    ``_render_variables`` hands the whole chain after the first ``|`` to
    ``_apply_filter``; the ``|wrap`` path in ``_render_with_wrap`` instead
    strips ``wrap`` out of the chain itself and calls ``_apply_filter`` once
    per remaining filter. Nothing covered that second site, so a chain
    combined with ``|wrap`` could have gone back to being a no-op unnoticed.
    """

    CTX = {
        "plugin": {
            "long_text": "the quick brown fox jumps over the lazy dog again",
            "value": "hello world from fiesta",
        }
    }

    def _render(self, line: str) -> list[str]:
        engine = TemplateEngine()
        rendered = engine.render_lines(
            [line, "", "", "", "", ""],
            context=self.CTX,
            device_type="flagship",
        )
        return [row.rstrip() for row in rendered.split("\n")]

    def test_a_filter_before_wrap_is_applied_and_the_value_still_wraps(self):
        assert self._render("{{plugin.long_text|upper|wrap}}")[:4] == [
            "THE QUICK BROWN FOX",
            "JUMPS OVER THE LAZY",
            "DOG AGAIN",
            "",
        ]

    def test_a_filter_after_wrap_is_applied_too(self):
        # Chain order does not matter: ``wrap`` is removed from the chain and
        # every other filter is applied to the value before it is wrapped.
        assert self._render("{{plugin.value|wrap|truncate:8}}")[:2] == ["hello wo", ""]

    def test_a_two_filter_chain_around_wrap_applies_both_in_order(self):
        # ``upper`` then ``truncate:25`` — truncating first would leave
        # "the quick brown fox jumps" uppercased to a different cut.
        assert self._render("{{plugin.long_text|upper|truncate:25|wrap}}")[:3] == [
            "THE QUICK BROWN FOX",
            "JUMPS",
            "",
        ]

    def test_a_filtered_wrap_still_accounts_for_the_prefix_width(self):
        assert self._render("NEWS: {{plugin.long_text|upper|wrap}}")[:3] == [
            "NEWS: THE QUICK BROWN",
            "FOX JUMPS OVER THE",
            "LAZY DOG AGAIN",
        ]


#: Patterns whose only defence is the guard in ``_compile_user_pattern``:
#: every one of them backtracks exponentially if it is ever compiled and run
#: against ``ADVERSARIAL_SUBJECT``.
ADVERSARIAL_EXPRESSIONS = [
    'REGEXMATCH(plugin.text, "(a+)+$")',
    'REGEXMATCH(plugin.text, "(a|a)*$")',
    'REGEXMATCH(plugin.text, "(a|aa)+$")',
    'REGEXMATCH(plugin.text, "(?:a|a)*$")',
    'REGEXMATCH(plugin.text, "^(a?){24}a{24}$")',
    'REGEXEXTRACT(plugin.text, "^(a|ab)*$")',
    'REGEXREPLACE(plugin.text, "(a*)*$", "x")',
    # Nesting puts the quantified group one level down, where a rule that
    # inspected a group's contents could not see it.
    'REGEXMATCH(plugin.text, "((a)|(a))*$")',
    'REGEXMATCH(plugin.text, "((a|a))*$")',
    # No group at all: the cost is in the run of adjacent quantifiers.
    'REGEXMATCH(plugin.text, "a*a*a*a*a*a*a*a*a*b")',
    'REGEXMATCH(plugin.text, "^[a-z]*[a-z]*[a-z]*[a-z]*[a-z]*$")',
]

#: 64 a's and a final character that cannot match — the shape that forces a
#: backtracking engine to try every partition of the run.
ADVERSARIAL_SUBJECT = "a" * 64 + "!"

#: Evaluated in a child process so a runaway regex can be killed. A signal
#: alarm would not do: ``re`` matches in C without releasing the GIL, so
#: neither a handler nor a watchdog thread runs until the match returns.
_TIMING_PROBE = """
import json
import sys
import time

from src.templates.expressions import evaluate

expressions = json.loads(sys.argv[1])
context = {"plugin": {"text": sys.argv[2]}}
start = time.perf_counter()
results = [evaluate(expression, context) for expression in expressions]
print(json.dumps({"seconds": time.perf_counter() - start, "results": results}))
"""

#: Hard kill for the child. Reaching it *is* the failure: it means one of the
#: patterns above was compiled and run instead of refused. Its only cost is how
#: long a genuine failure takes to report.
REGEX_HARD_TIMEOUT_SECONDS = 30.0


class TestKnownExponentialPatternsAreRefusedNotRun:
    """Every pattern below is refused before the regex engine sees it.

    Read the scope carefully: this is NOT a proof that a user regex cannot
    stall a render. ``re`` has no timeout, the guard in
    ``_compile_user_pattern`` is a shape blacklist, and a shape nobody has
    thought of would sail past it. What this pins is that each family we know
    backtracks exponentially — including the nested and sequential-quantifier
    ones that a narrower rule let through — is still refused at compile time,
    so re-narrowing the guard fails here instead of stalling a board.
    """

    def test_adversarial_patterns_are_refused_before_they_can_run(self):
        try:
            probe = subprocess.run(
                [sys.executable, "-c", _TIMING_PROBE, json.dumps(ADVERSARIAL_EXPRESSIONS), ADVERSARIAL_SUBJECT],
                cwd=REPO_ROOT,
                env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
                capture_output=True,
                text=True,
                check=False,
                timeout=REGEX_HARD_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            pytest.fail(
                f"Evaluating {len(ADVERSARIAL_EXPRESSIONS)} adversarial regex expressions did not "
                f"finish in {REGEX_HARD_TIMEOUT_SECONDS:.0f}s and the child had to be killed. The "
                "guard in src/templates/expressions.py is no longer refusing a catastrophically "
                "backtracking pattern, and a template using one would stall a board render:"
                "\n" + "\n".join(ADVERSARIAL_EXPRESSIONS)
            )

        assert probe.returncode == 0, f"timing probe crashed:\n{probe.stderr}"
        report = json.loads(probe.stdout.strip().splitlines()[-1])

        # Not vacuous: every expression really reached the regex functions.
        assert "#NAME?" not in report["results"], f"a REGEX* function was renamed: {report['results']}"
        assert "#REF" not in report["results"], f"the subject variable did not resolve: {report['results']}"

        # The discriminating assertion. Not finishing quickly is caught by the
        # child timeout above; what this adds is that finishing quickly happened
        # because each pattern was REFUSED, not because it happened to match
        # early. A wall-clock budget here would be dead code — a refusal costs
        # microseconds, so any threshold loose enough not to flake is unreachable.
        refused = [result for result in report["results"] if result == "#VALUE"]
        assert len(refused) == len(ADVERSARIAL_EXPRESSIONS), (
            "every known-exponential pattern must be refused with #VALUE at compile time; got "
            f"{report['results']}. A pattern that returned a match result reached the regex "
            "engine, which means the guard in src/templates/expressions.py stopped covering "
            "its shape — the next subject string could stall a board render."
        )
