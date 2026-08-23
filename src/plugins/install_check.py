"""Install-time validation: is this plugin actually usable on this box?

A plugin's own CI runs it from the *bundled* ``plugins/<id>/`` layout, one
directory shallower than the ``data/external_plugins/<id>/`` layout it
installs to, and with the plugin repo's dev dependencies present.  Neither
holds for a user.  The Star Trek Quotes plugin passed its own suite for
months while serving ``???`` to everyone, because the data file it read was
created by CI and never shipped.

These checks run at install time, against the tree that actually landed, and
answer one question: *can this plugin possibly work here?*  They deliberately
do not ask whether it is configured -- that is the user's business and comes
later.

Policy (see ``validate_install``):

* A **new install** that fails is rejected.  Nothing is worse than a plugin
  that installs cleanly and then renders ``???`` with no explanation.
* An **already-installed** plugin that starts failing (say, an upgrade drops
  a data file) is reported loudly via ``/api/plugins/errors`` and the
  Integrations UI, but never auto-disabled -- yanking a working board out
  from under someone is a worse failure than a stale one.
"""

from __future__ import annotations

import importlib.util
import re
from dataclasses import dataclass, field
from importlib import metadata as importlib_metadata
from pathlib import Path

# Distributions whose import name differs from the name pip installs under.
IMPORT_NAME_OVERRIDES = {
    "attrs": "attr",
    "beautifulsoup4": "bs4",
    "msgpack-python": "msgpack",
    "pillow": "PIL",
    "python-dateutil": "dateutil",
    "python-dotenv": "dotenv",
    "pyyaml": "yaml",
    "speedtest-cli": "speedtest",
}

_REQUIREMENT_NAME = re.compile(r"^[A-Za-z0-9._-]+")

# ── heuristic: does the source read a data file it never declared? ──────────
#
# The declaration is authoritative, but it is opt-in, and the plugin that
# started all this did not declare anything. This scan is the backstop: it
# reads the source for __file__-relative data paths and reports ones the
# manifest does not cover. It is a *warning* everywhere except the registry
# submission lane -- a regex over source is a guess, and a guess must never
# block an install.

DATA_SUFFIXES = ("json", "csv", "txt", "yaml", "yml", "ndjson", "tsv")

#   Path(__file__).parent / "quotes.json"
#   Path(__file__).parent.parent / "src" / "utils" / "x.json"
#   os.path.join(os.path.dirname(__file__), "data", "x.json")
_FILE_ANCHORED = re.compile(
    r"""
    (?P<anchor>
        Path\(\s*__file__\s*\)(?P<hops>(?:\s*\.\s*parent)*)
        | os\.path\.dirname\(\s*__file__\s*\)
    )
    (?P<tail>(?:\s*[/,]\s*(?:["'][^"']+["']|\w+\s*\(\s*\))|\s*\)\s*)*)
    """,
    re.VERBOSE,
)

#   plugin_dir = Path(__file__).parent
#   quotes_file = plugin_dir / "quotes.json"
_ANCHOR_ASSIGN = re.compile(
    r"""^[ \t]*(?P<name>\w+)[ \t]*=[ \t]*
        (?:Path\(\s*__file__\s*\)(?P<hops>(?:\s*\.\s*parent)*)
         | os\.path\.dirname\(\s*__file__\s*\))
        [ \t]*$""",
    re.VERBOSE | re.MULTILINE,
)

_QUOTED = re.compile(r"""["']([^"']+)["']""")

_NON_RUNTIME_PARTS = {"tests", "test", "docs", "__pycache__", ".git", ".github"}


def python_sources(plugin_dir: Path) -> list[Path]:
    """Runtime .py files for a plugin (tests, docs and caches excluded)."""
    return [
        p
        for p in sorted(plugin_dir.rglob("*.py"))
        if not any(part in _NON_RUNTIME_PARTS for part in p.relative_to(plugin_dir).parts)
    ]


