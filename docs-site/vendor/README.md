# Vendored `@fiestaboard/ui`

`fiestaboard-ui-1.3.2-board-teaser.tgz` is a packed build of the FiestaUI design system
(`@fiestaboard/ui`), referenced by `package.json` as
`"@fiestaboard/ui": "file:./vendor/fiestaboard-ui-1.3.2-board-teaser.tgz"`.
This pack is FiestaUI `main` at v1.3.2 plus the `BoardTeaser` component from
[FiestaUI PR #55](https://github.com/Fiestaboard/FiestaUI/pull/55); re-vendor a
clean pack once that PR ships in a released minor.

We vendor a tarball rather than depend on the published package because
`@fiestaboard/ui` publishes to GitHub Packages (not npmjs) and its `dist/` is
gitignored — so a plain `npm install` in CI/deploy would fail without a registry
token. The tarball is self-contained, so `npm ci` works with no extra auth.

## Regenerating the tarball

When the design system changes and the docs site needs to pick it up, rebuild
and repack from the FiestaUI checkout (a sibling of this repo):

```bash
cd ../FiestaUI            # the @fiestaboard/ui source repo
npm run build            # produces dist/
npm pack --pack-destination /path/to/FiestaBoard/docs-site/vendor
```

Then bump the filename in `package.json` if the version changed and run
`npm install` in `docs-site/` to refresh `package-lock.json`.

## Follow-up

Once `@fiestaboard/ui` is published to a registry the docs-site build can read,
switch the dependency from `file:./vendor/...` to a normal semver range and
delete this directory.
