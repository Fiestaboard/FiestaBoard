#!/usr/bin/env python3
"""Sweep every installed plugin for breakage that no amount of config can fix.

Per-plugin CI runs each plugin in a tree it never actually ships in: the repo
is checked out into the *bundled* ``plugins/<id>/`` layout, and some workflows
even synthesise data files before running the suite.  A plugin can therefore be
green in its own repo and completely dead once installed to
``data/external_plugins/<id>/``.  That is how the Star Trek Quotes plugin
shipped for months serving ``???`` for every variable
(Fiestaboard/fiestaboard-plugin--star-trek-quotes#10).

This sweep loads plugins the way the running app does and asserts the things
that must hold for *any* install, regardless of user configuration:

1. ``load``          - the plugin imports and instantiates
2. ``data_files``    - every ``__file__``-relative data file it reads exists
3. ``self_contained``- no ``__file__`` path escapes the plugin directory
4. ``dependencies``  - everything in requirements.txt is importable
5. ``fetch_contract``- fetch_data() does not raise, and an unavailable result
                       carries a non-empty error the user can act on

Checks 1-4 are hermetic.  Check 5 calls fetch_data(), which may touch the
network; a plugin that is merely unconfigured or whose upstream API is down is
reported but never fails the sweep.  Only a raised exception or a silent
failure counts against it.

Usage:
    python scripts/plugin_health_sweep.py [OPTIONS]

Options:
    --external-dir=PATH  Directory of installed plugins
                         (default: data/external_plugins)
    --plugin=ID          Sweep a single plugin
    --no-fetch           Skip check 5; run only the hermetic checks
    --json=PATH          Write the full report as JSON
    --markdown=PATH      Write a report suitable for a GitHub issue body
    --verbose            Show passing checks too

Sets ``has_findings=true|false`` on $GITHUB_OUTPUT when running in Actions.

Exit codes:
    0 - No breakage found
    1 - At least one plugin is broken
    2 - Configuration/setup error
"""

import argparse
import json
import os
import sys
import traceback
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
PLUGINS_DIR = PROJECT_ROOT / "plugins"
DEFAULT_EXTERNAL_DIR = PROJECT_ROOT / "data" / "external_plugins"

sys.path.insert(0, str(PROJECT_ROOT))


class Finding:
    """One failed check against one plugin."""

    def __init__(self, plugin_id: str, check: str, detail: str, fatal: bool = True):
        self.plugin_id = plugin_id
        self.check = check
        self.detail = detail
        self.fatal = fatal

    def to_dict(self) -> dict:
        return {
            "plugin": self.plugin_id,
            "check": self.check,
            "detail": self.detail,
            "fatal": self.fatal,
        }

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Finding {self.plugin_id}/{self.check}>"


def schema_defaults(plugin) -> dict:
    """Config a plugin gets with nothing configured but 'enabled'."""
    try:
        schema = plugin.get_settings_schema() or {}
    except Exception:
        schema = {}
    config = {
        name: spec["default"]
        for name, spec in (schema.get("properties") or {}).items()
        if isinstance(spec, dict) and "default" in spec
    }
    config["enabled"] = True
    return config


def check_fetch_contract(plugin_id: str, plugin) -> tuple[list[Finding], str]:
    """fetch_data() must not raise, and must explain itself when unavailable."""
    try:
        plugin.config = schema_defaults(plugin)
    except Exception as exc:
        return (
            [
                Finding(
                    plugin_id,
                    "fetch_contract",
                    f"applying default config raised {type(exc).__name__}: {exc}",
                )
            ],
            "CONFIG_RAISED",
        )

    try:
        result = plugin.fetch_data()
    except Exception as exc:
        return (
            [
                Finding(
                    plugin_id,
                    "fetch_contract",
                    f"fetch_data() raised {type(exc).__name__}: {exc}\n{traceback.format_exc(limit=3)}",
                )
            ],
            "FETCH_RAISED",
        )

    if result is None:
        return (
            [
                Finding(
                    plugin_id,
                    "fetch_contract",
                    "fetch_data() returned None instead of a PluginResult",
                )
            ],
            "RETURNED_NONE",
        )

    if result.available:
        return [], "OK"

    if not (result.error or "").strip():
        return (
            [
                Finding(
                    plugin_id,
                    "fetch_contract",
                    "unavailable with no error message; the UI can only render "
                    "'???' with no way for the user to learn why",
                )
            ],
            "SILENT_UNAVAILABLE",
        )

    # Unavailable-with-a-reason is the normal state for an unconfigured
    # plugin. Reported, never fatal.
    return [], "UNAVAILABLE"


def sweep(external_dir: Path, only: str | None, do_fetch: bool) -> tuple[list, list]:
    """Run every check against every discoverable plugin."""
    from src.plugins.install_check import validate_install
    from src.plugins.loader import PluginLoader
    from src.plugins.manifest import load_manifest

    loader = PluginLoader(plugins_dir=PLUGINS_DIR, external_dirs=[external_dir])
    plugin_ids = loader.discover_plugins()
    if only:
        plugin_ids = [p for p in plugin_ids if p == only]
        if not plugin_ids:
            raise SystemExit(f"error: plugin {only!r} not found")

    findings: list[Finding] = []
    report = []

    for plugin_id in sorted(plugin_ids):
        plugin_dir = loader._resolve_plugin_dir(plugin_id)
        row = {"plugin": plugin_id, "dir": str(plugin_dir), "status": "?"}

        if plugin_dir is not None:
            manifest_for_checks, _ = load_manifest(plugin_dir / "manifest.json")
            install_result = validate_install(plugin_id, plugin_dir, manifest_for_checks)
            for message in install_result.errors:
                findings.append(Finding(plugin_id, "install", message))
            for message in install_result.warnings:
                findings.append(Finding(plugin_id, "undeclared", message, fatal=False))

        try:
            plugin = loader.load_plugin(plugin_id)
        except Exception as exc:
            findings.append(
                Finding(
                    plugin_id,
                    "load",
                    f"loading raised {type(exc).__name__}: {exc}",
                )
            )
            row["status"] = "LOAD_RAISED"
            report.append(row)
            continue

        if plugin is None:
            errors = "; ".join(str(e) for e in loader.load_errors.get(plugin_id, []))
            findings.append(Finding(plugin_id, "load", errors or "plugin failed to load"))
            row["status"] = "LOAD_FAILED"
            report.append(row)
            continue

        manifest = loader.get_manifest(plugin_id)
        if (getattr(manifest, "plugin_type", None) or "data") == "transition":
            row["status"] = "TRANSITION"
            report.append(row)
            continue

        if not do_fetch:
            row["status"] = "LOADED"
            report.append(row)
            continue

        fetch_findings, status = check_fetch_contract(plugin_id, plugin)
        findings.extend(fetch_findings)
        row["status"] = status
        report.append(row)

    return findings, report


