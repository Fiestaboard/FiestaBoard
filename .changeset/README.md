# Changesets

Every PR that changes what ships (the Docker image or the FiestaPi image) adds a
changeset: run `npx changeset`, pick `patch`, `minor` or `major` for
`fiestaboard`, and write one user-facing line. That line becomes the
`CHANGELOG.md` entry and the GitHub Release note.

Changes that release nothing need no changeset, or use `npx changeset --empty`
or the `no-changeset` label. See
[docs/internal/development/RELEASING.md](../docs/internal/development/RELEASING.md).
