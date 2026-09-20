"""The Pi host must announce the HTTP endpoint used by Bonjour clients."""

from pathlib import Path
from xml.etree import ElementTree

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
