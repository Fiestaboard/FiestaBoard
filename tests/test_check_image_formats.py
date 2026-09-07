"""The gate that keeps ``image-size``'s unpatchable DoS parsers unreachable.

``scripts/check_image_formats.py`` refuses to let ICNS, HEIF or JXL files into
the repo, because ``@docusaurus/mdx-loader`` hands every Markdown-referenced
image to ``image-size``, whose ICNS/JXL/HEIF parsers hang the Node event loop
forever on crafted input and will never be patched (see issue #1578).

``image-size`` dispatches on magic bytes, not on file extension, so the two
things worth guarding are that the checker matches on content the same way
``image-size``'s own ``validate()`` does, and that it does not fire on the
formats the repo actually uses -- including ISO-BMFF containers such as MP4,
which share HEIF's ``ftyp`` header and differ only by brand.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_image_formats import (
    MAX_BOXES,
    _walk_boxes,
    detect_blocked_format,
    scan_paths,
)

REPO_ROOT = Path(__file__).parent.parent

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
GIF = b"GIF89a" + b"\x00" * 64
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'


def _ftyp(brand: bytes, *, size: int = 32) -> bytes:
    """An ISO-BMFF file whose first box is ``ftyp`` carrying ``brand``."""
    box = size.to_bytes(4, "big") + b"ftyp" + brand + b"\x00" * 4
    return box.ljust(size, b"\x00")


def _jxl_container() -> bytes:
    """The JXL box format: a 12-byte ``JXL `` signature, then ``ftyp jxl ``."""
    signature = (12).to_bytes(4, "big") + b"JXL " + b"\x0d\x0a\x87\x0a"
    ftyp = (20).to_bytes(4, "big") + b"ftyp" + b"jxl " + b"\x00" * 8
    return signature + ftyp


class TestBlockedFormatsAreDetected:
    def test_icns_magic_is_blocked(self):
        assert detect_blocked_format(b"icns" + b"\x00" * 64) == "ICNS"

    def test_naked_jxl_codestream_is_blocked(self):
        assert detect_blocked_format(b"\xff\x0a" + b"\x00" * 64) == "JXL"

    def test_jxl_container_is_blocked(self):
        assert detect_blocked_format(_jxl_container()) == "JXL"

    def test_zero_sized_signature_box_does_not_hide_the_jxl_brand(self):
        """A box declaring size 0 -- the shape both advisories turn on.

        ``image-size``'s ``findBox`` advances by 8 rather than by the declared
        0, so an attacker who declares 0 and puts a valid ``ftyp`` at offset 8
        still gets the file routed to the JXL parser. Trusting the declared
        size instead would walk in place and let that payload past the gate.
        """
        payload = (0).to_bytes(4, "big") + b"JXL " + (20).to_bytes(4, "big") + b"ftyp" + b"jxl " + b"\x00" * 32

        assert detect_blocked_format(payload) == "JXL"

    @pytest.mark.parametrize("brand", [b"avif", b"mif1", b"msf1", b"heic", b"heix", b"hevc", b"hevx"])
    def test_every_heif_brand_image_size_recognises_is_blocked(self, brand):
        assert detect_blocked_format(_ftyp(brand)) == "HEIF"


class TestSupportedFormatsAreNotBlocked:
    @pytest.mark.parametrize("data", [PNG, JPEG, GIF, SVG], ids=["png", "jpeg", "gif", "svg"])
    def test_formats_the_docs_actually_use_pass(self, data):
        assert detect_blocked_format(data) is None

    @pytest.mark.parametrize("brand", [b"isom", b"mp42", b"qt  "], ids=["mp4", "mp4v2", "mov"])
    def test_iso_bmff_video_shares_the_ftyp_header_but_is_not_blocked(self, brand):
        """MP4/MOV also start with an ``ftyp`` box; only the brand separates them."""
        assert detect_blocked_format(_ftyp(brand)) is None

    def test_empty_file_is_not_blocked(self):
        assert detect_blocked_format(b"") is None

    def test_file_shorter_than_the_magic_bytes_does_not_crash(self):
        assert detect_blocked_format(b"ic") is None

    def test_zero_sized_boxes_without_a_known_brand_are_not_blocked(self):
        payload = (0).to_bytes(4, "big") + b"free" + b"\x00" * 256
        assert detect_blocked_format(payload) is None


class TestBoxWalkerIsBounded:
    def test_walker_stops_after_max_boxes(self):
        """Unbounded, this walker would be the very bug it is guarding against."""
        pathological = ((0).to_bytes(4, "big") + b"free") * 512

        assert len(list(_walk_boxes(pathological))) == MAX_BOXES


class TestScanPaths:
    def test_offending_file_is_reported_with_its_format(self, tmp_path):
        bad = tmp_path / "logo.png"  # extension lies; content is what matters
        bad.write_bytes(b"icns" + b"\x00" * 64)

        assert scan_paths([bad]) == [(bad, "ICNS")]

    def test_clean_file_produces_no_findings(self, tmp_path):
        good = tmp_path / "logo.png"
        good.write_bytes(PNG)

        assert scan_paths([good]) == []

    def test_unreadable_path_is_skipped_rather_than_raising(self, tmp_path):
        assert scan_paths([tmp_path / "does-not-exist.png"]) == []

    def test_directories_are_skipped(self, tmp_path):
        assert scan_paths([tmp_path]) == []


class TestRepositoryIsClean:
    def test_no_tracked_file_in_this_repo_reaches_a_vulnerable_parser(self):
        """The check the CI job runs. Failing here means a bad image landed."""
        result = subprocess.run(
            [sys.executable, "scripts/check_image_formats.py"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stdout + result.stderr
