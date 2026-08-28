"""Drift guard: the HDMI retrofit script must match the image stage.

New FiestaPi images install the kiosk from
pi-image/stage-fiestaboard/02-hdmi-kiosk/files/; already-deployed Pis get
the identical pieces from scripts/fiestapi-hdmi-setup.sh, which embeds
them as heredocs. If either side changes without the other, deployed
fleets and fresh flashes silently diverge — this test pins them together.
"""

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "scripts" / "fiestapi-hdmi-setup.sh"
STAGE = ROOT / "pi-image" / "stage-fiestaboard" / "02-hdmi-kiosk" / "files"


def _heredoc(marker: str) -> str:
    """Extract the body of a <<'MARKER' … MARKER heredoc from the script."""
    text = SCRIPT.read_text()
    match = re.search(rf"<<'{marker}'\n(.*?)\n{marker}\n", text, re.DOTALL)
    assert match, f"heredoc {marker} not found in {SCRIPT}"
    return match.group(1) + "\n"


def test_unit_file_matches_image_stage():
    expected = (STAGE / "fiestapi-kiosk.service").read_text()
    assert _heredoc("UNIT_EOF") == expected


def test_wait_script_matches_image_stage():
    expected = (STAGE / "kiosk-wait.sh").read_text()
    assert _heredoc("WAIT_EOF") == expected
