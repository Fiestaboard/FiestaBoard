#!/bin/sh
# Regenerate tests/fixtures/markup/fiestaui_parse_line.json (parity fixtures)
# and src/markup_icons.json (the vendored icon table) from a FiestaUI
# checkout, by running FiestaUI's real TypeScript parser.
#
# Utility script marked for local execution: it only reads git metadata on the
# host and runs everything else in a throwaway node:24-alpine container.
#
#   sh scripts/markup_fixtures/generate.sh [path-to-FiestaUI]   (default ../FiestaUI)
#   FIESTAUI_NOTE="..." sh scripts/markup_fixtures/generate.sh   (annotate provenance)
#
# Generate from a merged FiestaUI commit. A dirty working tree is recorded as
# `"dirty": true` in the fixture header, and the commit SHA alone then does not
# identify the parser that produced the fixtures.
#
# The FiestaUI checkout is mounted READ-ONLY and copied (without node_modules
# or .git) into the container before `npm ci`, so the checkout is never
# touched. FiestaUI's dependencies install anonymously from npmjs.
set -eu

#
# To pin an exact commit without touching a checkout, export it and pass the
# export with its provenance:
#   git -C ../FiestaUI archive <sha> | tar -x -C /tmp/fiestaui-<sha>
#   FIESTAUI_COMMIT=<full sha> FIESTAUI_BRANCH=<branch> \
#     FIXTURE_NAME=fiestaui_base_grammar.json WRITE_ICONS=false \
#     sh scripts/markup_fixtures/generate.sh /tmp/fiestaui-<sha>
#
# FIXTURE_NAME (default fiestaui_parse_line.json) names the fixture file;
# WRITE_ICONS=false leaves src/markup_icons.json alone.

REPO_ROOT=$(cd "$(dirname "$0")/../.." && pwd)
FIESTAUI=$(cd "${1:-$REPO_ROOT/../FiestaUI}" && pwd)
OUT_DIR="$REPO_ROOT/tests/fixtures/markup"
FIXTURE_NAME="${FIXTURE_NAME:-fiestaui_parse_line.json}"
mkdir -p "$OUT_DIR"

if [ -n "${FIESTAUI_COMMIT:-}" ]; then
  # An exported tree: the caller states the provenance, and it is clean by construction.
  BRANCH="${FIESTAUI_BRANCH:-unknown}"
  COMMIT="$FIESTAUI_COMMIT"
  DIRTY=false
else
  # --no-optional-locks: `git status` must not refresh the other checkout's index.
  BRANCH=$(git -C "$FIESTAUI" rev-parse --abbrev-ref HEAD)
  COMMIT=$(git -C "$FIESTAUI" rev-parse HEAD)
  if [ -n "$(git -C "$FIESTAUI" --no-optional-locks status --porcelain -- src/lib)" ]; then
    DIRTY=true
  else
    DIRTY=false
  fi
fi

ICONS_ARG=/out-src/markup_icons.json
if [ "${WRITE_ICONS:-true}" = false ]; then
  ICONS_ARG=
fi

docker run --rm \
  -e FIESTAUI_BRANCH="$BRANCH" \
  -e FIESTAUI_COMMIT="$COMMIT" \
  -e FIESTAUI_DIRTY="$DIRTY" \
  -e FIESTAUI_NOTE="${FIESTAUI_NOTE:-}" \
  -e FIXTURE_NAME="$FIXTURE_NAME" \
  -e ICONS_ARG="$ICONS_ARG" \
  -v "$FIESTAUI":/fiestaui-src:ro \
  -v "$REPO_ROOT/scripts/markup_fixtures":/gen:ro \
  -v "$OUT_DIR":/out \
  -v "$REPO_ROOT/src":/out-src \
  node:24-alpine sh -c '
    set -e
    mkdir /work
    tar -C /fiestaui-src --exclude=./node_modules --exclude=./.git -cf - . | tar -C /work -xf -
    cd /work
    npm ci --ignore-scripts --no-audit --no-fund --loglevel=error
    node /gen/generate.mjs /work "/out/$FIXTURE_NAME" $ICONS_ARG
  '
