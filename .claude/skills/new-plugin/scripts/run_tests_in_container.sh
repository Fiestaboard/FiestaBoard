#!/usr/bin/env bash
# Run a standalone plugin's tests inside the running FiestaBoard dev container,
# which already has the core + all dependencies installed. This is the faithful
# local mirror of the plugin repo's GitHub Actions CI (same symlink scaffold,
# same PYTHONPATH, same pytest invocation) — and it honors the repo rule that
# Python deps live in Docker, never on the host.
#
# Usage:
#   run_tests_in_container.sh <plugin-dir> [<fiestaboard-repo-dir>]
#
#   <plugin-dir>            the standalone plugin repo to test (e.g. ../fiestaboard-plugin--tide-times)
#   <fiestaboard-repo-dir>  optional; only used as a last-resort way to find the container
#
# Robust to compose project drift: it talks to the container BY NAME via plain
# `docker exec` / `docker cp` rather than `docker compose`, because a restarted
# container can stop matching `docker compose` from a different working dir.
# It also self-heals a container that has lost pytest (can happen after a rebuild).
#
# Requires the dev container to be up: `/start` or
#   docker compose -f docker-compose.dev.yml up -d
set -euo pipefail

PLUGIN_DIR="${1:?usage: run_tests_in_container.sh <plugin-dir> [<fiestaboard-repo-dir>]}"
PLUGIN_DIR="$(cd "$PLUGIN_DIR" && pwd)"

# --- Find the running dev container by name (not via compose) ----------------
find_container() {
  # Prefer the canonical name, then any fiestaboard container that isn't a
  # web/mock/storybook sidecar.
  local names
  names="$(docker ps --format '{{.Names}}' 2>/dev/null || true)"
  if printf '%s\n' "$names" | grep -qx 'fiestaboard-dev'; then
    echo 'fiestaboard-dev'; return 0
  fi
  printf '%s\n' "$names" \
    | grep -i 'fiestaboard' \
    | grep -viE 'web|mock|storybook' \
    | head -n1
}
CONTAINER="$(find_container)"
if [ -z "$CONTAINER" ]; then
  echo "No running FiestaBoard dev container found. Start it with /start (or" >&2
  echo "  docker compose -f docker-compose.dev.yml up -d) and retry." >&2
  exit 1
fi

PLUGIN_ID="$(python3 -c "import json;print(json.load(open('$PLUGIN_DIR/manifest.json'))['id'])")"
DEST="/tmp/plugin-test-$(basename "$PLUGIN_DIR")"

echo "Plugin:    $PLUGIN_DIR (id: $PLUGIN_ID)"
echo "Container: $CONTAINER (core at /app)"

# --- Ensure pytest is available (self-heal a rebuilt container) --------------
if ! docker exec "$CONTAINER" python -m pytest --version >/dev/null 2>&1; then
  echo "pytest not found in container — installing pytest/pytest-cov/pytest-asyncio..."
  docker exec "$CONTAINER" pip install -q pytest pytest-cov pytest-asyncio
fi

# --- Copy a clean snapshot in and run the tests ------------------------------
echo "Copying into container at $DEST ..."
docker exec "$CONTAINER" sh -c "rm -rf '$DEST'" >/dev/null 2>&1 || true
docker cp "$PLUGIN_DIR" "$CONTAINER:$DEST" >/dev/null

# Detect layout: nested (real plugins/<id>/) needs no symlink; root layout does.
docker exec -w "$DEST" "$CONTAINER" sh -c '
  set -e
  PLUGIN_ID='"$PLUGIN_ID"'
  if [ -f "plugins/$PLUGIN_ID/__init__.py" ]; then
    # nested layout — already importable as plugins.<id>
    [ -f plugins/__init__.py ] || touch plugins/__init__.py
    COV="--cov=plugins"
  else
    # root layout — recreate the CI symlink scaffold (ignored by git)
    rm -rf "plugins/$PLUGIN_ID" "$PLUGIN_ID" 2>/dev/null || true
    mkdir -p plugins && touch plugins/__init__.py
    ln -sf .. "plugins/$PLUGIN_ID"
    ln -sf . "$PLUGIN_ID"
    COV="--cov=."
  fi
  cat > .coveragerc <<RCEOF
[run]
omit = /app/*
RCEOF
  PYTHONPATH="'"$DEST"':/app" BOARD_READ_WRITE_KEY=test_key \
    python -m pytest tests/ -v $COV --cov-report=term-missing \
      --cov-fail-under=70 --ignore=/app -p no:cacheprovider
'
