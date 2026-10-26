# Release channels

Development and pull requests target `main`. The `next` branch is frozen while
existing beta installations move onto the stable release stream. Do not merge
new work or sync `main` back into `next` during this transition.

## Beta publication pause

`Release: Publish Beta Image` (`release-beta.yml`) is disabled in GitHub Actions.
Its retained definition on `main` has no push trigger and permits a manual run
only against `next`. A future beta cycle requires a deliberate workflow
re-enable and a review of its target version before publishing.

Keep the workflow disabled while `next` retains its older push-triggered
definition. A change on `main` alone does not replace the workflow on `next`.
Preserve existing beta tags, releases, and versioned Docker images.

## Move beta installations onto stable

`v10.1.0-beta.1` was published after `v10.0.0`. A `10.0.x` patch is older than
that beta, so it cannot graduate every beta installation through an ordinary
update. The transition PR carries the `minor` label: the existing stable release
workflow derives a `10.1.0` release from the committed `10.0.0` version.

Keep version files at their current stable value in the PR; `release.yml` bumps
and commits them after merge. Confirm the PR still has `minor` immediately
before merging, and confirm the released version is newer than all published
betas before declaring the transition complete.

The beta update checker considers stable releases as well as prereleases. When
`10.1.0` is available, Update Now (or enabled automatic updates) installs that
exact version, records the stable channel, and clears the beta join snapshot
reference. The next boot therefore stays on stable without restoring old
configuration. Installations with automatic updates disabled still need their
owner to apply the update. Explicit Docker image pins need to be moved to the
stable version or `latest` by their owner.

## Keep main ahead of next

Integrate the remaining `next` housekeeping commits into `main` without rewriting
`next`, then continue development only on `main`. Preserve ancestry with a merge
commit or fast-forward integration; a squash copies the changes but leaves
`next` with unique commits. The current `main` ruleset allows squash merges, so
an authorized maintainer must resolve that integration constraint explicitly.
Do not force-push either branch or rewrite published tags to make a comparison
look clean.
