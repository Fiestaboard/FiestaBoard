"""External plugin source management.

Handles loading plugins from three sources:
1. Built-in  – plugins shipped in the repository's ``plugins/`` directory.
2. Registry  – plugins listed in ``plugin-registry.json`` (git repos in the
   FiestaBoard organisation that follow the ``fiestaboard-plugin--{name}``
   naming convention).
3. Git URL   – arbitrary public git repositories specified by the user.

External plugins (registry and git) are cloned into a persistent
``external_plugins/`` directory so they survive container restarts.
"""

import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── constants ────────────────────────────────────────────────────────────────

# Conservative git ref pattern for branch/tag names supplied by users.
# Disallows whitespace, shell/control chars, path traversal, and refs that
# start with '-' (option-like).
GIT_REF_RE = re.compile(r"^(?!-)(?!.*\.\.)(?!.*//)[A-Za-z0-9._/-]{1,255}$")

REGISTRY_FILENAME = "plugin-registry.json"
EXTERNAL_PLUGINS_DIR = "external_plugins"

# Naming convention for registry plugins
REGISTRY_PREFIX = "fiestaboard-plugin--"
REGISTRY_NAME_RE = re.compile(r"^fiestaboard-plugin--[a-z][a-z0-9-]*$")

# Plugin id must be a safe single-segment identifier so it can be used as a
# directory name without enabling path traversal.  Same character set as a
# Python identifier with optional leading lowercase letter.
PLUGIN_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

# Constant character allow-list used to rebuild a validated plugin id from
# scratch before passing it to the filesystem.  Keeping this as a literal
# string (not derived from user input) gives static analysers a clear
# barrier for path-injection flows.
_PLUGIN_ID_ALLOWED = "abcdefghijklmnopqrstuvwxyz0123456789_"

# Simple allow-list for git URL schemes
_ALLOWED_SCHEMES = ("https://",)

# Where the plugin code lives inside a cloned repo (root by default)
_PLUGIN_SUBDIR = ""

# ── data classes ─────────────────────────────────────────────────────────────


@dataclass
class PluginSource:
    """Describes where a plugin was loaded from."""

    #: "builtin", "registry", or "git"
    source_type: str

    #: For registry/git sources, the git URL.  Empty for built-in plugins.
    repository_url: str = ""

    #: The directory on disk where the plugin lives after checkout/clone.
    local_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_type": self.source_type,
            "repository_url": self.repository_url,
            "local_path": self.local_path,
        }


@dataclass
class RegistryEntry:
    """A single entry in ``plugin-registry.json``."""

    #: Plugin id (manifest id) – derived from the repo name.
    plugin_id: str

    #: Display name.
    name: str

    #: Short description.
    description: str = ""

    #: HTTPS URL of the git repository.
    repository: str = ""

    #: Which branch/tag to clone.  Defaults to the repo's default branch.
    branch: str = ""

    #: Plugin author.
    author: str = ""

    #: Minimum FiestaBoard version required (semver constraint, e.g. ">=2.10.0").
    fiestaboard_version: str = ""

    #: Lucide icon name.
    icon: str = "puzzle"

    #: Plugin category.
    category: str = "utility"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RegistryEntry":
        return cls(
            plugin_id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            repository=data.get("repository", ""),
            branch=data.get("branch", ""),
            author=data.get("author", ""),
            fiestaboard_version=data.get("fiestaboard_version", ""),
            icon=data.get("icon", "puzzle"),
            category=data.get("category", "utility"),
        )


# ── registry loading ────────────────────────────────────────────────────────


