#!/usr/bin/env bash
# Apply main-branch protection for FiestaBoard plugin repos (fiestaboard-plugin--*).
#
# Preferred: organization ruleset (scripts/fiestaboard-plugin-org-main-ruleset.json).
# That API requires GitHub Team; on Free orgs you get HTTP 403 and this script falls
# back to classic branch protection per repo (same intent: PR + 1 approval, no force
# push, no branch deletion).
#
# Requires: gh CLI, repo admin on each plugin repo (org owner has this).
# If org rulesets are desired, also: gh auth refresh -h github.com -s admin:org
set -euo pipefail

ORG="FiestaBoard"
RULESET_NAME="Plugin repos - main branch requirements"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RULESET_JSON="${SCRIPT_DIR}/fiestaboard-plugin-org-main-ruleset.json"
CLASSIC_JSON="${SCRIPT_DIR}/fiestaboard-plugin-branch-protection-classic.json"

if [[ ! -f "${CLASSIC_JSON}" ]]; then
  echo "Missing ${CLASSIC_JSON}" >&2
  exit 1
fi

try_org_ruleset() {
  if [[ ! -f "${RULESET_JSON}" ]]; then
    return 1
  fi
  if ! gh api "orgs/${ORG}/rulesets" >/dev/null 2>&1; then
    return 1
  fi
  local existing_id
  existing_id="$(
    gh api "orgs/${ORG}/rulesets" --paginate --jq -r \
      "[.[] | select(.name == \"${RULESET_NAME}\") | .id] | first // empty"
  )"
  if [[ -n "${existing_id}" ]]; then
    echo "Updating org ruleset id ${existing_id} (${RULESET_NAME})"
    gh api --method PUT "orgs/${ORG}/rulesets/${existing_id}" --input "${RULESET_JSON}"
  else
    echo "Creating org ruleset (${RULESET_NAME})"
    gh api --method POST "orgs/${ORG}/rulesets" --input "${RULESET_JSON}"
  fi
  return 0
}

apply_classic_per_repo() {
  echo "Applying classic branch protection on main for each fiestaboard-plugin--* repo..."
  local names
  names="$(
    gh repo list "${ORG}" -L 1000 --json name -q \
      '.[] | select(.name | test("^fiestaboard-plugin--")) | .name'
  )"
  if [[ -z "${names}" ]]; then
    echo "No matching repositories found." >&2
    exit 1
  fi
  local n
  n="$(echo "${names}" | wc -l | tr -d ' ')"
  echo "Found ${n} repository(ies)."
  local repo
  while IFS= read -r repo; do
    [[ -z "${repo}" ]] && continue
    echo "  PUT ${ORG}/${repo} branches/main/protection"
    gh api --method PUT "repos/${ORG}/${repo}/branches/main/protection" --input "${CLASSIC_JSON}" --silent
  done <<< "${names}"
  echo "Classic protection applied."
}

ruleset_msg="$(gh api "orgs/${ORG}/rulesets" 2>&1)" || true
if echo "${ruleset_msg}" | grep -q 'Upgrade to GitHub Team'; then
  echo "Organization rulesets are not available on this plan (GitHub Team required)."
  echo "Using classic branch protection for each plugin repository instead."
  apply_classic_per_repo
  exit 0
fi

if try_org_ruleset; then
  echo "Done (organization ruleset). Verify: https://github.com/organizations/${ORG}/settings/rules"
  exit 0
fi

echo "Cannot use organization rulesets API (missing admin:org or other error). Falling back to classic protection."
apply_classic_per_repo
