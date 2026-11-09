# Vendored packages

## `fiestaboard-ui-8.17.0-alpha.0.tgz`

This is the `@fiestaboard/ui` 8.17.0-alpha.0 release, used on the `v11` branch only. Its npm publish failed:
the release run of Fiestaboard/FiestaUI#383 got E404 on PUT (owner action O11), so the registry still has
only `latest` = 8.16.0.

`web/package.json` installs it with `"@fiestaboard/ui": "file:vendor/fiestaboard-ui-8.17.0-alpha.0.tgz"`.
CI and the Docker build therefore need no git fetch and no registry auth. The Dockerfile copies `web/vendor/`
before `npm ci`.

|                   |                                                                                                                                   |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Source            | `Fiestaboard/FiestaUI` at `900fabf640d6f848f93fedf9885108147149c2d9`, the #383 merge commit on `alpha` ("chore: release (alpha)") |
| Built with        | `node:24` image (Node 24.22.2, npm 11.19.1), the same Node major as FiestaUI's `release.yml`                                      |
| Steps             | `npm ci --no-audit && npm run build && npm pack`                                                                                  |
| sha512            | `sha512-sTRSE4G44g4buS/979pHJ1ZiCWNlMQqktSoQnt1400l8ZuI/5ibzUMz5Cw8Cv93bUJxo4VeNPtpLWD3HSt5iFg==`                                 |
| sha1 (npm shasum) | `c974b3043a238a7203ff11ce0eb41aca92e02659`                                                                                        |

The sha512 is also the `integrity` value in `web/package-lock.json`. Two builds from fresh clones produced
byte-identical tarballs.

To rebuild it:

```bash
git clone https://github.com/Fiestaboard/FiestaUI.git && cd FiestaUI
git checkout 900fabf640d6f848f93fedf9885108147149c2d9
docker run --rm -v "$PWD":/src -w /src node:24 sh -c 'npm ci --no-audit && npm run build && npm pack'
```

## Removing it

Once O11 is fixed, replace this tarball with the registry pin `8.17.0-alpha.N`. Most of the swap is the
dependency line in `web/package.json`:

```diff
-    "@fiestaboard/ui": "file:vendor/fiestaboard-ui-8.17.0-alpha.0.tgz",
+    "@fiestaboard/ui": "8.17.0-alpha.N",
```

After that:

- Regenerate the lockfile in the container.
- Delete `web/vendor/`.

The Dockerfile's `COPY web/vendo[r] ./vendor/` line matches nothing once the directory is gone, so the
Dockerfile does not need to change.
