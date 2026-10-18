"""The tested runtime image must be loaded from this run and verified by ID."""

import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("image_id,load_status", [("sha256:expected", 0), ("sha256:wrong", 0), ("sha256:expected", 12)])
def test_image_load_rejects_failures_and_wrong_image(tmp_path, image_id, load_status):
    jobs = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]
    for job_name in ("e2e-tests", "specialized-e2e-tests"):
        step = next(s for s in jobs[job_name]["steps"] if s.get("name") == "Load and verify test image")
        docker = tmp_path / "docker"
        docker.write_text(
            "#!/bin/bash\nset -eu\n"
            f'if [ "$1" = load ]; then exit {load_status}; fi\n'
            '[ "$1 $2" = "image inspect" ] || exit 90\n'
            f'echo "{image_id}"\n'
        )
        docker.chmod(0o755)
        result = subprocess.run(
            ["bash", "-e", "-o", "pipefail", "-c", step["run"]],
            env={
                **os.environ,
                "PATH": f"{tmp_path}:{os.environ['PATH']}",
                "RUNNER_TEMP": str(tmp_path),
                "EXPECTED_IMAGE_ID": "sha256:expected",
            },
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert (result.returncode == 0) == (load_status == 0 and image_id == "sha256:expected")


def test_consumers_download_this_runs_artifact_and_verify_producer_identity():
    jobs = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]
    producer = jobs["build-test-image"]
    assert producer["outputs"]["image_id"] == "${{ steps.build.outputs.imageid }}"
    upload = next(s for s in producer["steps"] if s.get("uses", "").startswith("actions/upload-artifact"))
    for job_name in ("e2e-tests", "specialized-e2e-tests"):
        job = jobs[job_name]
        assert "build-test-image" in job["needs"]
        download = next(s for s in job["steps"] if s.get("uses", "").startswith("actions/download-artifact"))
        assert download["with"]["name"] == upload["with"]["name"]
        assert "run-id" not in download["with"]
        verify = next(s for s in job["steps"] if s.get("name") == "Load and verify test image")
        assert verify["env"]["EXPECTED_IMAGE_ID"] == "${{ needs.build-test-image.outputs.image_id }}"
