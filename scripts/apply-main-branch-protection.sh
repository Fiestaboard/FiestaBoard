#!/usr/bin/env bash
# Apply main-branch protection for the FiestaBoard repo.
#
# Rules:
#   - Require a pull request before merging (0 approvals required)
#   - CI must pass ("CI Success" sentinel job)
#   - Only the "taco-farmers" team can merge
#   - Force pushes and branch deletion are blocked
#
# Prerequisites:
#   - gh CLI authenticated (gh auth status)
#   - The ci-success sentinel job must be present in .github/workflows/ci.yml
#     (merge feat/branch-protection-sentinel first)
#
# Usage:
#   bash scripts/apply-main-branch-protection.sh
set -euo pipefail

OWNER="Fiestaboard"
REPO="FiestaBoard"
BRANCH="main"
TEAM_SLUG="taco-farmers"

echo "Applying branch protection to ${OWNER}/${REPO}:${BRANCH}..."

gh api --method PUT \
  "repos/${OWNER}/${REPO}/branches/${BRANCH}/protection" \
  --input - <<EOF
{
  "required_status_checks": {
    "strict": false,
    "checks": [
      {"context": "CI Success"}
    ]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": false,
    "require_code_owner_reviews": false,
    "required_approving_review_count": 0,
    "require_last_push_approval": false
  },
  "restrictions": {
    "users": [],
    "teams": ["${TEAM_SLUG}"]
  },
  "required_linear_history": false,
  "allow_force_pushes": false,
  "allow_deletions": false
}
EOF

echo ""
echo "✅ Branch protection applied."
echo ""
echo "Settings:"
echo "  • PRs required to merge to ${BRANCH} (0 approvals needed)"
echo "  • 'CI Success' check must pass before merging"
echo "  • Only @${OWNER}/${TEAM_SLUG} can merge"
echo "  • Force pushes and deletion blocked"
echo ""
echo "To verify:"
echo "  gh api repos/${OWNER}/${REPO}/branches/${BRANCH}/protection | jq ."