def load_registry(registry_path: Optional[Path] = None) -> List[RegistryEntry]:
    """Load the plugin registry JSON file.

    Args:
        registry_path: Explicit path.  When *None* the file is located
            relative to the project root.

    Returns:
        List of :class:`RegistryEntry` objects.  Returns an empty list when the
        file is missing or unparseable.
    """
    if registry_path is None:
        project_root = Path(__file__).parent.parent.parent
        registry_path = project_root / REGISTRY_FILENAME

    if not registry_path.exists():
        logger.debug("Plugin registry not found at %s", registry_path)
        return []

    try:
        with open(registry_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to read plugin registry %s: %s", registry_path, exc)
        return []

    entries: List[RegistryEntry] = []
    for item in data.get("plugins", []):
        entry = RegistryEntry.from_dict(item)
        if not entry.plugin_id or not entry.repository:
            logger.warning("Skipping invalid registry entry: %s", item)
            continue
        entries.append(entry)

    logger.info("Loaded %d entries from plugin registry", len(entries))
    return entries


# ── naming convention helpers ────────────────────────────────────────────────


def validate_registry_repo_name(repo_url: str) -> Tuple[bool, str]:
    """Check that a repository URL follows the registry naming convention.

    Registry plugins **must** live in a repository whose name matches
    `fiestaboard-plugin--{name}`.

    Args:
        repo_url: Full HTTPS URL of the repository.

    Returns:
        ``(True, "")`` when valid, ``(False, reason)`` otherwise.
    """
    repo_name = repo_name_from_url(repo_url)
    if not repo_name:
        return False, f"Cannot extract repository name from URL: {repo_url}"
    if not REGISTRY_NAME_RE.match(repo_name):
        return (
            False,
            f"Repository name '{repo_name}' does not follow the required "
            f"'{REGISTRY_PREFIX}{{name}}' naming convention",
        )
    return True, ""


def plugin_id_from_repo_name(repo_name: str) -> str:
    """Derive the plugin id from a ``fiestaboard-plugin--{name}`` repo name.

    Dashes in the suffix are converted to underscores to match manifest id
    conventions.

    >>> plugin_id_from_repo_name("fiestaboard-plugin--my-weather")
    'my_weather'
    """
    if repo_name.startswith(REGISTRY_PREFIX):
        suffix = repo_name[len(REGISTRY_PREFIX):]
        return suffix.replace("-", "_")
    return repo_name.replace("-", "_")


def repo_name_from_url(url: str) -> str:
    """Extract the repository name from a git URL.

    >>> repo_name_from_url("https://github.com/Org/fiestaboard-plugin--foo.git")
    'fiestaboard-plugin--foo'
    """
    url = url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    return url.rsplit("/", 1)[-1] if "/" in url else ""


# ── git operations ───────────────────────────────────────────────────────────


def _validate_git_url(url: str) -> Tuple[bool, str]:
    """Very basic validation that *url* looks like an HTTPS git URL.

    In addition to scheme checking we reject characters that could confuse
    ``git`` into treating the URL as an option (a leading ``-`` after the
    scheme), or shell metacharacters that have no business appearing in a
    repository URL.  This keeps the URL safe to pass to ``subprocess.run``
    even though we already invoke ``git`` without a shell.
    """
    if not isinstance(url, str) or not url:
        return False, "URL must be a non-empty string"
    if not any(url.startswith(s) for s in _ALLOWED_SCHEMES):
        return False, f"Only HTTPS URLs are supported (got {url!r})"
    if ".." in url or any(c in url for c in "\n\r\t \"'`$;|&<>\\"):
        return False, "URL contains invalid characters"

    # Parse and sanity-check the URL structure.
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
    except ValueError:
        return False, "URL could not be parsed"
    if parsed.scheme != "https" or not parsed.hostname:
        return False, "URL must be a fully-qualified https URL"
    # Embedded credentials (https://user:pass@host) are not needed for
    # public clones and would leak into logs / process listings.
    if parsed.username is not None or parsed.password is not None:
        return False, "URL must not contain credentials"
    # Defence in depth: even after the scheme check, refuse to pass a value
    # that could be parsed as a CLI option.
    if url.lstrip().startswith("-"):
        return False, "URL must not start with '-'"
    return True, ""


def _validate_plugin_id(plugin_id: str) -> Tuple[bool, str]:
    """Validate that *plugin_id* is safe to use as a single path segment."""
    if not isinstance(plugin_id, str) or not PLUGIN_ID_RE.match(plugin_id):
        return False, (
            f"Invalid plugin id {plugin_id!r}: must match "
            f"{PLUGIN_ID_RE.pattern}"
        )
    return True, ""


def _validate_git_ref(ref: str) -> Tuple[bool, str]:
    """Validate a user-supplied git branch/tag name."""
    if not isinstance(ref, str):
        return False, "Invalid branch/tag: must be a string"
    if not GIT_REF_RE.fullmatch(ref):
        return False, (
            f"Invalid branch/tag {ref!r}: must match {GIT_REF_RE.pattern}"
        )
    return True, ""


def clone_or_update_repo(
    repo_url: str,
    dest_dir: Path,
    branch: str = "",
    *,
    allowed_root: Optional[Path] = None,
) -> Tuple[bool, str]:
    """Clone a git repository, or fetch/reset if it already exists.

    For existing clones (the update path) the ``repo_url`` is not used —
    git pulls from whatever remote ``origin`` is already configured.  This
    means the URL validation is intentionally skipped for that path, which
    also avoids a bug where the registry stores an empty ``repository_url``
    for plugins loaded from disk.

    Shallow clones (``--depth 1``) are handled correctly: we use
    ``git fetch --depth=1 origin`` + ``git reset --hard FETCH_HEAD`` instead
    of ``git pull --ff-only``, which fails on shallow histories.

    Args:
        repo_url: HTTPS URL of the repository (required for fresh clones only).
        dest_dir: Local directory to clone into.
        branch: Optional branch/tag.  Uses the repo default when empty.
        allowed_root: Trusted root directory that ``dest_dir`` must be contained
            within.  If not provided, defaults to the result of
            :func:`get_external_plugins_dir`.  High-level callers (e.g.
            :func:`install_registry_plugin`) should pass the same
            ``external_dir`` they used when constructing ``dest_dir`` so that
            the containment check uses a consistent boundary.

    Returns:
        ``(True, "")`` on success, ``(False, error_message)`` on failure.
    """
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}

    # Defensive sink-level guard.  The path used at filesystem and
    # subprocess sinks is built **purely** from trusted constants:
    #
    #   * ``external_root`` — the realpath of the trusted ``allowed_root``
    #     parameter (defaults to :func:`get_external_plugins_dir`).
    #   * ``safe_basename`` — extracted via :func:`re.fullmatch` against
    #     :data:`PLUGIN_ID_RE` and reassigned from ``m.group(0)``.
    #     ``m.group(0)`` is a CodeQL-recognised sanitiser for
    #     ``py/path-injection`` / ``py/command-line-injection`` because
    #     the matched substring is, by construction, a member of the
    #     literal alphabet ``[a-z][a-z0-9_]{0,63}`` (no ``/``, ``\``,
    #     ``..``, NUL, or shell metacharacters can appear).
    #
    # The raw ``dest_dir`` argument is used only for two things:
    #   1. An *input* containment check — we reject callers that pass a
    #      path pointing outside ``allowed_root`` (path traversal,
    #      sibling dirs, …).  This is a guard, not a source for ``safe_dest``.
    #   2. Extracting the basename string for regex validation.  The
    #      basename never reaches a sink directly — only ``m.group(0)``
    #      does.
    root = allowed_root if allowed_root is not None else get_external_plugins_dir()
    external_root = os.path.realpath(str(root))

    # (1) Reject inputs that resolve outside the trusted root.  This is a
    #     pure boolean guard — ``input_real`` does **not** flow into the
    #     path actually used at the sinks below.
    input_real = os.path.realpath(str(dest_dir))
    try:
        _common = os.path.commonpath([external_root, input_real])
    except ValueError:
        return False, (
            f"Refusing to use destination outside external plugins directory: "
            f"{dest_dir}"
        )
    if _common != external_root or input_real == external_root:
        return False, (
            f"Refusing to use destination outside external plugins directory: "
            f"{dest_dir}"
        )

    # (2) Extract the basename as a *string* and validate via regex.
    #     ``m.group(0)`` is the regex-matched substring — a CodeQL
    #     barrier for path/command injection.
    raw_basename = os.path.basename(os.path.normpath(str(dest_dir)))
    m = PLUGIN_ID_RE.fullmatch(raw_basename)
    if not m:
        return False, (
            f"Refusing to use destination with invalid basename: {dest_dir}"
        )
    safe_basename = m.group(0)
    # Belt-and-braces character-level allow-list (no-op when the regex
    # holds, but gives CodeQL a second, literal barrier).
    if any(c not in _PLUGIN_ID_ALLOWED for c in safe_basename):
        return False, (
            f"Refusing to use destination with invalid basename: {dest_dir}"
        )

    # Build the path actually used at the sinks from the trusted root
    # and the regex-matched basename only.  ``safe_dest`` therefore does
    # not depend on the raw ``dest_dir`` argument's path components.
    safe_dest = Path(os.path.join(external_root, safe_basename))

    if safe_dest.exists() and (safe_dest / ".git").is_dir():
        # Already cloned — fetch latest commits and reset to remote HEAD.
        # Works for both full and shallow (--depth 1) clones.
        try:
            subprocess.run(
                ["git", "-C", str(safe_dest), "fetch", "--depth=1", "origin"],
                check=True, capture_output=True, text=True,
                timeout=120, env=env,
            )
            subprocess.run(
                ["git", "-C", str(safe_dest), "reset", "--hard", "FETCH_HEAD"],
                check=True, capture_output=True, text=True,
                timeout=30, env=env,
            )
            logger.info("Updated existing plugin clone")
            return True, ""
        except subprocess.SubprocessError as exc:
            return False, f"git fetch/reset failed at {safe_dest}: {exc}"

    # Fresh clone — URL is required and must be validated.
    ok, err = _validate_git_url(repo_url)
    if not ok:
        return False, err
    # Re-derive repo_url from a regex match so downstream subprocess calls
    # are not tracked as tainted by static-analysis tools
    # (py/command-line-injection).  The pattern enforces the same character
    # constraints as _validate_git_url.
    _url_m = re.fullmatch(r"https://[^\x00-\x1f\s\"'<>\\]+", repo_url)
    if not _url_m:
        return False, "URL contains unexpected characters after validation"
    repo_url = _url_m.group(0)

    if branch:
        ok, err = _validate_git_ref(branch)
        if not ok:
            return False, err

    safe_dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        cmd = ["git", "clone", "--depth", "1"]
        if branch:
            cmd += ["--branch", branch]
        # ``--`` ensures the repo URL and destination are treated as
        # positional arguments and never as options, even if validation
        # somehow misses a leading ``-``.
        cmd += ["--", repo_url, str(safe_dest)]
        subprocess.run(
            cmd, check=True, capture_output=True, text=True,
            timeout=120, env=env,
        )
        logger.info("Cloned external plugin repository successfully")
        return True, ""
    except subprocess.SubprocessError as exc:
        return False, f"git clone failed for {repo_url}: {exc}"


