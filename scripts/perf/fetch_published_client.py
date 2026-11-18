#!/usr/bin/env python3
"""Copy the served web client out of a published image, read-only.

Uses only the Python standard library and the public Docker Registry HTTP API.
It never pulls the image into Docker, never runs image content, and never calls
``tarfile.extractall``. Every downloaded layer is checked against its manifest
digest and size and against the config's uncompressed diff ID before any file is
read. Only regular files under ``app/web/build/client`` are copied, replayed in
manifest layer order. Links, devices or a whiteout that touches the client tree
stop the run instead of producing a partial tree.

Example (the re-baseline procedure in docs/internal/development/PERFORMANCE.md):

    python3 scripts/perf/fetch_published_client.py \
        --tag v11-alpha-11.0.0-alpha.10 --out /path/to/scratch/alpha10
"""

from __future__ import annotations

import argparse
import datetime
import gzip
import hashlib
import json
import sys
import tarfile
import urllib.request
from pathlib import Path, PurePosixPath

REPOSITORY = "fiestaboard/fiestaboard"
PREFIX = PurePosixPath("app/web/build/client")
INDEX_TYPES = (
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
)
MANIFEST_TYPES = (
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
)


def _touches_client(name: PurePosixPath) -> bool:
    return name == PREFIX or PREFIX in name.parents or name in PREFIX.parents


def replay_layer(archive: tarfile.TarFile, dest: Path) -> list[dict]:
    """Apply one layer's client entries to ``dest``; fail closed on anything unsafe."""
    affected = []
    for member in archive:
        name = PurePosixPath(member.name.removeprefix("./"))
        if name.is_absolute() or ".." in name.parts:
            raise ValueError(f"Unsafe layer path: {member.name}")
        if name.name.startswith(".wh."):
            # Covers plain and opaque (.wh..wh..opq) whiteouts alike.
            target = name.parent / name.name.removeprefix(".wh.")
            if _touches_client(target) or _touches_client(name.parent):
                raise ValueError(f"Whiteout touches the client tree: {member.name}")
            continue
        if not _touches_client(name) or member.isdir():
            continue
        if not member.isfile():
            raise ValueError(f"Non-regular client entry: {member.name}")
        relative = name.relative_to(PREFIX)
        source = archive.extractfile(member)
        if source is None:
            raise ValueError(f"Unreadable client entry: {member.name}")
        data = source.read()
        target_path = dest / relative
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(data)
        affected.append({"path": str(relative), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    return affected


def _get(url: str, token: str, accept: tuple[str, ...] = ()) -> tuple[bytes, str]:
    headers = {"Authorization": "Bearer " + token}
    if accept:
        headers["Accept"] = ", ".join(accept)
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
        return response.read(), response.headers.get("Content-Type", "")


def fetch(tag: str, platform: str, out: Path) -> dict:
    os_name, arch = platform.split("/", 1)
    token = json.load(
        urllib.request.urlopen(
            "https://auth.docker.io/token?service=registry.docker.io&scope=repository:" + REPOSITORY + ":pull",
            timeout=60,
        )
    )["token"]
    base = "https://registry-1.docker.io/v2/" + REPOSITORY
    index_raw, index_type = _get(f"{base}/manifests/{tag}", token, INDEX_TYPES + MANIFEST_TYPES)
    index_digest = "sha256:" + hashlib.sha256(index_raw).hexdigest()
    index = json.loads(index_raw)
    if index_type.split(";")[0] in INDEX_TYPES or "manifests" in index:
        matches = [
            entry
            for entry in index["manifests"]
            if entry.get("platform", {}).get("os") == os_name and entry.get("platform", {}).get("architecture") == arch
        ]
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one {platform} manifest in {tag}, found {len(matches)}")
        manifest_digest = matches[0]["digest"]
        manifest_raw, _ = _get(f"{base}/manifests/{manifest_digest}", token, MANIFEST_TYPES)
        if "sha256:" + hashlib.sha256(manifest_raw).hexdigest() != manifest_digest:
            raise ValueError("Manifest digest mismatch")
    else:
        manifest_digest, manifest_raw = index_digest, index_raw
    manifest = json.loads(manifest_raw)
    config_digest = manifest["config"]["digest"]
    config_raw, _ = _get(f"{base}/blobs/{config_digest}", token)
    if "sha256:" + hashlib.sha256(config_raw).hexdigest() != config_digest:
        raise ValueError("Config digest mismatch")
    config = json.loads(config_raw)
    diff_ids = config["rootfs"]["diff_ids"]
    layers = manifest["layers"]
    if len(diff_ids) != len(layers):
        raise ValueError("Layer count does not match diff IDs")

    client = out / "client"
    if client.exists():
        raise ValueError(f"{client} already exists; use an empty output directory")
    client.mkdir(parents=True)
    blobs = out / "layers"
    blobs.mkdir(exist_ok=True)
    records = []
    for position, layer in enumerate(layers):
        digest = layer["digest"]
        path = blobs / (digest.split(":")[1] + ".tar.gz")
        request = urllib.request.Request(f"{base}/blobs/{digest}", headers={"Authorization": "Bearer " + token})
        hasher = hashlib.sha256()
        size = 0
        with urllib.request.urlopen(request, timeout=120) as response, path.open("wb") as handle:
            while chunk := response.read(1024 * 1024):
                hasher.update(chunk)
                size += len(chunk)
                handle.write(chunk)
        if size != layer["size"] or "sha256:" + hasher.hexdigest() != digest:
            raise ValueError(f"Layer {position} failed its compressed digest/size check")
        uncompressed = hashlib.sha256()
        with gzip.open(path, "rb") as stream:
            while chunk := stream.read(1024 * 1024):
                uncompressed.update(chunk)
        if "sha256:" + uncompressed.hexdigest() != diff_ids[position]:
            raise ValueError(f"Layer {position} failed its diff ID check")
        with tarfile.open(path, "r:gz") as archive:
            affected = replay_layer(archive, client)
        records.append({"index": position, "digest": digest, "size": size, "client_files": len(affected)})
        path.unlink()  # Keep only verified client bytes on disk.
    env = dict(item.split("=", 1) for item in config.get("config", {}).get("Env", []) if "=" in item)
    provenance = {
        "repository": REPOSITORY,
        "tag": tag,
        "platform": platform,
        "index_digest": index_digest,
        "manifest_digest": manifest_digest,
        "config_digest": config_digest,
        "version_env": env.get("VERSION"),
        "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "method": "Registry HTTP API; digests and diff IDs verified; client files replayed in layer order; "
        "client-tree whiteouts and non-regular entries fail closed; image never executed.",
        "layers": records,
    }
    (out / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    return provenance


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tag", required=True, help="Immutable published tag, e.g. v11-alpha-11.0.0-alpha.10")
    parser.add_argument("--platform", default="linux/amd64")
    parser.add_argument("--out", type=Path, required=True, help="Empty scratch directory")
    args = parser.parse_args()
    try:
        provenance = fetch(args.tag, args.platform, args.out)
    except (ValueError, OSError, KeyError, tarfile.TarError) as exc:
        print(f"Fetch error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({key: provenance[key] for key in ("tag", "manifest_digest", "version_env")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
