"""nginx must not rewrite application-generated gateway errors.

The `@api_starting` fallback exists for one window only: nginx is listening but
the API process is not yet bound to 127.0.0.1:8000, so nginx *itself* generates
a 502/504 and we serve a friendly "starting up" JSON instead of a raw gateway
error.

`proxy_intercept_errors on` widens that from "errors nginx generated" to "any
response with status >= 300", which swallowed the 502/504 responses FastAPI
returns deliberately (a plugin options provider that raised or timed out, a
failed system update, a dead generic-data URL) and rewrote every one of them
into the boot-race 503 — real status gone, JSON `detail` gone.

These tests pin the two halves of that contract in all three configs.
"""

from pathlib import Path

import pytest

CONFIGS = ("nginx.conf", "nginx.https.conf", "nginx-dev.conf")

REPO_ROOT = Path(__file__).resolve().parent.parent


def _read(name: str) -> str:
    return (REPO_ROOT / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("config_name", CONFIGS)
def test_upstream_responses_are_not_intercepted(config_name: str) -> None:
    """App-returned 502/504 must reach the client, so interception stays off."""
    directives = [
        line.strip() for line in _read(config_name).splitlines() if line.strip().startswith("proxy_intercept_errors")
    ]

    assert directives == ["proxy_intercept_errors off;"], (
        f"{config_name} must declare `proxy_intercept_errors off;` exactly once. "
        "Turning it on makes error_page swallow the 502/504 the API returns itself."
    )


@pytest.mark.parametrize("config_name", CONFIGS)
def test_boot_race_still_falls_back_to_the_starting_response(config_name: str) -> None:
    """nginx-generated 502/504 on /api must still produce the JSON boot-race body."""
    text = _read(config_name)

    assert text.count("error_page 502 504 = @api_starting;") == 2, (
        f"{config_name} must keep the @api_starting fallback on both /api locations "
        "(/api/mcp and /api/) so a not-yet-listening upstream stays friendly."
    )
    assert '"detail":"Service is starting up, please try again shortly"' in text
    assert "location @api_starting {" in text
