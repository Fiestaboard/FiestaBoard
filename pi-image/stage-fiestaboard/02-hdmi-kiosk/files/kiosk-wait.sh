#!/bin/bash
# Block until the FiestaBoard web server answers on localhost so the kiosk
# browser never opens onto a connection-refused page during boot. First
# boots pull Docker images and can legitimately take minutes; we wait up
# to 15, then let Chromium start anyway — the app's own boot splash and
# retry logic take over from there.
set -u

DEADLINE=$((SECONDS + 900))
until curl -fsS -o /dev/null --max-time 5 "http://localhost:4420/api/health"; do
    if [ "$SECONDS" -ge "$DEADLINE" ]; then
        echo "kiosk-wait: FiestaBoard not up after 15 min; starting browser anyway" >&2
        exit 0
    fi
    sleep 3
done
