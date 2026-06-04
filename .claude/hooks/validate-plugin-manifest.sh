#!/usr/bin/env bash
# PostToolUse hook for Edit/Write. If the touched path is a plugin manifest.json,
# run scripts/validate_plugins.py and surface output to the conversation.
#
# Reads tool input as JSON on stdin.
# Exit 0 always (advisory only — does not block).

set -u

input="$(cat)"

file_path="$(printf '%s' "$input" | python3 -c '
import sys, json
d = json.load(sys.stdin)
ti = d.get("tool_input", {})
print(ti.get("file_path") or ti.get("filePath") or "")
' 2>/dev/null || true)"

if [[ -z "$file_path" ]]; then
  exit 0
fi

# Match plugins/<id>/manifest.json (allow anywhere on disk, not just CWD)
if [[ ! "$file_path" =~ /plugins/([^/]+)/manifest\.json$ ]]; then
  exit 0
fi

plugin_id="${BASH_REMATCH[1]}"

# Skip the template
if [[ "$plugin_id" == "_template" ]]; then
  exit 0
fi

# Locate repo root by walking up from the touched file
dir="$(dirname "$file_path")"
while [[ "$dir" != "/" && ! -d "$dir/scripts" ]]; do
  dir="$(dirname "$dir")"
done

if [[ ! -f "$dir/scripts/validate_plugins.py" ]]; then
  echo "[validate-plugin-manifest] could not locate scripts/validate_plugins.py from $file_path" >&2
  exit 0
fi

echo "[validate-plugin-manifest] validating plugin: $plugin_id"
(cd "$dir" && python3 scripts/validate_plugins.py --plugin="$plugin_id" 2>&1) || {
  echo "[validate-plugin-manifest] validation reported issues for $plugin_id (see above)" >&2
}

exit 0