def referenced_data_paths(source: str) -> list[tuple[int, list[str]]]:
    """Find ``__file__``-anchored data-file references in source text.

    Returns ``(parent_hops, path_segments)`` per distinct reference.
    ``parent_hops`` counts ``.parent`` steps, which is what reveals a path
    reaching outside the plugin's own directory.
    """
    refs: list[tuple[int, list[str]]] = []

    for match in _FILE_ANCHORED.finditer(source):
        segments = _QUOTED.findall(match.group("tail") or "")
        if not segments or not segments[-1].lower().endswith(DATA_SUFFIXES):
            continue
        hops = len(re.findall(r"\.\s*parent", match.group("hops") or ""))
        if match.group("anchor").startswith("os.path.dirname"):
            hops = 1
        refs.append((hops, segments))

    for assign in _ANCHOR_ASSIGN.finditer(source):
        name = assign.group("name")
        hops = len(re.findall(r"\.\s*parent", assign.group("hops") or "")) or 1
        joined = re.compile(
            rf"""(?:\b{re.escape(name)}\b(?P<tail>(?:\s*/\s*["'][^"']+["'])+)
                 | os\.path\.join\(\s*{re.escape(name)}\s*(?P<jtail>(?:,\s*["'][^"']+["'])+)\s*\))""",
            re.VERBOSE,
        )
        for use in joined.finditer(source):
            segments = _QUOTED.findall(use.group("tail") or use.group("jtail") or "")
            if not segments or not segments[-1].lower().endswith(DATA_SUFFIXES):
                continue
            refs.append((hops, segments))

    deduped = dict.fromkeys((hops, tuple(segs)) for hops, segs in refs)
    return [(hops, list(segs)) for hops, segs in deduped]


def detect_data_file_problems(plugin_dir: Path, declared: list[str]) -> tuple[list[str], list[str]]:
    """Scan source for data-file reads the declaration does not cover.

    Returns ``(errors, warnings)``.  Severity follows whether the plugin can
    actually work, **not** whether the author remembered to declare anything:

    * a path that escapes the plugin directory -> error (can never resolve
      once installed, no matter what is on disk)
    * a file that is read but absent -> error (the plugin is broken right now;
      this is the Star Trek case, which declared nothing)
    * a file that is read, present, but undeclared -> warning (works today,
      but nothing would catch it going missing at install time)
    """
    declared_set = set(declared)
    errors: list[str] = []
    warnings: list[str] = []
    seen: set[str] = set()

    for src in python_sources(plugin_dir):
        try:
            text = src.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "__file__" not in text:
            continue
        rel_src = src.relative_to(plugin_dir)
        depth = len(rel_src.parts)  # 1 == plugin root

        for hops, segments in referenced_data_paths(text):
            joined = "/".join(segments)
            if joined == "manifest.json":
                continue
            key = f"{rel_src}:{joined}"
            if key in seen:
                continue
            seen.add(key)

            if hops - 1 >= depth:
                errors.append(
                    f"{rel_src} reads {joined!r} from outside the plugin "
                    f"directory ({hops - 1} levels up). That path only "
                    f"resolves in the bundled plugins/<id>/ layout and breaks "
                    f"once the plugin is installed."
                )
                continue

            base = src.parent
            for _ in range(max(hops - 1, 0)):
                base = base.parent
            if not base.joinpath(*segments).exists():
                errors.append(
                    f"{rel_src} reads {joined!r} but no such file ships with "
                    f"the plugin. Every variable it provides will render "
                    f"'???'."
                )
            elif joined not in declared_set:
                warnings.append(
                    f"{rel_src} reads {joined!r} but manifest data_files does "
                    f"not declare it, so a missing copy would not be caught "
                    f"at install time"
                )
    return errors, warnings


@dataclass
class InstallCheckResult:
    """Outcome of validating one plugin directory."""

    plugin_id: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when nothing would stop this plugin from working."""
        return not self.errors

    def to_dict(self) -> dict[str, list[str]]:
        return {"errors": list(self.errors), "warnings": list(self.warnings)}


def _declared_requirements(plugin_dir: Path) -> list[str]:
    """Distribution names from the plugin's runtime requirements.txt."""
    names: list[str] = []
    for req in sorted(plugin_dir.rglob("requirements.txt")):
        if "dev" in req.name:
            continue
        if any(part in {".git", "__pycache__", "tests"} for part in req.parts):
            continue
        try:
            content = req.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in content.splitlines():
            line = line.split("#")[0].strip()
            if not line or line.startswith("-"):
                continue
            match = _REQUIREMENT_NAME.match(line)
            if match:
                names.append(match.group(0))
    # dedupe, order-stable
    return list(dict.fromkeys(names))


