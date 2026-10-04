"""The ``output`` plugin kind's manifest: the block, FiestaUI's schemas, character sets.

Pinned here:

- the vendored FiestaUI schemas resolve each other by ``$id`` with no
  network, and every built-in model and set is valid against them (the
  files' bytes are pinned by ``tests/test_fiestaui_vendored.py``);
- ``plugin_type: "output"`` validates, requires an ``output`` block, and
  refuses what an output has no use for (teaser, previews, variables, oauth);
- the block: ``output_api`` outside this core's range refuses the load (fail
  closed); device models are FiestaUI DeviceModels or known built-in ids,
  never an unknown id; ``$ref`` files must live in the plugin and be declared
  in ``data_files``;
- character sets materialise with D17's rules (per-field override, arrays
  replace, version not inherited, unknown parent / self-extends / incomplete
  set refused), through core's one materialiser,
  :func:`src.led.charsets.materialize_character_set` (its FiestaUI goldens
  are ``tests/test_led_parity.py``);
- the registry naming convention accepts ``fiestaboard-output--``.
"""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

from src import fiestaui as fiestaui_data
from src.led.charsets import CharacterSetError, materialize_character_set
from src.outputs import fiestaui
from src.outputs.output_manifest import SUPPORTED_OUTPUT_API, parse_output_block
from src.plugins.manifest import load_manifest, validate_manifest, validate_preview_completeness
from src.plugins.sources import plugin_id_from_repo_name, validate_registry_repo_name

FIXTURE = Path(__file__).parent / "fixtures" / "plugins" / "recording_output"


def manifest_data() -> dict:
    return json.loads((FIXTURE / "manifest.json").read_text("utf-8"))


def inline_block(**overrides) -> dict:
    block = {"output_api": 1, "device_models": ["divoom_pixoo64"], **overrides}
    return {k: v for k, v in block.items() if v is not None}


def output_manifest(**block_overrides) -> dict:
    return {
        "id": "acme_sign",
        "name": "Acme Sign",
        "version": "1.0.0",
        "plugin_type": "output",
        "output": inline_block(**block_overrides),
    }


@pytest.fixture
def plugin_copy(tmp_path) -> Path:
    """An editable copy of the recording output plugin."""
    target = tmp_path / "recording_output"
    shutil.copytree(FIXTURE, target)
    return target


def rewrite(plugin_dir: Path, mutate) -> None:
    path = plugin_dir / "manifest.json"
    data = json.loads(path.read_text("utf-8"))
    mutate(data)
    path.write_text(json.dumps(data), "utf-8")


# --- vendored FiestaUI files -----------------------------------------------------------


class TestVendoredSchemas:
    def test_a_device_model_resolves_its_charset_ref_locally(self):
        # The device-model schema $refs the character-set schema by $id; a
        # network fetch would be refused by the suite's socket fence.
        model = dict(fiestaui_data.builtin_device_models()["divoom_pixoo64"])
        model["charset"] = {"id": "x", "extends": "led_3x5", "chars": ["too long"]}
        errors = fiestaui.validate_device_model(model)
        assert any("charset" in e for e in errors)

    @pytest.mark.parametrize("model_id", ["vestaboard_flagship", "divoom_pixoo64"])
    def test_a_font_is_checked_on_every_model_not_only_an_led_one(self, model_id):
        # FiestaUI #326 review fix: a split-flap model has no use for a font,
        # but one it names must still be a face that exists.
        model = dict(fiestaui_data.builtin_device_models()[model_id])
        assert fiestaui.validate_device_model({**model, "font": "3x5"}) == []
        errors = fiestaui.validate_device_model({**model, "font": "9x9"})
        assert errors and all(e.startswith("device_model.font") for e in errors)

    def test_every_vendored_built_in_model_is_valid(self):
        for model_id, model in fiestaui_data.builtin_device_models().items():
            assert fiestaui.validate_device_model(model, model_id) == []

    def test_every_vendored_built_in_character_set_is_valid(self):
        for set_id, charset in fiestaui_data.builtin_character_sets().items():
            assert fiestaui.validate_character_set(charset, set_id) == []


# --- the kind -------------------------------------------------------------------------