def get_remote_head_sha(dest_dir: Path) -> Optional[str]:
    """Return the remote HEAD SHA for the origin of an existing clone.

    Uses ``git ls-remote`` which is a lightweight network operation that does
    not modify the local repository.  Returns *None* on any error.
    """
    if not dest_dir.exists() or not (dest_dir / ".git").is_dir():
        return None

    try:
        # Get the remote URL from the local clone
        result = subprocess.run(
            ["git", "-C", str(dest_dir), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return None
        remote_url = result.stdout.strip()
        # Validate the URL read from the local git config before passing it
        # into another subprocess call (prevents command/path injection).
        ok, _ = _validate_git_url(remote_url)
        if not ok:
            return None
        # Re-derive remote_url from a regex match so the subprocess sink
        # does not see it as tainted (CodeQL py/command-line-injection).
        _url_m = re.fullmatch(r"https://[^\x00-\x1f\s\"'<>\\]+", remote_url)
        if not _url_m:
            return None
        remote_url = _url_m.group(0)

        # Determine the default branch name tracked locally
        branch_result = subprocess.run(
            ["git", "-C", str(dest_dir), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        branch = branch_result.stdout.strip() or "main"
        # Allow only characters that are legal in git branch names and safe
        # as subprocess arguments (prevents argument injection).
        # Re-derive branch from the match result so the subprocess sink
        # does not see it as tainted (CodeQL py/command-line-injection).
        _branch_m = re.match(r'^[A-Za-z0-9_./-]+$', branch)
        if not _branch_m:
            return None
        branch = _branch_m.group(0)

        # Query the remote for the latest SHA
        ls_result = subprocess.run(
            ["git", "ls-remote", "--heads", remote_url, branch],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        if ls_result.returncode != 0 or not ls_result.stdout.strip():
            return None

        # Output format: "<sha>\trefs/heads/<branch>"
        sha = ls_result.stdout.strip().split()[0]
        return sha
    except (subprocess.SubprocessError, IndexError, OSError):
        return None


def get_local_head_sha(dest_dir: Path) -> Optional[str]:
    """Return the local HEAD SHA of a cloned plugin repository."""
    if not dest_dir.exists() or not (dest_dir / ".git").is_dir():
        return None
    try:
        result = subprocess.run(
            ["git", "-C", str(dest_dir), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (subprocess.SubprocessError, OSError):
        return None


def check_plugin_update_available(dest_dir: Path) -> bool:
    """Return True if the remote has commits not yet pulled locally."""
    local = get_local_head_sha(dest_dir)
    remote = get_remote_head_sha(dest_dir)
    if local is None or remote is None:
        return False
    return local != remote


def remove_external_plugin(dest_dir: Path) -> bool:
    """Remove a cloned external plugin directory.

    Returns:
        ``True`` if removed, ``False`` if the directory did not exist.
    """
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
        logger.info("Removed external plugin directory: %s", dest_dir)
        return True
    return False


# ── high-level helpers ───────────────────────────────────────────────────────


def get_external_plugins_dir(project_root: Optional[Path] = None) -> Path:
    """Return the directory used for cloned external plugins.

    The directory is created if it does not exist.
    """
    if project_root is None:
        project_root = Path(__file__).parent.parent.parent
    ext_dir = project_root / EXTERNAL_PLUGINS_DIR
    ext_dir.mkdir(parents=True, exist_ok=True)
    return ext_dir


def _safe_external_dest(
    external_dir: Path, plugin_id: str
) -> Tuple[Optional[Path], str]:
    """Compute a safe destination path inside `external_dir` for a plugin.

    The plugin id flows through three independent CodeQL-recognized
    path-injection barriers before it ever reaches a filesystem call:

    1. :func:`re.fullmatch` against a strict character-class allow-list.
    2. Per-character allow-list reconstruction — the value is rebuilt
       from a constant string of permitted characters and the result
       must equal the original input.
    3. After `os.path.realpath`, :func:`os.path.commonpath` is used to
       prove the resolved candidate is contained within
       `external_root`.  This is the canonical CodeQL sanitizer for
       `py/path-injection` and is checked **before** any further use
       of the path.
    """
    if not isinstance(plugin_id, str) or not plugin_id:
        return None, "Invalid plugin id"

    # (1) Inline allow-list match (single segment, lowercase + digits +
    # underscore only).
    if not PLUGIN_ID_RE.fullmatch(plugin_id):
        return None, f"Invalid plugin id {plugin_id!r}"

    # (2) Rebuild from a fixed allow-list and require equality.
    safe_id = "".join(c for c in plugin_id if c in _PLUGIN_ID_ALLOWED)
    if safe_id != plugin_id:
        return None, f"Invalid plugin id {plugin_id!r}"

    # (3) Build and resolve the candidate path, then confirm containment
    # with ``os.path.commonpath`` *before* returning the path.  This is
    # the CodeQL-recognised path-injection barrier.
    external_root = os.path.realpath(str(external_dir))
    raw_candidate = os.path.join(external_root, safe_id)
    candidate_real = os.path.realpath(raw_candidate)
    try:
        common = os.path.commonpath([external_root, candidate_real])
    except ValueError:
        return None, f"Refusing to install plugin outside {external_root}"
    if common != external_root:
        return None, f"Refusing to install plugin outside {external_root}"
    if candidate_real == external_root:
        return None, "Refusing to install plugin at root directory"

    return Path(candidate_real), ""


def install_registry_plugin(
    entry: RegistryEntry,
    external_dir: Optional[Path] = None,
) -> Tuple[bool, str]:
    """Clone a plugin listed in the registry.

    Validates the naming convention before cloning.

    Returns:
        ``(True, "")`` on success, ``(False, reason)`` on failure.
    """
    ok, err = validate_registry_repo_name(entry.repository)
    if not ok:
        return False, err

    ok, err = _validate_plugin_id(entry.plugin_id)
    if not ok:
        return False, err

    if external_dir is None:
        external_dir = get_external_plugins_dir()

    dest, err = _safe_external_dest(external_dir, entry.plugin_id)
    if dest is None:
        return False, err
    return clone_or_update_repo(entry.repository, dest, entry.branch, allowed_root=external_dir)


def install_git_plugin(
    repo_url: str,
    plugin_id: Optional[str] = None,
    branch: str = "",
    external_dir: Optional[Path] = None,
) -> Tuple[bool, str]:
    """Clone an arbitrary public git repository as a plugin.

    Custom git plugins do **not** need to follow the
    ``fiestaboard-plugin--`` naming convention.

    Args:
        repo_url: HTTPS URL of the repository.
        plugin_id: Override the derived plugin id.  When *None* the id is
            derived from the repository name.
        branch: Optional branch or tag to check out.
        external_dir: Override the external plugins directory.

    Returns:
        ``(True, "")`` on success, ``(False, reason)`` on failure.
    """
    # Validate the URL up front so an invalid value can't influence path
    # construction or be passed to ``git`` as an option.
    ok, err = _validate_git_url(repo_url)
    if not ok:
        return False, err

    if external_dir is None:
        external_dir = get_external_plugins_dir()

    repo_name = repo_name_from_url(repo_url)
    if not repo_name:
        return False, f"Cannot determine repository name from URL: {repo_url}"

    if plugin_id is None:
        plugin_id = plugin_id_from_repo_name(repo_name)

    ok, err = _validate_plugin_id(plugin_id)
    if not ok:
        return False, err

    dest, err = _safe_external_dest(external_dir, plugin_id)
    if dest is None:
        return False, err
    return clone_or_update_repo(repo_url, dest, branch, allowed_root=external_dir)