CHECK_EXPLANATIONS = {
    "load": "The plugin does not load at all, so it is invisible to users.",
    "install": (
        "The plugin cannot work as installed -- a declared data file is "
        "missing, or it needs a package FiestaBoard does not ship."
    ),
    "undeclared": (
        "Advisory. The plugin reads a data file it does not declare in "
        "`manifest.json`, so a missing copy would not be caught at install "
        "time. Declare it under `data_files`."
    ),
    "data_files": (
        "The plugin reads a data file that is not shipped with it. Every variable it exposes will render as `???`."
    ),
    "self_contained": (
        "The plugin reaches outside its own directory for data. Such a path "
        "only resolves in the bundled `plugins/<id>/` layout and breaks once "
        "the plugin is installed to `data/external_plugins/<id>/`."
    ),
    "dependencies": ("The plugin declares a dependency the platform never installs (see #1671)."),
    "fetch_contract": ("`fetch_data()` raised, returned nothing, or failed without telling the user why."),
}


def render_markdown(findings: list, report: list, external_dir: Path) -> str:
    """Build an issue body describing the sweep results."""
    lines = [
        "## Plugin health sweep",
        "",
        f"Swept **{len(report)}** plugins installed to `{external_dir}`.",
        "",
    ]
    if not findings:
        lines += ["No breakage found. ✅", ""]
        return "\n".join(lines)

    by_plugin: dict[str, list] = {}
    for finding in findings:
        by_plugin.setdefault(finding.plugin_id, []).append(finding)

    lines += [
        f"Found **{len(findings)}** issue(s) across **{len(by_plugin)}** "
        f"plugin(s). These are failures no user configuration can fix.",
        "",
    ]
    for plugin_id in sorted(by_plugin):
        lines.append(f"### `{plugin_id}`")
        lines.append("")
        for finding in by_plugin[plugin_id]:
            lines.append(f"- **{finding.check}** — {finding.detail}")
        lines.append("")

    checks_seen = sorted({f.check for f in findings})
    lines += ["<details><summary>What these checks mean</summary>", ""]
    for check in checks_seen:
        lines.append(f"- **{check}**: {CHECK_EXPLANATIONS.get(check, '')}")
    lines += ["", "</details>", ""]
    return "\n".join(lines)


def set_output(name: str, value: str) -> None:
    """Publish a step output when running inside GitHub Actions."""
    output_file = os.environ.get("GITHUB_OUTPUT")
    if not output_file:
        return
    with Path(output_file).open("a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--external-dir", default=str(DEFAULT_EXTERNAL_DIR))
    parser.add_argument("--plugin", default=None)
    parser.add_argument("--no-fetch", action="store_true")
    parser.add_argument("--json", dest="json_path", default=None)
    parser.add_argument("--markdown", dest="markdown_path", default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    external_dir = Path(args.external_dir)
    if not external_dir.exists():
        print(f"error: external plugin dir not found: {external_dir}", file=sys.stderr)
        return 2

    findings, report = sweep(external_dir, args.plugin, not args.no_fetch)

    print(f"Swept {len(report)} plugins from {external_dir}\n")
    if args.verbose:
        print(f"{'plugin':28} status")
        print("-" * 50)
        for row in report:
            print(f"{row['plugin']:28} {row['status']}")
        print()

    if args.json_path:
        Path(args.json_path).write_text(
            json.dumps(
                {
                    "findings": [f.to_dict() for f in findings],
                    "plugins": report,
                },
                indent=2,
            )
        )

    if args.markdown_path:
        Path(args.markdown_path).write_text(render_markdown(findings, report, external_dir))

    fatal = [f for f in findings if f.fatal]
    set_output("has_findings", "true" if fatal else "false")

    if not findings:
        print("No breakage found. Every plugin loads, ships its data files,")
        print("has its dependencies available, and honours the fetch contract.")
        return 0

    by_plugin: dict[str, list[Finding]] = {}
    for finding in findings:
        by_plugin.setdefault(finding.plugin_id, []).append(finding)

    print(f"{len(fatal)} blocking, {len(findings) - len(fatal)} advisory across {len(by_plugin)} plugin(s)\n")
    for plugin_id in sorted(by_plugin):
        print(f"  {plugin_id}")
        for finding in by_plugin[plugin_id]:
            mark = "" if finding.fatal else " (advisory)"
            print(f"    [{finding.check}]{mark} {finding.detail}")
        print()

    # Advisory findings -- an undeclared data file that is nonetheless
    # present -- must not fail a scheduled job, or every plugin published
    # before data_files existed turns the run red forever.
    return 1 if fatal else 0


if __name__ == "__main__":
    sys.exit(main())
