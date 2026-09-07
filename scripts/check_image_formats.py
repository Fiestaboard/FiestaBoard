#!/usr/bin/env python3
"""Refuse image formats that reach ``image-size``'s unpatchable DoS parsers.

The docs site builds with Docusaurus, and ``@docusaurus/mdx-loader`` hands
every Markdown-referenced image to ``image-size`` at build time::

    const size = await imageSizeFromFile(imagePath)

Two high-severity advisories against ``image-size`` have no patched version,
and never will: the project was archived on 2026-06-03 with ``2.0.2`` -- the
affected release -- as its last.

  GHSA-w3rx-r6r6-pgpr  ICNS parser hangs on a zero-valued entry-length field
  GHSA-5p2g-fcmc-qvqq  JXL and HEIF parsers hang on a zero-sized box

Both are infinite loops that block the Node event loop permanently, so a
single crafted image committed here would wedge the docs build forever rather
than fail it. Exposure is build-time only -- the deployed site is static HTML
and ``image-size`` never sees runtime input -- so the realistic threat is a
malicious image reaching the repo. Those three parsers are the only way in,
which makes refusing their formats at the gate a complete mitigation for the
path we actually have. Tracked as issue #1578; drop this once Docusaurus ships
facebook/docusaurus#12235, which replaces the dependency outright.

``image-size`` dispatches on magic bytes and ignores file extensions, so this
matches on content exactly the way its own ``validate()`` functions do -- a
crafted ICNS renamed to ``.png`` is still parsed as ICNS.

Usage::

    python scripts/check_image_formats.py            # every tracked file
    python scripts/check_image_formats.py a.png b.icns
"""

import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

# `brandMap` in image-size's lib/types/heif.ts. A file is only routed to the
# HEIF parser when its `ftyp` brand is one of these, which is what keeps MP4
# and MOV -- same `ftyp` header, different brand -- out of scope.
HEIF_BRANDS = frozenset({b"avif", b"mif1", b"msf1", b"heic", b"heix", b"hevc", b"hevx"})

# Enough to cover the `ftyp` box, which is the first or second box in every
# ISO-BMFF variant. Nothing here needs the rest of the file.
HEAD_BYTES = 4096

# A malformed file can declare boxes that advance the offset by the 8-byte
# minimum forever; image-size's own walker is what the advisory is about, so
# this one is explicitly bounded.
MAX_BOXES = 32


def _walk_boxes(data: bytes) -> Iterable[tuple[bytes, int, int]]:
    """Yield ``(name, offset, size)`` for each ISO-BMFF box in ``data``.

    Mirrors ``findBox`` in image-size, including its ``size > 0 ? size : 8``
    fallback, so that this agrees with the parser it is protecting.
    """
    offset = 0
    for _ in range(MAX_BOXES):
        if offset < 0 or offset + 8 > len(data):
            return
        size = int.from_bytes(data[offset : offset + 4], "big")
        name = data[offset + 4 : offset + 8]
        yield name, offset, size
        offset += size if size > 0 else 8


def _ftyp_brand(data: bytes) -> bytes | None:
    """The brand of the first ``ftyp`` box, or ``None`` if there isn't one."""
    for name, offset, _size in _walk_boxes(data):
        if name == b"ftyp":
            brand = data[offset + 8 : offset + 12]
            return brand if len(brand) == 4 else None
    return None


def detect_blocked_format(data: bytes) -> str | None:
    """Return the vulnerable parser ``data`` would reach, or ``None``.

    ``data`` may be a truncated head of the file; only the first few bytes
    matter to any of these checks.
    """
    # ICNS: toUTF8String(input, 0, 4) === "icns"
    if data[:4] == b"icns":
        return "ICNS"

    # JXL, naked codestream: toHexString(input, 0, 2) === "ff0a"
    if data[:2] == b"\xff\x0a":
        return "JXL"

    # JXL, container: a "JXL " box, then an ftyp box branded "jxl "
    if data[4:8] == b"JXL " and _ftyp_brand(data) == b"jxl ":
        return "JXL"

    # HEIF (and AVIF): an ftyp box whose brand is in image-size's brandMap
    if data[4:8] == b"ftyp" and _ftyp_brand(data) in HEIF_BRANDS:
        return "HEIF"

    return None


def scan_paths(paths: Iterable[Path]) -> list[tuple[Path, str]]:
    """Return ``(path, format)`` for every path that would hit a bad parser.

    Paths that are missing, unreadable, or directories are skipped -- this is
    a content check, not a filesystem audit.
    """
    findings: list[tuple[Path, str]] = []
    for path in paths:
        try:
            with open(path, "rb") as fh:
                head = fh.read(HEAD_BYTES)
        except (OSError, ValueError):
            continue

        blocked = detect_blocked_format(head)
        if blocked:
            findings.append((path, blocked))
    return findings


def tracked_files(root: Path) -> list[Path]:
    """Every file git tracks under ``root``."""
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        capture_output=True,
        check=True,
    )
    return [root / name.decode() for name in result.stdout.split(b"\0") if name]


def main(argv: list[str]) -> int:
    root = Path(__file__).parent.parent
    paths = [Path(a) for a in argv] if argv else tracked_files(root)

    findings = scan_paths(paths)
    if not findings:
        print(f"OK: no ICNS/HEIF/JXL content in {len(paths)} files checked.")
        return 0

    for path, blocked in findings:
        try:
            shown = path.relative_to(root)
        except ValueError:
            shown = path
        print(
            f"::error file={shown}::{shown} is {blocked} content, which "
            f"@docusaurus/mdx-loader parses with image-size -- a parser with "
            f"two unpatchable infinite-loop advisories "
            f"(GHSA-w3rx-r6r6-pgpr, GHSA-5p2g-fcmc-qvqq) that would hang the "
            f"docs build. Convert it to PNG, JPEG, WebP or SVG. See issue "
            f"#1578."
        )

    print(
        f"\nFAIL: {len(findings)} file(s) use an image format that reaches an unpatched image-size parser.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
