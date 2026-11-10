# fiestaboard

## 10.3.4

### Patch Changes

- [#2438](https://github.com/Fiestaboard/FiestaBoard/pull/2438) [`808913a`](https://github.com/Fiestaboard/FiestaBoard/commit/808913a4219f826eea3bab9eac35c8f332df084b) Thanks [@jeffredodd](https://github.com/jeffredodd)! - MQTT's `current_page` sensor now reports the page the board is actually showing (including scheduled, collection, override and silence pages) and publishes as soon as the page changes, instead of reporting the manually selected page.

- [#2472](https://github.com/Fiestaboard/FiestaBoard/pull/2472) [`9101893`](https://github.com/Fiestaboard/FiestaBoard/commit/91018934a676b4d9b1ce7fee622ece1bd5f3d603) Thanks [@roblesi](https://github.com/roblesi)! - Docker Compose no longer fails with "env file .env not found" on a fresh install: the `.env` file is now optional, and an unset `FIESTAUPDATER_TOKEN` no longer prints a warning.

## 10.3.3

### Patch Changes

- [#2428](https://github.com/Fiestaboard/FiestaBoard/pull/2428) [`51f4d33`](https://github.com/Fiestaboard/FiestaBoard/commit/51f4d333c93c54e7717809eb32a4c3578134b1ee) Thanks [@fiestaboard-ci-bot](https://github.com/apps/fiestaboard-ci-bot)! - Upgrade the FiestaUI design system (`@fiestaboard/ui`) to v8.16.0.