class TestOutputKind:
    def test_an_output_manifest_validates(self):
        assert validate_manifest(output_manifest()) == (True, [])

    def test_an_output_plugin_needs_an_output_block(self):
        data = output_manifest()
        del data["output"]
        ok, errors = validate_manifest(data)
        assert not ok and any("'output' block" in e for e in errors)

    def test_only_output_plugins_carry_an_output_block(self):
        data = output_manifest()
        data["plugin_type"] = "data"
        ok, errors = validate_manifest(data)
        assert not ok and any("only supported for output plugins" in e for e in errors)

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("teaser", "HELLO"),
            ("previews", [{"rows": ["HI"]}]),
            ("variables", {"simple": ["x"]}),
            ("oauth", {"provider": "x"}),
            ("transition_settings", {"max_frames": 3}),
        ],
    )
    def test_an_output_plugin_refuses_what_it_has_no_use_for(self, field, value):
        data = {**output_manifest(), field: value}
        ok, errors = validate_manifest(data)
        assert not ok and any(field in e for e in errors)

    def test_output_plugins_need_no_board_previews(self):
        assert validate_preview_completeness(output_manifest()) == []

    def test_an_unknown_plugin_type_is_refused(self):
        ok, errors = validate_manifest({**output_manifest(), "plugin_type": "sensor"})
        assert not ok and any("plugin_type" in e for e in errors)


# --- the output block -------------------------------------------------------------------


class TestOutputBlock:
    def test_the_fixture_loads_with_its_refs_resolved(self):
        manifest, errors = load_manifest(FIXTURE / "manifest.json")
        assert errors == []
        assert manifest.output.device_model_ids == ("recording_sign", "divoom_pixoo64")
        assert manifest.output.character_set["id"] == "recording_sign_v1"

    def test_capabilities_come_from_the_first_model_and_the_transport_fields(self):
        manifest, _ = load_manifest(FIXTURE / "manifest.json")
        caps = manifest.output.capabilities
        assert (caps.technology, caps.animation, caps.delivery) == ("split_flap", "stream", "push")
        assert caps.native_transitions == frozenset({"column"})
        assert caps.read_back.supported is True
        # The plugin's own character set wins over the model's charset.
        assert caps.charset == "recording_sign_v1"

    def test_a_built_in_model_brings_its_facts(self):
        output, errors = parse_output_block(inline_block(), base_dir=None, data_files=[])
        assert errors == []
        caps = output.capabilities
        # The Pixoo 64 streams single frames since its hardware test
        # (FiestaUI #335): no sequence, so no frame budget.
        assert (caps.technology, caps.animation, caps.max_frames, caps.charset) == (
            "led_matrix",
            "stream",
            None,
            "led_3x5",
        )

    @pytest.mark.parametrize("api", [0, SUPPORTED_OUTPUT_API[1] + 1])
    def test_an_unsupported_output_api_refuses_the_load(self, plugin_copy, api):
        rewrite(plugin_copy, lambda d: d["output"].__setitem__("output_api", api))
        manifest, errors = load_manifest(plugin_copy / "manifest.json")
        assert manifest is None
        assert any("output_api" in e and "not supported" in e for e in errors)

    def test_a_missing_output_api_is_refused(self):
        _, errors = parse_output_block(inline_block(output_api=None), base_dir=None, data_files=[])
        assert any("output_api is required" in e for e in errors)

    def test_an_unknown_built_in_model_id_is_never_coerced(self):
        _, errors = parse_output_block(
            inline_block(device_models=["vestaboard_megaboard"]), base_dir=None, data_files=[]
        )
        assert errors == ["output.device_models[0]: unknown built-in device model id 'vestaboard_megaboard'"]

    def test_a_model_with_the_retired_top_level_pixel_shape_is_refused(self):
        model = copy.deepcopy(dict(fiestaui_data.builtin_device_models()["divoom_pixoo64"]))
        model["pixelShape"] = "square"
        _, errors = parse_output_block(inline_block(device_models=[model]), base_dir=None, data_files=[])
        assert any("pixelShape" in e for e in errors)

    def test_no_device_models_is_refused(self):
        _, errors = parse_output_block(inline_block(device_models=[]), base_dir=None, data_files=[])
        assert any("non-empty" in e for e in errors)

    def test_a_ref_must_be_declared_in_data_files(self, plugin_copy):
        rewrite(plugin_copy, lambda d: d.__setitem__("data_files", ["output/character-set.json"]))
        manifest, errors = load_manifest(plugin_copy / "manifest.json")
        assert manifest is None
        assert any("must also be listed in data_files" in e for e in errors)

    def test_a_ref_may_not_leave_the_plugin(self, plugin_copy):
        def mutate(d):
            d["output"]["device_models"] = {"$ref": "../elsewhere.json"}
            d["data_files"].append("../elsewhere.json")

        rewrite(plugin_copy, mutate)
        manifest, errors = load_manifest(plugin_copy / "manifest.json")
        assert manifest is None
        assert any("inside the plugin" in e for e in errors)

    def test_a_missing_ref_file_refuses_the_load(self, plugin_copy):
        (plugin_copy / "output" / "device-models.json").unlink()
        manifest, errors = load_manifest(plugin_copy / "manifest.json")
        assert manifest is None
        assert any("file not found" in e for e in errors)

    def test_an_invalid_model_in_a_ref_file_refuses_the_load(self, plugin_copy):
        path = plugin_copy / "output" / "device-models.json"
        models = json.loads(path.read_text("utf-8"))
        del models[0]["family"]
        path.write_text(json.dumps(models), "utf-8")
        manifest, errors = load_manifest(plugin_copy / "manifest.json")
        assert manifest is None
        assert any("family" in e for e in errors)

    def test_unknown_block_fields_are_refused(self):
        _, errors = parse_output_block(inline_block(colour="red"), base_dir=None, data_files=[])
        assert errors == ["output.colour: not an output block field"]

    @pytest.mark.parametrize(
        ("field", "value", "fragment"),
        [
            ("delivery", "carrier-pigeon", "output.delivery"),
            ("min_interval_ms", -1, "output.min_interval_ms"),
            ("read_back", {"supported": "yes"}, "output.read_back.supported"),
            ("native_transitions", ["swirl"], "unknown strategies"),
            ("settings_schema", [], "output.settings_schema"),
        ],
    )
    def test_transport_fields_are_checked(self, field, value, fragment):
        _, errors = parse_output_block(inline_block(**{field: value}), base_dir=None, data_files=[])
        assert any(fragment in e for e in errors)


