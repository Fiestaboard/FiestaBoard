# V10 Divoom Release QA

Use one candidate image and record its digest, core commit, installed Divoom commit, Pi model/OS, Pixoo firmware and browser URL form throughout this pass. Run against a test installation or backed-up data. Keep physical results separate from loopback tests.

## Release Gates

- Build and digest-verify the seed from `outputs.lock.json`. The Divoom cancellation fix is merged at `863ab740a23db02e4274e52f23a3b0a815c4526e`; the previous pin `3819a91` fails current core's cancellation conformance check.
- Run all three bundled output packages' tests against the candidate core, including Divoom's strict conformance suite. CI's Platform Tests step owns this gate.
- Verify a fresh offline Divoom install gets the pinned commit. On an existing beta installation, verify that the old installed copy survives an image upgrade, then apply its plugin update explicitly through Integrations and verify the running commit. Both plugin commits declare `0.6.0`.
- Restart the app and make `POST /outputs/divoom_pixoo/install` the first plugin request. It must return 200 for the existing installation without a preliminary output-list request or copying over the installed files.
- Upgrade a representative v9 installation and verify pages, schedules, display settings and authentication persist. Verify fresh setup separately.
- Run the physical checks below against the resulting packaged image. Automated conformance does not establish firmware behavior, visual smoothness or network reachability.

## Physical Display Checks

1. Complete setup, send a distinctive text-and-color page, and compare the physical display with the preview.
2. Send A, fade to B, then immediately send A again. Repeat while saving a change to the display's settings during a fade. The latest requested page must appear and brightness must recover without manual repair.
3. Briefly disconnect and reconnect the Pixoo. Send again and verify recovery and brightness.
4. Verify a scheduled page change, silence blocking, an explicit force send, and pause/resume.
5. Restart FiestaBoard and verify pages, schedules, settings and plugin identity persist, then send again.

## Discovery Report #2339

The report includes a scan of a container subnet and a failed explicit-address scan. These are separate observations. The second has no confirmed cause yet. Do not close [#2339](https://github.com/Fiestaboard/FiestaBoard/issues/2339) as fixed or user error based only on loopback tests or a successful cloud lookup.

1. Record the network reported by **Find my Pixoo** when accessing FiestaBoard by LAN IP and by hostname.
2. Try the explicit Pixoo address in **Network to search** and record the result.
3. Separately complete **Enter address manually**, **Test connection**, save, and send a page. A `/32` discovery scan is not the manual setup path.
4. From inside the affected FiestaBoard container, run the read-only probe below with the real Pixoo address. Compare its method, command, HTTP status, timing and JSON shape with the successful Postman request.

Replace the example address and, if needed, the Compose service name. This reads configuration; it does not send a picture or change brightness. It prints only known configuration fields and the returned field names. Review the output before sharing; do not post addresses, MACs or credentials.

```bash
docker compose exec -T fiestaboard python - <<'PY'
import json
import time

import requests

address = "192.168.1.100"  # Replace with the Pixoo's address.
started = time.monotonic()
try:
    reply = requests.post(
        f"http://{address}:80/post",
        json={"Command": "Channel/GetAllConf"},
        timeout=(3, 5),
    )
    print("HTTP", reply.status_code, "seconds", round(time.monotonic() - started, 3))
    try:
        body = reply.json()
    except ValueError:
        print("Response was not JSON")
    else:
        print("JSON type:", type(body).__name__)
        if isinstance(body, dict):
            print("Fields:", sorted(body))
            allowed = ("error_code", "Brightness", "LightSwitch", "RotationFlag", "CurClockId")
            print(json.dumps({key: body[key] for key in allowed if key in body}))
except requests.RequestException as exc:
    print(type(exc).__name__, "after", round(time.monotonic() - started, 3), "seconds")
PY
```

The probe above uses the manual test's longer timeouts. Discovery uses a 0.8-second connect/read timeout and requires HTTP 200, `error_code: 0`, and at least one recognized configuration field. A slow reply or a minimal JSON success response can therefore distinguish discovery from manual testing; neither has been established on the reporter's device. The direct probe tests container reachability and bypasses the plugin's optional host allowlist, so also record whether `FIESTABOARD_OUTPUTS_ALLOW_HOSTS` is configured, with private values redacted.

Ping and Divoom cloud lookup do not verify this HTTP exchange. Normal Docker bridge networking supports outbound routed/masqueraded connections; bridge mode alone does not prove the LAN device is unreachable. Do not change network mode, weaken device identification or lengthen discovery timeouts without evidence from the affected setup.

## Evidence to Retain

Record pass/fail and logs for each release gate, the exact commits and image digest, and any pending hardware checks in the PR. Keep the discovery report open until its explicit-address failure is explained or reproduced and fixed. A successful source test or local image with replaced seed files is not proof that the published release contains those files.
