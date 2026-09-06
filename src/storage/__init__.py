"""Storage kernel: the one atomic, locked, schema-versioned JSON store.

Every JSON-file store (pages, schedules, collections, panels, settings) is
built on :class:`src.storage.json_store.JsonStore` instead of open-coding the
staging-file write, the lock, and the migration runner.
"""

from .json_store import JsonStore

__all__ = ["JsonStore"]
