# fiestaboard

## 10.4.0-beta.1

### Minor Changes

- [#2394](https://github.com/Fiestaboard/FiestaBoard/pull/2394) [`ccd6ff9`](https://github.com/Fiestaboard/FiestaBoard/commit/ccd6ff92367958a8aa11b1c77d8855dcb78e347a) Thanks [@jeffredodd](https://github.com/jeffredodd)! - List the Ulanzi TC001 output plugin in the display Marketplace and setup catalog.

- [#2408](https://github.com/Fiestaboard/FiestaBoard/pull/2408) [`7648108`](https://github.com/Fiestaboard/FiestaBoard/commit/7648108a7f0276246c46b78164446943fb62ad3e) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Add saved-content search and sorting to the Pages library while preserving display compatibility filters and preview caching.

### Patch Changes

- [#2412](https://github.com/Fiestaboard/FiestaBoard/pull/2412) [`8067b15`](https://github.com/Fiestaboard/FiestaBoard/commit/8067b15cf95ebafec8c6a8b08c50ef098d2e524c) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Ignore retired output-device poll replies and keep one failed recovery from blocking other boards.

- [#2417](https://github.com/Fiestaboard/FiestaBoard/pull/2417) [`7f22a6c`](https://github.com/Fiestaboard/FiestaBoard/commit/7f22a6c224dba2aa7730c5938e35cbb1b1fed2b0) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Resolve sunrise and sunset schedules when civil twilight is unavailable.

- [#2418](https://github.com/Fiestaboard/FiestaBoard/pull/2418) [`663b262`](https://github.com/Fiestaboard/FiestaBoard/commit/663b26238ec753e49f53f47b40047d0069bc41d2) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Apply edited collection rotation intervals without waiting for an obsolete deadline.

- [#2419](https://github.com/Fiestaboard/FiestaBoard/pull/2419) [`63642d3`](https://github.com/Fiestaboard/FiestaBoard/commit/63642d3b9259e2fa1bea4ea4892fea6593bb70ef) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Skip collection members that do not fit the board when sending pinned content immediately.

- [#2421](https://github.com/Fiestaboard/FiestaBoard/pull/2421) [`9b9aa40`](https://github.com/Fiestaboard/FiestaBoard/commit/9b9aa40fe48948be94d691cc9e4d201871724c07) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Keep forced output-write mode isolated across overlapping writers.

- [#2429](https://github.com/Fiestaboard/FiestaBoard/pull/2429) [`780bed6`](https://github.com/Fiestaboard/FiestaBoard/commit/780bed67bf1115ae24897fe79448ea31563ef100) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Run network diagnostics off the API event loop without changing process-wide socket timeouts.

- [#2426](https://github.com/Fiestaboard/FiestaBoard/pull/2426) [`ce36f3e`](https://github.com/Fiestaboard/FiestaBoard/commit/ce36f3eac1274b0412608b209c7aefbd69063aea) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Replace plugin demo pages atomically so failed saves preserve the existing demo.

- [#2403](https://github.com/Fiestaboard/FiestaBoard/pull/2403) [`27566d1`](https://github.com/Fiestaboard/FiestaBoard/commit/27566d1c1f5a70da802f2d2a79b5d36cfaa41a8a) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Preserve settings and schedule defaults when persistence fails.

- [#2402](https://github.com/Fiestaboard/FiestaBoard/pull/2402) [`4aa117f`](https://github.com/Fiestaboard/FiestaBoard/commit/4aa117f23f4722d866c51a3ccb3a19da2a6db1e0) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Keep pages, collections, and schedules unchanged when a save fails.

- [#2399](https://github.com/Fiestaboard/FiestaBoard/pull/2399) [`63840e1`](https://github.com/Fiestaboard/FiestaBoard/commit/63840e1ce6370c2985db156b81c7d9ab981910a2) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Update follow-redirects to 1.16.2 to fix cross-realm sensitive header handling in development dependencies.

- [#2465](https://github.com/Fiestaboard/FiestaBoard/pull/2465) [`ac5be14`](https://github.com/Fiestaboard/FiestaBoard/commit/ac5be1460d9acfcb25cc9fc24db74e16b997fc48) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Formulas now have firm limits on how much text they can build and how much work they can do, so a single page can no longer stall the hub.

- [#2420](https://github.com/Fiestaboard/FiestaBoard/pull/2420) [`e5dfc17`](https://github.com/Fiestaboard/FiestaBoard/commit/e5dfc17620865bd23723650beae5e2a12cafd1be) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Roll back general configuration updates when durable writes fail.

- [#2404](https://github.com/Fiestaboard/FiestaBoard/pull/2404) [`18e85ea`](https://github.com/Fiestaboard/FiestaBoard/commit/18e85eae143e20aeeef6dbf27e786cf99b3813d2) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Persist plugin configuration before publishing runtime updates.

- [#2427](https://github.com/Fiestaboard/FiestaBoard/pull/2427) [`4f1ca09`](https://github.com/Fiestaboard/FiestaBoard/commit/4f1ca09acb46e5821db585e308afb90779246cb1) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Publish discovered plugins only after restoring saved configuration successfully.

- [#2406](https://github.com/Fiestaboard/FiestaBoard/pull/2406) [`5567dd8`](https://github.com/Fiestaboard/FiestaBoard/commit/5567dd89474f6760f36e22f4b7723ebdc06d6ea0) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Invalidate in-flight plugin fetch results after configuration and lifecycle changes.

- [#2414](https://github.com/Fiestaboard/FiestaBoard/pull/2414) [`7a5eede`](https://github.com/Fiestaboard/FiestaBoard/commit/7a5eedef8448d844b1e85899b9ca87235ee3dca7) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Persist new plugin instances atomically before publishing them.

- [#2413](https://github.com/Fiestaboard/FiestaBoard/pull/2413) [`7c0528d`](https://github.com/Fiestaboard/FiestaBoard/commit/7c0528d2e593a98ff424aad3a8aedd58be6395f8) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Persist plugin instance deletion before removing runtime state.

- [#2405](https://github.com/Fiestaboard/FiestaBoard/pull/2405) [`5f8c00f`](https://github.com/Fiestaboard/FiestaBoard/commit/5f8c00f51d6b844a38077155593d5429273bc6ee) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Persist plugin enable and disable changes before changing runtime state.

- [#2424](https://github.com/Fiestaboard/FiestaBoard/pull/2424) [`2309e43`](https://github.com/Fiestaboard/FiestaBoard/commit/2309e43484dc7928b90252a8a96e143a239db448) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Ensure each retired plugin instance is cleaned up only once during reload.

- [#2425](https://github.com/Fiestaboard/FiestaBoard/pull/2425) [`a53de9a`](https://github.com/Fiestaboard/FiestaBoard/commit/a53de9a761151d9cc795f7e29df425049d7ce60d) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Load current plugin source after rapid updates instead of stale bytecode.

- [#2422](https://github.com/Fiestaboard/FiestaBoard/pull/2422) [`04c1350`](https://github.com/Fiestaboard/FiestaBoard/commit/04c13507fcdea39c988671e1eefce3654ddfa376) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Make plugin uninstall transactional and preserve cleanup ownership.

- [#2423](https://github.com/Fiestaboard/FiestaBoard/pull/2423) [`0308768`](https://github.com/Fiestaboard/FiestaBoard/commit/0308768d675fe43989ae2fcbf19406e663fa059d) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Serialize plugin source updates across the complete update operation.

- [#2400](https://github.com/Fiestaboard/FiestaBoard/pull/2400) [`e7ef2a5`](https://github.com/Fiestaboard/FiestaBoard/commit/e7ef2a519f6cb715103822f2f30ba557096a11b8) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Keep legacy query-based page editor navigation synchronized after dirty page IDs change or are removed.

- [#2401](https://github.com/Fiestaboard/FiestaBoard/pull/2401) [`69af234`](https://github.com/Fiestaboard/FiestaBoard/commit/69af2347af518109b02ff8258172844c40df210f) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Keep legacy collection data recoverable when migration cannot be saved.

- [#2415](https://github.com/Fiestaboard/FiestaBoard/pull/2415) [`8871517`](https://github.com/Fiestaboard/FiestaBoard/commit/88715175ea096203637cf00782dd426be4770b3b) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Recover original data after a backup restore fails partway through.

- [#2416](https://github.com/Fiestaboard/FiestaBoard/pull/2416) [`50b32ea`](https://github.com/Fiestaboard/FiestaBoard/commit/50b32ea3af936f5148120809b45ceb7723cbcc16) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Reject malformed backup stores before changing any live files.

## 10.3.4-beta.0

### Patch Changes

- [#2441](https://github.com/Fiestaboard/FiestaBoard/pull/2441) [`8913d58`](https://github.com/Fiestaboard/FiestaBoard/commit/8913d583903e3f1bea8766e292c0fea2271f0cf4) Thanks [@jeffredodd](https://github.com/jeffredodd)! - MQTT's `current_page` sensor now reports the page the board is actually showing (including scheduled, collection, override and silence pages) and publishes as soon as the page changes, instead of reporting the manually selected page.

## 10.3.3

### Patch Changes

- [#2428](https://github.com/Fiestaboard/FiestaBoard/pull/2428) [`51f4d33`](https://github.com/Fiestaboard/FiestaBoard/commit/51f4d333c93c54e7717809eb32a4c3578134b1ee) Thanks [@fiestaboard-ci-bot](https://github.com/apps/fiestaboard-ci-bot)! - Upgrade the FiestaUI design system (`@fiestaboard/ui`) to v8.16.0.
