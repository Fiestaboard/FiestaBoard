#!/bin/sh
# Vendor FiestaUI's device data into src/fiestaui/ and its golden fixtures into
# tests/fixtures/fiestaui/.
#
#   sh scripts/fiestaui_fixtures/vendor.sh /path/to/FiestaUI <commit>
#
# Local-only utility. It reads one commit of a FiestaUI clone with
# `git archive`, never its working tree, so an uncommitted edit cannot leak
# in. Files are copied byte for byte. Afterwards, set "commit" and "files" in
# src/fiestaui/provenance.json from what it prints;
# tests/test_fiestaui_vendored.py fails until they agree.
set -eu

FIESTAUI=${1:?usage: vendor.sh /path/to/FiestaUI <commit>}
COMMIT=${2:?usage: vendor.sh /path/to/FiestaUI <commit>}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
FIX=scripts/ci/tests/fixtures
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

git -C "$FIESTAUI" archive "$COMMIT" "$FIX" | tar -x -C "$TMP"

# plugin-models.json is both: runtime data (FiestaPanel's own models, one per
# render style) and the golden fixture the manifest tests read.
DATA="device-model.schema.json character-set.schema.json character-sets.json device-models.json led-fonts.json plugin-models.json"
GOLDENS="charset-golden.json led-golden.json plugin-models.json"

mkdir -p "$ROOT/src/fiestaui" "$ROOT/tests/fixtures/fiestaui"
for f in $DATA; do
  cp "$TMP/$FIX/$f" "$ROOT/src/fiestaui/$f"
done
for f in $GOLDENS; do
  cp "$TMP/$FIX/$f" "$ROOT/tests/fixtures/fiestaui/$f"
done

echo "FiestaUI commit: $(git -C "$FIESTAUI" rev-parse "$COMMIT^{commit}")"
cd "$ROOT"
for f in $DATA; do shasum -a 256 "src/fiestaui/$f"; done
for f in $GOLDENS; do shasum -a 256 "tests/fixtures/fiestaui/$f"; done