def _is_importable(distribution: str) -> bool:
    """True when this runtime provides *distribution*.

    Installed metadata is asked first, because it is keyed by the name pip
    installs under (PEP 503 normalised) and so needs no guess about the import
    name.  Guessing is what makes this dangerous: a wrong guess here is a
    blocking error that *refuses the install*, and FiestaBoard ships two
    packages whose import name differs from their distribution name without
    appearing in the override table below -- ``finnhub-python`` (imports as
    ``finnhub``) and ``paho-mqtt`` (imports as ``paho.mqtt``).  A plugin
    declaring either would have been rejected for a dependency that is in
    fact present.

    ``find_spec`` remains as a fallback for a module that is importable
    without installed metadata -- vendored, or provided under a different
    distribution name.
    """
    try:
        importlib_metadata.distribution(distribution)
        return True
    except importlib_metadata.PackageNotFoundError:
        pass
    except (ValueError, OSError):
        # Malformed name or unreadable metadata: fall through to the import
        # probe rather than treating the dependency as missing.
        pass

    module = IMPORT_NAME_OVERRIDES.get(distribution.lower(), distribution.replace("-", "_"))
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def check_declared_data_files(plugin_dir: Path, declared: list[str]) -> list[str]:
    """Every file the manifest promises must actually be present."""
    errors = []
    for rel in declared:
        target = plugin_dir / rel
        if not target.exists():
            errors.append(
                f"manifest declares data file {rel!r} but it is missing from the plugin. The install is incomplete."
            )
        elif not target.is_file():
            errors.append(f"manifest declares data file {rel!r} but it is not a file.")
    return errors


def check_declaration_is_well_formed(raw_manifest: dict, declared: list[str]) -> list[str]:
    """Catch entries parse_data_files() dropped for escaping the plugin dir."""
    raw = raw_manifest.get("data_files")
    if not isinstance(raw, list):
        return []
    kept = set(declared)
    errors = []
    for entry in raw:
        if not isinstance(entry, str):
            errors.append(f"data_files entry {entry!r} is not a string")
            continue
        normalised = entry.strip().replace("\\", "/")
        parts = [p for p in normalised.split("/") if p not in ("", ".")]
        if "/".join(parts) in kept:
            continue
        errors.append(
            f"data_files entry {entry!r} is not a path inside the plugin "
            f"directory. Plugins must ship their own data; reaching outside "
            f"the plugin directory only works in the bundled layout and "
            f"breaks once installed."
        )
    return errors


def check_dependencies(plugin_dir: Path) -> list[str]:
    """Declared third-party packages must be importable in this runtime.

    The platform does not install a plugin's requirements.txt, so anything
    listed there is missing at runtime unless the platform happens to ship it.
    """
    errors = []
    for dist in _declared_requirements(plugin_dir):
        if not _is_importable(dist):
            errors.append(
                f"requires Python package {dist!r}, which is not available. "
                f"FiestaBoard does not install plugin dependencies; the plugin "
                f"must rely only on the standard library and the packages "
                f"FiestaBoard already ships."
            )
    return errors


def check_required_files(plugin_dir: Path) -> list[str]:
    """The files every plugin needs regardless of what it declares."""
    errors = []
    for required in ("__init__.py", "manifest.json"):
        if not (plugin_dir / required).is_file():
            errors.append(f"missing required file {required!r}")
    return errors


def validate_install(
    plugin_id: str,
    plugin_dir: Path,
    manifest,
) -> InstallCheckResult:
    """Validate a plugin directory that has just been installed or loaded.

    Args:
        plugin_id: The plugin's id.
        plugin_dir: Directory the plugin was installed into.
        manifest: A parsed ``PluginManifest`` (or None if it would not parse).

    Returns:
        An :class:`InstallCheckResult`. ``result.ok`` is False when the plugin
        cannot work here, whatever the user configures.
    """
    result = InstallCheckResult(plugin_id=plugin_id)

    if not plugin_dir.is_dir():
        result.errors.append(f"plugin directory {plugin_dir} does not exist")
        return result

    result.errors.extend(check_required_files(plugin_dir))

    if manifest is None:
        result.errors.append("manifest.json could not be parsed")
        return result

    declared = list(getattr(manifest, "data_files", []) or [])
    raw_manifest = getattr(manifest, "raw", {}) or {}

    result.errors.extend(check_declaration_is_well_formed(raw_manifest, declared))
    result.errors.extend(check_declared_data_files(plugin_dir, declared))
    result.errors.extend(check_dependencies(plugin_dir))

    # Backstop for the plugin that declares nothing -- which is every plugin
    # published before data_files existed, including the one that prompted it.
    # A genuinely missing file is an error even when undeclared; merely
    # failing to declare a file that is present is advisory.
    scan_errors, scan_warnings = detect_data_file_problems(plugin_dir, declared)
    result.errors.extend(scan_errors)
    result.warnings.extend(scan_warnings)

    return result
