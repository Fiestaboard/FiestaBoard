#!/bin/sh
# Vendor FiestaUI's LED data and golden fixtures into src/led/ and tests/fixtures/led/.
#
#   sh scripts/led_fixtures/vendor.sh /path/to/FiestaUI <commit>
#
# Local-only utility. It reads one commit of a FiestaUI clone with
# `git archive`, never its working tree, so an uncommitted edit cannot leak
# in. Files are copied byte for byte. Afterwards, update FIESTAUI_COMMIT and
# VENDORED_SHA256 in src/led/provenance.py with the hashes it prints;
# tests/test_led_parity.py fails until they agree.
set -eu

FIESTAUI=${1:?usage: vendor.sh /path/to/FiestaUI <commit>}
COMMIT=${2:?usage: vendor.sh /path/to/FiestaUI <commit>}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
FIX=scripts/ci/tests/fixtures
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

git -C "$FIESTAUI" archive "$COMMIT" "$FIX" | tar -x -C "$TMP"

mkdir -p "$ROOT/src/led" "$ROOT/tests/fixtures/led"
for f in led-fonts.json character-sets.json; do
  cp "$TMP/$FIX/$f" "$ROOT/src/led/$f"
done
for f in led-golden.json charset-golden.json device-models.json; do
  cp "$TMP/$FIX/$f" "$ROOT/tests/fixtures/led/$f"
done

echo "FiestaUI commit: $(git -C "$FIESTAUI" rev-parse "$COMMIT")"
cd "$ROOT"
shasum -a 256 src/led/led-fonts.json src/led/character-sets.json \
  tests/fixtures/led/led-golden.json tests/fixtures/led/charset-golden.json \
  tests/fixtures/led/device-models.json
