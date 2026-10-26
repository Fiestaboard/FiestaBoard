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
update. The combined enhancement PR targets stable `10.1.1`. Its version files are
synchronized to `10.1.0` and it carries the `patch` release label, so the existing
stable workflow increments them to `10.1.1` after merge. The `enhancement` label
describes the change; it does not select the version bump.

Confirm the PR has `patch` and neither `minor` nor `major` immediately before
merging: those higher-priority labels would change the requested target.
`release.yml` commits the final version bump after merge. Recheck the version
base if another release merges first, and confirm the published release is
`10.1.1` and newer than all published betas before declaring the transition
complete.

The beta update checker considers stable releases as well as prereleases. When
`10.1.1` is available, Update Now (or enabled automatic updates) installs that
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
