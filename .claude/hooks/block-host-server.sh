#!/usr/bin/env bash
# PreToolUse hook for Bash. Blocks the four NEVER rules from CLAUDE.md:
#   - python -m src.api_server (or src/api_server.py)
#   - cd web && npm run dev / npm install
#   - pip install (on host)
#
# Reads tool input as JSON on stdin (Claude Code hook contract).
# Exit 0: allow. Exit 2: block with stderr message shown to model.

set -u

input="$(cat)"
cmd="$(printf '%s' "$input" | python3 -c 'import sys, json; d=json.load(sys.stdin); print(d.get("tool_input", {}).get("command", ""))' 2>/dev/null || true)"

if [[ -z "$cmd" ]]; then
  exit 0
fi

block() {
  echo "BLOCKED: $1" >&2
  echo "FiestaBoard runs everything in a Docker container. Use the dev container instead:" >&2
  echo "  • Start container: /start  (or docker-compose -f docker-compose.dev.yml up -d)" >&2
  echo "  • Run Python:      docker-compose -f docker-compose.dev.yml exec fiestaboard <cmd>" >&2
  echo "  • Web dev:         already running inside the container — no host npm run dev" >&2
  echo "  • Dependencies:    edit requirements.txt / web/package.json and rebuild (/build or /restart)" >&2
  exit 2
}

# Python API server on host
if [[ "$cmd" =~ (^|[^[:alnum:]])python[0-9.]*[[:space:]]+-m[[:space:]]+src\.api_server ]]; then
  block "running the API server on the host"
fi
if [[ "$cmd" =~ (^|[^[:alnum:]])python[0-9.]*[[:space:]]+src/api_server\.py ]]; then
  block "running the API server on the host"
fi

# npm run dev / npm install in web/ on host
if [[ "$cmd" =~ (^|[^[:alnum:]])cd[[:space:]]+web([[:space:]]|$).*npm[[:space:]]+run[[:space:]]+dev ]]; then
  block "running 'npm run dev' on the host"
fi
if [[ "$cmd" =~ (^|[^[:alnum:]])cd[[:space:]]+web([[:space:]]|$).*npm[[:space:]]+install ]]; then
  block "running 'npm install' on the host"
fi

# pip install on host (allow when wrapped in docker-compose exec)
if [[ "$cmd" =~ (^|[^[:alnum:]])pip[0-9.]*[[:space:]]+install ]]; then
  if [[ ! "$cmd" =~ docker-compose ]] && [[ ! "$cmd" =~ docker[[:space:]]+exec ]]; then
    block "running 'pip install' on the host"
  fi
fi

exit 0
