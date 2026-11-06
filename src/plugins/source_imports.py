"""Read ordinary plugin source directly without trusting timestamp bytecode."""

import sys
from importlib.machinery import FileFinder, SourceFileLoader
from pathlib import Path
from threading import RLock
from types import CodeType

_roots: set[Path] = set()
_roots_lock = RLock()


def _within_plugin_tree(path: str | Path) -> bool:
    try:
        resolved = Path(path).resolve()
    except (OSError, RuntimeError, ValueError):
        return False
    with _roots_lock:
        roots = tuple(_roots)
    return any(resolved.is_relative_to(root) for root in roots)


class CurrentSourceLoader(SourceFileLoader):
    """Keep normal source decoding/compilation, bypass only the pyc cache."""

    def get_code(self, fullname: str) -> CodeType:
        source_path = self.get_filename(fullname)
        return self.source_to_code(self.get_data(source_path), source_path)


def plugin_source_loader(fullname: str, filename: str) -> SourceFileLoader:
    """Leave sources resolving outside a registered plugin tree unchanged."""
    loader = CurrentSourceLoader if _within_plugin_tree(filename) else SourceFileLoader
    return loader(fullname, filename)


class CurrentSourceFinder(FileFinder):
    """Preserve a directory finder's policy, replacing only plain source loads."""

    def __init__(self, path: str, *loader_details, delegate: FileFinder | None = None) -> None:
        self._finder = delegate if delegate is not None else FileFinder(path, *loader_details)
        self._finder.invalidate_caches()

    def __getattr__(self, name: str):
        return getattr(self._finder, name)

    def find_spec(self, fullname: str, target=None):
        spec = self._finder.find_spec(fullname, target)
        if spec is not None and type(spec.loader) is SourceFileLoader:
            spec.loader = plugin_source_loader(fullname, spec.loader.get_filename(fullname))
        return spec

    def invalidate_caches(self) -> None:
        self._finder.invalidate_caches()


def _plugin_path_hook(path: str):
    """Delegate normal hook selection lazily, only inside registered trees.

    Do not prepopulate cold directories: plugin entry code can install a custom
    hook before its first sibling import. Custom finders/loaders keep their
    policy; only an ordinary FileFinder is adapted.
    """
    if not _within_plugin_tree(path):
        raise ImportError(path)
    for hook in tuple(sys.path_hooks):
        if hook is _plugin_path_hook:
            continue
        try:
            finder = hook(path)
        except ImportError:
            continue
        if type(finder) is FileFinder:
            return CurrentSourceFinder(path, delegate=finder)
        return finder
    raise ImportError(path)


def prepare_source_imports(plugin_dir: Path) -> None:
    """Register a verified tree, preserving cold and custom import policy."""
    root = plugin_dir.resolve()
    with _roots_lock:
        _roots.add(root)
        if not any(hook is _plugin_path_hook for hook in sys.path_hooks):
            sys.path_hooks.insert(0, _plugin_path_hook)
    # Resolve paths and invoke finder methods outside our registration lock.
    # Warm finders may predate registration; cold directories use the hook.
    for directory, previous in list(sys.path_importer_cache.items()):
        if not isinstance(directory, str) or not _within_plugin_tree(directory):
            continue
        if isinstance(previous, CurrentSourceFinder):
            previous.invalidate_caches()
        elif type(previous) is FileFinder and sys.path_importer_cache.get(directory) is previous:
            sys.path_importer_cache[directory] = CurrentSourceFinder(directory, delegate=previous)
