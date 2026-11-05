"""Read plugin source directly without trusting timestamp-based bytecode."""

import os
import sys
from importlib.machinery import (
    BYTECODE_SUFFIXES,
    EXTENSION_SUFFIXES,
    SOURCE_SUFFIXES,
    ExtensionFileLoader,
    FileFinder,
    SourceFileLoader,
    SourcelessFileLoader,
)
from pathlib import Path
from types import CodeType


class CurrentSourceLoader(SourceFileLoader):
    """Keep normal source decoding/compilation, bypass only the pyc cache."""

    def get_code(self, fullname: str) -> CodeType:
        source_path = self.get_filename(fullname)
        return self.source_to_code(self.get_data(source_path), source_path)


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
            spec.loader = CurrentSourceLoader(fullname, spec.loader.get_filename(fullname))
        return spec

    def invalidate_caches(self) -> None:
        self._finder.invalidate_caches()


def prepare_source_imports(plugin_dir: Path) -> None:
    """Use current source for ordinary imports inside this verified tree.

    The entry module uses CurrentSourceLoader explicitly. Its relative or
    flattened imports use these ordinary directory finders. No global path
    hook is installed, and custom finders retain their own policy.
    """
    root = plugin_dir.resolve()
    root_key = str(root)
    directories = {root_key}
    for folder, children, files in os.walk(root, followlinks=False):
        children[:] = [name for name in children if name not in {".git", "__pycache__"}]
        if any(name.endswith(tuple(SOURCE_SUFFIXES)) for name in files):
            directories.add(folder)
    # Include previously imported directories, even if an update removed their
    # last source file. Never resolve or replace unrelated interpreter entries.
    for key in list(sys.path_importer_cache):
        if not isinstance(key, str) or not key.startswith(root_key + os.sep):
            continue
        try:
            resolved = Path(key).resolve()
        except OSError:
            continue
        if resolved.is_relative_to(root) and resolved.is_dir():
            directories.add(key)
    for directory in directories:
        previous = sys.path_importer_cache.get(directory)
        if isinstance(previous, CurrentSourceFinder):
            previous.invalidate_caches()
            continue
        if previous is not None and type(previous) is not FileFinder:
            continue
        sys.path_importer_cache[directory] = CurrentSourceFinder(
            directory,
            (ExtensionFileLoader, EXTENSION_SUFFIXES),
            (SourceFileLoader, SOURCE_SUFFIXES),
            (SourcelessFileLoader, BYTECODE_SUFFIXES),
            delegate=previous,
        )
