"""The Pi host must announce the HTTP endpoint used by Bonjour clients."""

import os
import subprocess
from pathlib import Path
from xml.etree import ElementTree

import pytest

PI_INSTALL = Path(__file__).resolve().parents[1] / "pi-image/stage-fiestaboard/01-install-fiestaboard"


def test_pi_image_advertises_fiestaboard_http_service_on_host():
    service_path = PI_INSTALL / "files/fiestaboard-http.service"
    service = ElementTree.parse(service_path).getroot().find("service")

    assert service.findtext("type") == "_http._tcp"
    assert service.findtext("port") == "4420"
    assert {record.text for record in service.findall("txt-record")} >= {
        "product=FiestaBoard",
        "path=/",
    }

    installer = (PI_INSTALL / "00-run.sh").read_text()
    assert "files/fiestaboard-http.service" in installer
    assert "etc/avahi/services/fiestaboard-http.service" in installer
    assert "avahi-daemon" in (PI_INSTALL / "00-packages").read_text()
    assert "systemctl enable avahi-daemon.service" in installer


def test_pi_image_restarts_avahi_after_a_crash():
    drop_in = PI_INSTALL / "files/avahi-daemon-restart.conf"
    settings = drop_in.read_text()
    installer = (PI_INSTALL / "00-run.sh").read_text()

    assert "[Service]" in settings
    assert "Restart=on-failure" in settings
    assert "RestartSec=5s" in settings
    assert "etc/systemd/system/avahi-daemon.service.d" in installer
    assert "files/avahi-daemon-restart.conf" in installer


def test_pi_image_checks_avahi_health_every_five_minutes():
    timer = (PI_INSTALL / "files/fiestapi-heal-mdns.timer").read_text()
    assert "OnUnitActiveSec=5min" in timer


@pytest.mark.parametrize(
    ("response", "dbus_exit_code", "expected_restart"),
    [
        ("fiestapi.local", 0, False),
        ("fiestapi-2.local", 0, True),
        ("", 0, True),
        ("", 1, True),
        ("fiestapi.local", 1, True),
    ],
)
def test_mdns_healer_restarts_only_when_unhealthy(
    tmp_path, response, dbus_exit_code, expected_restart
):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "hostname").write_text("#!/bin/sh\necho fiestapi\n")
    (fake_bin / "dbus-send").write_text(
        "#!/bin/sh\nprintf '   string \"%s\"\\n' \"$FAKE_AVAHI_FQDN\"\n"
        "exit \"$FAKE_DBUS_EXIT_CODE\"\n"
    )
    (fake_bin / "systemctl").write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$FAKE_SYSTEMCTL_LOG\"\n"
    )
    (fake_bin / "logger").write_text("#!/bin/sh\nexit 0\n")
    for command in fake_bin.iterdir():
        command.chmod(0o755)

    systemctl_log = tmp_path / "systemctl.log"
    result = subprocess.run(
        ["bash", str(PI_INSTALL / "files/heal-mdns.sh")],
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "FAKE_AVAHI_FQDN": response,
            "FAKE_DBUS_EXIT_CODE": str(dbus_exit_code),
            "FAKE_SYSTEMCTL_LOG": str(systemctl_log),
        },
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert systemctl_log.exists() is expected_restart
    if expected_restart:
        assert systemctl_log.read_text() == "restart avahi-daemon\n"
