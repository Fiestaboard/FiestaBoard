#!/usr/bin/env python3
"""Create a fresh synthetic dataset for the bounded production a11y survey.

Run only in the approved container after the parent task's resource gate.
This stdlib-only tool neither imports the application nor starts a hub,
installs dependencies, reaches the network, or reads an existing data store.
Mount ONLY the resulting ``data/`` as the hub's /app/data; keep the manifest
outside the mutable mount. The published entrypoint assigns data ownership
to appuser. Use a fresh, controlled container environment: copied credential,
plugin, auth, output, MQTT or updater environment overrides can defeat this
fixture. Runtime preflight must verify the observed state after boot.

The JSON shapes were source-reviewed at v11.0.0-alpha.3 (83236253aa81).
That provenance is not a boot result or an image-source attestation. Manual
updates disable the periodic updater, not the shell's on-demand public
Docker Hub/GitHub metadata check. This is not a backend network sandbox.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path

SOURCE_SHA = "83236253aa8103db856b7efa456e088b9c9ec548"
SOURCE_VERSION = "11.0.0-alpha.3"
BOARD_ID = "prod-a11y-synthetic-board"
DATASET_PATTERN = re.compile(r"prod-a11y-[a-z0-9]+(?:-[a-z0-9]+)*\Z")


def _documents() -> dict[str, dict]:
    """Pinned input shapes; do not instantiate services while provisioning."""
    return {
        "config.json": {
            "schema_version": 2,
            "app_version_seen": SOURCE_VERSION,
            "board": {"api_mode": "local", "host": "", "local_api_key": "", "cloud_key": ""},
            "general": {"instance_name": "Synthetic accessibility audit", "timezone": "UTC", "output_target": "board"},
            "features": {"silence_schedule": {"enabled": False}},
            "ai_providers": {"enabled": False, "providers": [], "default_provider_id": None},
            # PluginRegistry.initialize defaults every absent data plugin to
            # disabled. No extracted plugin is configured for auto-install.
            "plugins": {},
        },
        "settings.json": {
            "schema_version": 8,
            "output": {"target": "board"},
            "board": {
                "board_type": "black",
                "boards": [
                    {
                        "id": BOARD_ID,
                        "name": "Synthetic audit board",
                        "device_type": "panel",
                        "board_color": "black",
                        "grid_rows": 6,
                        "grid_cols": 22,
                        "output": "fiestapanel",
                        "output_config": {},
                        "enabled": True,
                        "paused": False,
                        "schedule_enabled": False,
                        "schedule_defer_on_reenable": False,
                        "auto_restore": False,
                        "transition": "none",
                    }
                ],
            },
            "wizard": {"state": "completed"},
            "active_page": {"page_id": None, "by_board": {}},
            "schedule": {"enabled": False, "defer_on_reenable": False},
            "temporary_override": None,
            "mqtt": {"enabled": False},
            "plugins": {"auto_update": False, "transition_plugins_enabled": False},
        },
        "pages.json": {"schema_version": 6, "pages": []},
        "collections.json": {"schema_version": 1, "collections": []},
        "schedules.json": {"schema_version": 2, "schedules": [], "default_page_id": None, "default_page_by_board": {}},
        "panels.json": {"schema_version": 5, "panels": []},
        "auth.json": {"version": 1, "users": [], "auth_pref": "disabled", "session_registry_version": 1},
        ".system-update.json": {"schema_version": 1, "auto_update_interval": "manual", "auto_update_enabled": False},
    }


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _write_new(directory_fd: int, name: str, payload: bytes, mode: int) -> None:
    # Relative to an opened directory, with exclusive creation: no symlink or
    # existing file can redirect a write into an earlier campaign or user data.
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=directory_fd)
    with os.fdopen(fd, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def create_dataset(parent: Path, dataset_id: str, *, acknowledge_synthetic: bool) -> Path:
    """Reserve a new direct child and write seed inputs plus immutable hashes.

    ``parent`` must already exist at its canonical absolute path. An existing
    destination, even empty or a broken symlink, is always an error. On any
    partial failure leave the reserved directory intact and use a new ID;
    never clean up or repurpose a directory supplied by an operator.
    """
    if acknowledge_synthetic is not True:
        raise ValueError("Explicit synthetic-only acknowledgment is required.")
    if not isinstance(dataset_id, str) or not DATASET_PATTERN.fullmatch(dataset_id) or len(dataset_id) > 100:
        raise ValueError("dataset ID must be a direct child named prod-a11y-<lowercase letters, digits, hyphens>.")
    parent = Path(parent)
    if not parent.is_absolute():
        raise ValueError("The dataset parent must be an absolute existing directory.")
    canonical = parent.resolve(strict=True)
    if canonical != parent:
        raise ValueError("The dataset parent must be canonical, with no symlink or traversal components.")
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    parent_fd = os.open(parent, directory_flags)
    try:
        # mkdir is the atomic reservation; there is deliberately no exists()
        # check, exist_ok=True, overwrite flag or deletion fallback.
        os.mkdir(dataset_id, mode=0o700, dir_fd=parent_fd)
        dataset_fd = os.open(dataset_id, directory_flags, dir_fd=parent_fd)
        try:
            os.mkdir("data", mode=0o755, dir_fd=dataset_fd)
            data_fd = os.open("data", directory_flags, dir_fd=dataset_fd)
            files = {}
            try:
                for filename, document in _documents().items():
                    payload = _json_bytes(document)
                    _write_new(data_fd, filename, payload, 0o600 if filename == "auth.json" else 0o644)
                    files[filename] = {"sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}
            finally:
                os.close(data_fd)
            manifest = _json_bytes(
                {
                    "format_version": 1,
                    "synthetic_only": True,
                    "dataset_id": dataset_id,
                    "fixture": "configured-single-panel-empty-stores-auth-disabled",
                    "board_id": BOARD_ID,
                    "source_review": {"sha": SOURCE_SHA, "version": SOURCE_VERSION},
                    "boot_verified": False,
                    "files": files,
                    "limits": [
                        "Initial seed hashes only; boot mutates data. Mount only data/, not this manifest.",
                        "Operator must use a clean container environment and verify runtime preconditions.",
                        "No physical board connection; FiestaPanel renders in memory.",
                        "No backend network isolation; shell update discovery queries public metadata.",
                        "No runtime accessibility, source attestation or conformance result.",
                    ],
                }
            )
            _write_new(dataset_fd, "seed-manifest.json", manifest, 0o444)
            # Written last. Both files must exist and this digest must match
            # before the operator treats a partially created seed as complete.
            digest = (hashlib.sha256(manifest).hexdigest() + "\n").encode("ascii")
            _write_new(dataset_fd, "seed-manifest.sha256", digest, 0o444)
        finally:
            os.close(dataset_fd)
    finally:
        os.close(parent_fd)
    return parent / dataset_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", required=True, type=Path, help="Existing canonical absolute dataset parent")
    parser.add_argument("--dataset-id", required=True, help="Fresh prod-a11y-... direct-child name")
    parser.add_argument("--acknowledge-synthetic-only", action="store_true", required=True)
    args = parser.parse_args()
    dataset = create_dataset(args.parent, args.dataset_id, acknowledge_synthetic=args.acknowledge_synthetic_only)
    print(json.dumps({"dataset": str(dataset), "data": str(dataset / "data"), "boot_verified": False}))


if __name__ == "__main__":
    main()