# --- character sets (plan D17) ---------------------------------------------------------


class TestCharacterSets:
    def test_a_field_given_replaces_the_parents_and_arrays_are_not_merged(self):
        got = materialize_character_set({"id": "mine", "extends": "led_3x5", "chars": ["A"], "icons": []})
        assert got["chars"] == ["A"] and got["icons"] == []
        parent = fiestaui_data.builtin_character_sets()["led_3x5"]
        assert got["tiles"] == parent["tiles"] and got["font"] == parent["font"]

    def test_version_is_never_inherited(self):
        assert fiestaui_data.builtin_character_sets()["vestaboard_v2"]["version"] == 2
        assert materialize_character_set({"id": "mine", "extends": "vestaboard_v2"})["version"] == 1

    def test_a_set_extends_an_already_materialised_one(self):
        first = materialize_character_set({"id": "first", "extends": "led_3x5", "chars": ["Z"]})
        second = materialize_character_set({"id": "second", "extends": "first"}, [first])
        assert second["chars"] == ["Z"] and second["extends"] == "first"

    def test_an_unknown_parent_is_refused(self):
        with pytest.raises(CharacterSetError, match="extends unknown set"):
            materialize_character_set({"id": "mine", "extends": "nope"})

    def test_a_set_extending_itself_is_refused(self):
        with pytest.raises(CharacterSetError, match="extends itself"):
            materialize_character_set({"id": "led_3x5", "extends": "led_3x5"})

    def test_a_set_extending_nothing_must_be_complete(self):
        with pytest.raises(CharacterSetError, match="invalid"):
            materialize_character_set({"id": "mine", "chars": ["A"]})

    def test_the_manifest_block_refuses_an_unmaterialisable_set(self):
        _, errors = parse_output_block(
            inline_block(character_set={"id": "mine", "extends": "nope"}), base_dir=None, data_files=[]
        )
        assert any("extends unknown set" in e for e in errors)


# --- registry naming -------------------------------------------------------------------


class TestRegistryNaming:
    def test_an_output_repo_name_is_accepted(self):
        assert validate_registry_repo_name("https://github.com/Fiestaboard/fiestaboard-output--divoom-pixoo") == (
            True,
            "",
        )

    def test_an_output_repo_name_derives_its_plugin_id(self):
        assert plugin_id_from_repo_name("fiestaboard-output--divoom-pixoo") == "divoom_pixoo"

    def test_the_authoring_script_shares_the_runtime_convention(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "validate_plugins", Path(__file__).parent.parent / "scripts" / "validate_plugins.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert module._plugin_id_from_repo_name("fiestaboard-output--acme-sign") == "acme_sign"
        assert module.REGISTRY_NAME_RE.match("fiestaboard-output--acme-sign")
