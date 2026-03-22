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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── constants ────────────────────────────────────────────────────────────────

REGISTRY_FILENAME = "plugin-registry.json"
EXTERNAL_PLUGINS_DIR = "external_plugins"

# Naming convention for registry plugins
REGISTRY_PREFIX = "fiestaboard-plugin--"
REGISTRY_NAME_RE = re.compile(r"^fiestaboard-plugin--[a-z][a-z0-9-]*$")

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
    ``fiestaboard-plugin--{name}``.

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
    """Very basic validation that *url* looks like an HTTPS git URL."""
    if not any(url.startswith(s) for s in _ALLOWED_SCHEMES):
        return False, f"Only HTTPS URLs are supported (got {url!r})"
    if ".." in url or "\n" in url or " " in url:
        return False, "URL contains invalid characters"
    return True, ""


def clone_or_update_repo(
    repo_url: str,
    dest_dir: Path,
    branch: str = "",
) -> Tuple[bool, str]:
    """Clone a git repository, or pull updates if it already exists.

    Args:
        repo_url: HTTPS URL of the repository.
        dest_dir: Local directory to clone into.
        branch: Optional branch/tag.  Uses the repo default when empty.

    Returns:
        ``(True, "")`` on success, ``(False, error_message)`` on failure.
    """
    ok, err = _validate_git_url(repo_url)
    if not ok:
        return False, err

    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}

    if dest_dir.exists() and (dest_dir / ".git").is_dir():
        # Already cloned – pull latest
        try:
            cmd = ["git", "-C", str(dest_dir), "pull", "--ff-only"]
            subprocess.run(
                cmd, check=True, capture_output=True, text=True,
                timeout=120, env=env,
            )
            logger.info("Updated existing clone at %s", dest_dir)
            return True, ""
        except subprocess.SubprocessError as exc:
            return False, f"git pull failed for {repo_url}: {exc}"

    # Fresh clone
    dest_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        cmd = ["git", "clone", "--depth", "1"]
        if branch:
            cmd += ["--branch", branch]
        cmd += [repo_url, str(dest_dir)]
        subprocess.run(
            cmd, check=True, capture_output=True, text=True,
            timeout=120, env=env,
        )
        logger.info("Cloned %s → %s", repo_url, dest_dir)
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

        # Determine the default branch name tracked locally
        branch_result = subprocess.run(
            ["git", "-C", str(dest_dir), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        branch = branch_result.stdout.strip() or "main"

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

    if external_dir is None:
        external_dir = get_external_plugins_dir()

    dest = external_dir / entry.plugin_id
    return clone_or_update_repo(entry.repository, dest, entry.branch)


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
    if external_dir is None:
        external_dir = get_external_plugins_dir()

    repo_name = repo_name_from_url(repo_url)
    if not repo_name:
        return False, f"Cannot determine repository name from URL: {repo_url}"

    if plugin_id is None:
        plugin_id = plugin_id_from_repo_name(repo_name)

    dest = external_dir / plugin_id
    return clone_or_update_repo(repo_url, dest, branch)
