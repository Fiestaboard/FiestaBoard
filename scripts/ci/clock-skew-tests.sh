#!/usr/bin/env bash
# Run the web vitest suite with the wall clock started at fixed instants
# (web/src/__tests__/test-now.ts reads TEST_NOW), so a test that only passes
# on the day it was written fails here (#2571 passed only on weekdays).
#
# Run from the repo root after `npm ci` in web/. CI:
#   - pull_request: only the tests `vitest --changed origin/$BASE_REF` selects
#     (changed tests plus every test that imports a changed module), unless
#     the PR touches the clock or test setup itself, then the full suite.
#   - changeset-release/* PRs, workflow_dispatch (the nightly v11 run) and
#     CLOCK_SKEW_MODE=full: the full suite.
# Both instants always run, even when the first one fails.
#
# Reproduce one leg locally (in the web test container):
#   TZ=UTC TEST_NOW=2026-11-21T12:00:00Z npx vitest run
set -uo pipefail

# Saturday; and Dec 31 23:00, where "tomorrow" is next month and next year.
# UTC is what makes the second one a year boundary.
INSTANTS=${CLOCK_SKEW_INSTANTS:-"2026-11-21T12:00:00Z 2026-12-31T23:00:00Z"}
export TZ=UTC

# A change to any of these can move every test's clock or setup.
FULL_SUITE_TRIGGERS='^(web/src/__tests__/(setup|test-now)\.ts|web/src/__tests__/mocks/|web/(vitest|vite)\.config\.|web/package(-lock)?\.json|web/suppress-warnings\.mjs|scripts/ci/clock-skew-tests\.sh)'

mode=${CLOCK_SKEW_MODE:-}
if [ -z "$mode" ]; then
  if [ "${GITHUB_EVENT_NAME:-}" != "pull_request" ] || [[ "${HEAD_REF:-}" == changeset-release/* ]]; then
    mode=full
  else
    : "${BASE_REF:?BASE_REF (the PR base branch) is required on pull_request}"
    changed=$(git diff --name-only "origin/$BASE_REF" HEAD) || exit 1
    if grep -Eq "$FULL_SUITE_TRIGGERS" <<<"$changed"; then
      mode=full
      echo "Clock or test setup changed: running the full suite."
    else
      mode=changed
    fi
  fi
fi

args=(run)
if [ "$mode" = "changed" ]; then
  args+=(--changed "origin/$BASE_REF" --passWithNoTests)
fi

cd web || exit 1
failed=()
for now in $INSTANTS; do
  echo "::group::TEST_NOW=$now ($mode)"
  # The shim itself first: if it stopped moving the clock, every leg below
  # would pass without testing anything.
  TEST_NOW="$now" npx vitest run src/__tests__/test-now.test.ts || failed+=("$now (shim)")
  TEST_NOW="$now" npx vitest "${args[@]}" || failed+=("$now")
  echo "::endgroup::"
done

{
  echo "### Clock skew ($mode)"
  for now in $INSTANTS; do
    if printf '%s\n' "${failed[@]}" | grep -q "^$now"; then echo "- ❌ \`TEST_NOW=$now\`"; else echo "- ✅ \`TEST_NOW=$now\`"; fi
  done
  echo
  echo "Reproduce: \`TZ=UTC TEST_NOW=<instant> npx vitest run\` in web/."
} >> "${GITHUB_STEP_SUMMARY:-/dev/null}"

if [ ${#failed[@]} -gt 0 ]; then
  echo "::error title=Clock skew::Tests failed with the clock at: ${failed[*]}. Reproduce: TZ=UTC TEST_NOW=<instant> npx vitest run"
  exit 1
fi
