# fiestaboard

## 10.4.0

### Minor Changes

- [#2551](https://github.com/Fiestaboard/FiestaBoard/pull/2551) [`a3ecf00`](https://github.com/Fiestaboard/FiestaBoard/commit/a3ecf0079fd96ebcdb8d1ba53ac919ddc75da6bb) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Settings → System now offers a Stable, Beta and Alpha preview release-channel chooser that shows each channel's published version. Picking a channel never installs anything until you confirm; upgrading to FiestaBoard 11 asks for explicit confirmation and takes a required automatic backup first, and returning to an older channel restores the matching pre-upgrade backup. Update checks stay isolated per channel.

### Patch Changes

- [#2438](https://github.com/Fiestaboard/FiestaBoard/pull/2438) [`808913a`](https://github.com/Fiestaboard/FiestaBoard/commit/808913a4219f826eea3bab9eac35c8f332df084b) Thanks [@jeffredodd](https://github.com/jeffredodd)! - MQTT's `current_page` sensor now reports the page the board is actually showing (including scheduled, collection, override and silence pages) and publishes as soon as the page changes, instead of reporting the manually selected page.

- [#2472](https://github.com/Fiestaboard/FiestaBoard/pull/2472) [`9101893`](https://github.com/Fiestaboard/FiestaBoard/commit/91018934a676b4d9b1ce7fee622ece1bd5f3d603) Thanks [@roblesi](https://github.com/roblesi)! - Docker Compose no longer fails with "env file .env not found" on a fresh install: the `.env` file is now optional, and an unset `FIESTAUPDATER_TOKEN` no longer prints a warning.

## 10.3.3

### Patch Changes

- [#2428](https://github.com/Fiestaboard/FiestaBoard/pull/2428) [`51f4d33`](https://github.com/Fiestaboard/FiestaBoard/commit/51f4d333c93c54e7717809eb32a4c3578134b1ee) Thanks [@fiestaboard-ci-bot](https://github.com/apps/fiestaboard-ci-bot)! - Upgrade the FiestaUI design system (`@fiestaboard/ui`) to v8.16.0.
