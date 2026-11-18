# fiestaboard

## 11.0.0-alpha.9

### Minor Changes

- [#2538](https://github.com/Fiestaboard/FiestaBoard/pull/2538) [`e54c7f3`](https://github.com/Fiestaboard/FiestaBoard/commit/e54c7f3f976df281a33e5ed0113abfb0b2e05ed5) Thanks [@jeffredodd](https://github.com/jeffredodd)! - The phone app can add, change and remove displays and change display settings. If you move a display to a new address from the phone, you have to enter its key again.

- [#2537](https://github.com/Fiestaboard/FiestaBoard/pull/2537) [`addb149`](https://github.com/Fiestaboard/FiestaBoard/commit/addb149c6c35894d7312cb4c9b6e7524d86ed45d) Thanks [@jeffredodd](https://github.com/jeffredodd)! - FiestaBot works from the phone app. It can only do what the phone can do, and it always asks before sensitive actions, which also need your password re-entered.

## 11.0.0-alpha.8

### Minor Changes

- [#2501](https://github.com/Fiestaboard/FiestaBoard/pull/2501) [`0afe3c8`](https://github.com/Fiestaboard/FiestaBoard/commit/0afe3c8137a280f90eb590df50c948b5935d20d4) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Keep the editor preview visible while editing on touch devices, add responsive kit toolbars and mirroring controls, and save Pages in place before showing them on a display.
  
  Keep plain-text tools and undo history available for unknown displays, offer starter actions on empty pages, and preserve toolbar landmarks, editor focus and the preview when the visible viewport contracts.

- [#2536](https://github.com/Fiestaboard/FiestaBoard/pull/2536) [`5fd4b6b`](https://github.com/Fiestaboard/FiestaBoard/commit/5fd4b6bfb79c68a6a114f65084e85be04537f05a) Thanks [@jeffredodd](https://github.com/jeffredodd)! - The phone app can change general settings and see Wi-Fi status. After you re-enter your password, it can also join or forget Wi-Fi networks, update or restart the hub, change AI providers, and export or restore backups. A phone's backup leaves out passwords and keys.

- [#2535](https://github.com/Fiestaboard/FiestaBoard/pull/2535) [`33be4a0`](https://github.com/Fiestaboard/FiestaBoard/commit/33be4a0a9f03572165f9acb13cfbc44ee5413ded) Thanks [@jeffredodd](https://github.com/jeffredodd)! - The phone app can install plugins from the plugin list, update them and remove them after you re-enter your password. Installing from a Git URL stays in the web app.

- [#2534](https://github.com/Fiestaboard/FiestaBoard/pull/2534) [`823790a`](https://github.com/Fiestaboard/FiestaBoard/commit/823790ad684e0171c1511e417c6c76d00eafcfb0) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Phones can re-enter the account password to unlock sensitive actions for 10 minutes (step-up). The hub asks for it before those actions.

### Patch Changes

- [#2506](https://github.com/Fiestaboard/FiestaBoard/pull/2506) [`cd4cf4f`](https://github.com/Fiestaboard/FiestaBoard/commit/cd4cf4f147a5f7535682a3562be1131045f9a483) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Group integrations that need setup or reconnection, show settings beside the installed list on larger screens, and use compact marketplace results on phones.
  
  Open full integration details on phones, reconnect accounts, and browse settings, live variables and README documentation.

- [#2503](https://github.com/Fiestaboard/FiestaBoard/pull/2503) [`60b33e0`](https://github.com/Fiestaboard/FiestaBoard/commit/60b33e0937ab358ca79e38d2ebb9c0ed56f66494) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Unify Home's silence and out-of-sync banners, retain held messages, and clearly pause sends with a last-known preview when the hub is unreachable.

- [#2530](https://github.com/Fiestaboard/FiestaBoard/pull/2530) [`5e018c4`](https://github.com/Fiestaboard/FiestaBoard/commit/5e018c4534bc3075055e2ecd7b2e1a561c947e9b) Thanks [@jeffredodd](https://github.com/jeffredodd)! - The hub's mDNS record now carries its `.local` host name (and its name while sign-in is off) for the TV and phone apps; the phone pairing QR skips a bridged Podman or Docker container's own address whatever its range; and a failed duplicate-display check during a connection test now reads as "not checked" instead of "none found".

- [#2539](https://github.com/Fiestaboard/FiestaBoard/pull/2539) [`a341b0f`](https://github.com/Fiestaboard/FiestaBoard/commit/a341b0ff4aad4d3935bff83583051b935b2d6cb5) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Stop the docs link check from failing CI when a linked host returns a transient 502/503/504; broken links (404s) still fail.

- [#2527](https://github.com/Fiestaboard/FiestaBoard/pull/2527) [`69b0d8c`](https://github.com/Fiestaboard/FiestaBoard/commit/69b0d8c3a93c027d9ebecc40412e29e084939118) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Distinguish failed notification tests from skipped tests in every language and remove unused notification translations.

- [#2531](https://github.com/Fiestaboard/FiestaBoard/pull/2531) [`966bc2a`](https://github.com/Fiestaboard/FiestaBoard/commit/966bc2ad15ff6b42b711e560af75ea170d4c4d4a) Thanks [@jeffredodd](https://github.com/jeffredodd)! - The display connection test now applies the same host checks as the Local API enablement step.

- [#2502](https://github.com/Fiestaboard/FiestaBoard/pull/2502) [`566125d`](https://github.com/Fiestaboard/FiestaBoard/commit/566125d84af677277ef9dac3a310e9d0dbc656cc) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Refresh Schedule with responsive day, list and week views and read-only previews of what a display will show at a chosen time.

- [#2507](https://github.com/Fiestaboard/FiestaBoard/pull/2507) [`c5a403f`](https://github.com/Fiestaboard/FiestaBoard/commit/c5a403f730fdb92be91fab48565a9f3242f8e6af) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Present Settings in individual responsive panels, clarify browser and hub preference scope, and add a FiestaBot section that explains currently supported behavior.

- [#2505](https://github.com/Fiestaboard/FiestaBoard/pull/2505) [`1307989`](https://github.com/Fiestaboard/FiestaBoard/commit/1307989f0b36dfc8b2fb1e9e1dc7e3d4ff3d51d8) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Add atomic, display and session scoped cancellation receipts for restoring a temporary override without replacing newer display changes or extending its original expiry.

- [#2499](https://github.com/Fiestaboard/FiestaBoard/pull/2499) [`e83731f`](https://github.com/Fiestaboard/FiestaBoard/commit/e83731f19c8a45f3e2425d96dd9507e58b11b3fd) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Group Displays by health and show the selected display’s preview, settings, playback and diagnostics beside the list on larger screens.

- [#2532](https://github.com/Fiestaboard/FiestaBoard/pull/2532) [`6098848`](https://github.com/Fiestaboard/FiestaBoard/commit/60988488396a4837ab919d5177e2d659d1b8b157) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Home explains why "Show again" is unavailable while a display is paused, quotes held messages with each language's quotation marks, and no longer starts the out-of-sync sentence with a stray space. Plural selection falls back to English rules instead of failing on an unknown language tag.

## 11.0.0-alpha.7

### Patch Changes

- [#2522](https://github.com/Fiestaboard/FiestaBoard/pull/2522) [`e5194ec`](https://github.com/Fiestaboard/FiestaBoard/commit/e5194ec28324e0b892203edec25ff879a378ea2b) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Correct localized Collection rule counts and place the tablet preview immediately after the selection-mode chips.

## 11.0.0-alpha.6

### Minor Changes

- [#2524](https://github.com/Fiestaboard/FiestaBoard/pull/2524) [`b5cad79`](https://github.com/Fiestaboard/FiestaBoard/commit/b5cad79d2685cd940ab402a15638d205ed893e1a) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Add opt-in browser push settings, safe notification routing, sign-out cleanup and feature-detected app attention badges. Clearly distinguish account consent, browser permission and enrollment, and keep automatic alert categories unavailable until hub event sources are implemented.

### Patch Changes

- [#2498](https://github.com/Fiestaboard/FiestaBoard/pull/2498) [`2e072a2`](https://github.com/Fiestaboard/FiestaBoard/commit/2e072a22261c4d212f38a367a41939f5585230dc) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Restore Home's supporting pane with the hub's next change, other displays, and a Schedule Mode switch with Undo.

- [#2523](https://github.com/Fiestaboard/FiestaBoard/pull/2523) [`484854f`](https://github.com/Fiestaboard/FiestaBoard/commit/484854f9db581a696e2bb5dd87abc6021ba117f4) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Refresh the v11 preview guides to the published alpha.5 image and clarify built-in HTTPS and web push availability.

## 11.0.0-alpha.5

### Minor Changes

- [#2504](https://github.com/Fiestaboard/FiestaBoard/pull/2504) [`e779041`](https://github.com/Fiestaboard/FiestaBoard/commit/e779041f7ebd074cb57985413d7c3dcc062fb5f6) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Align first-run setup and display connection with the universal web design, add single-use phone QR pairing and phone/TV sign-out controls, and improve TV approval and password recovery.

### Patch Changes

- [#2517](https://github.com/Fiestaboard/FiestaBoard/pull/2517) [`ae12478`](https://github.com/Fiestaboard/FiestaBoard/commit/ae12478c10eb966327bbda7ca437f2f9de43e517) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Harden hub HTTPS startup with nginx configuration validation and Mozilla intermediate TLS 1.2 ciphers. Make generated public certificates mode 0644 while keeping private keys mode 0600.

- [#2504](https://github.com/Fiestaboard/FiestaBoard/pull/2504) [`e779041`](https://github.com/Fiestaboard/FiestaBoard/commit/e779041f7ebd074cb57985413d7c3dcc062fb5f6) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Match setup and TV approval spacing, display-picker layout, session surfaces, and phone sign-out sheets to the live web designs.

- [#2519](https://github.com/Fiestaboard/FiestaBoard/pull/2519) [`1a1bb61`](https://github.com/Fiestaboard/FiestaBoard/commit/1a1bb615f36d082d5898a1e6bddb21c357ffc897) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Document the v11 Alpha preview, release-channel availability, and 10.x upgrade and recovery procedures, including backup limits and sign-in consequences. Correct outdated update and rollback guidance.

## 11.0.0-alpha.4

### Minor Changes

- [#2500](https://github.com/Fiestaboard/FiestaBoard/pull/2500) [`0441ad7`](https://github.com/Fiestaboard/FiestaBoard/commit/0441ad75e0238d24b40f79cb3c580d23be566f9f) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Arrange the Collection editor with selection-mode chips, header actions, a saved-state preview, accessible rule menus and keyboard ordering.

- [#2509](https://github.com/Fiestaboard/FiestaBoard/pull/2509) [`67d7c40`](https://github.com/Fiestaboard/FiestaBoard/commit/67d7c4086f4fa548c2f376df625cf0a6e702045c) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Expose a versioned, ETag-cacheable catalog of built-in LED fonts and character sets at `GET /v1/render-assets` for native renderers, with recorded response fixtures and a native-client contract guide.

- [#2510](https://github.com/Fiestaboard/FiestaBoard/pull/2510) [`bfd7ff5`](https://github.com/Fiestaboard/FiestaBoard/commit/bfd7ff5362f0b52e7600682bd810b59d1f431883) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Add optional built-in HTTPS with persistent self-signed or operator-supplied certificates, preserving local HTTP and Home Assistant ingress.

- [#2514](https://github.com/Fiestaboard/FiestaBoard/pull/2514) [`a9bc76b`](https://github.com/Fiestaboard/FiestaBoard/commit/a9bc76bd69e4ccda9836358167c4b3b39dda46c5) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Add secure web push enrollment and delivery with persistent private VAPID keys,
  independent account/browser consent, bounded retries, expired subscription cleanup,
  and a rate-limited current-browser test. Expose an honest event-source capability
  list for the upcoming notification settings UI.

- [#2513](https://github.com/Fiestaboard/FiestaBoard/pull/2513) [`98c0acb`](https://github.com/Fiestaboard/FiestaBoard/commit/98c0acb25da7620dcc59a01d93bee9decb72fc93) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Add bounded formula execution traces and per-cell template source maps to render previews for web and native editor debugging.

### Patch Changes

- [#2508](https://github.com/Fiestaboard/FiestaBoard/pull/2508) [`85747d1`](https://github.com/Fiestaboard/FiestaBoard/commit/85747d1739aa32370bd0473191bcd9ee1573c18e) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Fix status polling at temporary-message expiry so each board's pending return to its schedule, saved page, or blank display is preserved for the display engine.

- [#2472](https://github.com/Fiestaboard/FiestaBoard/pull/2472) [`9101893`](https://github.com/Fiestaboard/FiestaBoard/commit/91018934a676b4d9b1ce7fee622ece1bd5f3d603) Thanks [@roblesi](https://github.com/roblesi)! - Docker Compose no longer fails with "env file .env not found" on a fresh install: the `.env` file is now optional, and an unset `FIESTAUPDATER_TOKEN` no longer prints a warning.

## 11.0.0-alpha.3

### Patch Changes

- [#2496](https://github.com/Fiestaboard/FiestaBoard/pull/2496) [`35adf28`](https://github.com/Fiestaboard/FiestaBoard/commit/35adf287ed9ade0d24cc099ad6e4944509f6a0a8) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Keep release-channel exploration separate from confirmation, show channel choices
  while cached version discovery loads, and translate the remaining chooser text.

## 11.0.0-alpha.2

### Minor Changes

- [#2493](https://github.com/Fiestaboard/FiestaBoard/pull/2493) [`3f0a6da`](https://github.com/Fiestaboard/FiestaBoard/commit/3f0a6da0d411f8c556dabad66ddc6011192daaf6) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Choose Stable, Beta, or the isolated FiestaBoard 11 Alpha preview from Settings, with available versions, explicit migration confirmation, and automatic recovery backups. Enable channel switching and isolated in-app updates on v11 previews.

### Patch Changes

- [#2494](https://github.com/Fiestaboard/FiestaBoard/pull/2494) [`8eb393b`](https://github.com/Fiestaboard/FiestaBoard/commit/8eb393b33946613895ab3d8f3efa11a896ff32c4) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Make the slow-plugin circuit-breaker regression deterministic under parallel test load while retaining late-data delivery and quarantine assertions.

## 11.0.0-alpha.1

### Minor Changes

- [#2477](https://github.com/Fiestaboard/FiestaBoard/pull/2477) [`8224f9e`](https://github.com/Fiestaboard/FiestaBoard/commit/8224f9e47f47aacb33de62f6e7bd3af1a39824cb) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Reorder the pages in a Collection by dragging the grip, from the keyboard (Space to lift, the arrow keys to move, Space to drop, Esc to cancel) or with Move up and Move down; every step is announced, and it works with touch.

- [#2478](https://github.com/Fiestaboard/FiestaBoard/pull/2478) [`e579d07`](https://github.com/Fiestaboard/FiestaBoard/commit/e579d0749324c8df2dee708dc44000ff4ca78ddf) Thanks [@jeffredodd](https://github.com/jeffredodd)! - The page editor lists its keyboard shortcuts: press `?` (outside a text field), or use the new Shortcuts button or the "? All shortcuts" hint, to see Undo, Redo, Apply a formula, Close a picker and Leave draw mode, with ⌘ on a Mac and Ctrl elsewhere.

- [#2482](https://github.com/Fiestaboard/FiestaBoard/pull/2482) [`1317f01`](https://github.com/Fiestaboard/FiestaBoard/commit/1317f0131681282430e0356f6e52869a18ecccdb) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Board previews no longer shrink to fit: a board wider than its space keeps its real tiles and scrolls sideways inside its frame, with a fade on the side that has more board, snapping to each Note or column, a "Note 1 of 3" position readout, and ← → / Home / End keys. Fit (press F) is still there as an overview, and your choice lasts the session. Board sizes now read columns × rows ("45 × 3"). The editor shortcut list now includes these preview keys when the split-flap viewport is active. Home board actions sit in the card header so they remain clear of the preview size controls.

- [#2481](https://github.com/Fiestaboard/FiestaBoard/pull/2481) [`2b3311e`](https://github.com/Fiestaboard/FiestaBoard/commit/2b3311e57c7ea75bebdcabd436e86267184ea61f) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Home is rebuilt on the canonical design: one "Compose a message" button in the page header, a Now showing card with Change Page, and both verbs ending in the same duration step (15 min, 1 hr, until the Schedule's next change, until you cancel) and Show now. An Override shows its badge, a countdown and what happens next, with Cancel override and Undo; every display gets its own timed override; and the board has a context menu (right-click, Shift+F10, long-press or the ⋯ button) with Change Page, Compose, Edit page, Copy as text, Refresh and Pause. The old Force Set durations (5 and 30 minutes, and a custom 1–480 minutes) are gone, and Compose in Schedule Mode now holds a message for a set time by default (until the next Schedule change, or 1 hour) instead of until you cancel it.

- [#2480](https://github.com/Fiestaboard/FiestaBoard/pull/2480) [`46053fa`](https://github.com/Fiestaboard/FiestaBoard/commit/46053fa4ae9c3c5751d399d516fe8fc53eeae66f) Thanks [@jeffredodd](https://github.com/jeffredodd)! - New navigation: phones get a bottom tab bar (Home, Pages, Schedule, Displays, More) and tablets get the side rail from 768 px; Settings, Staff Picks and Help & Docs join the nav, Integrations shows a badge when one needs setting up, and Settings is now a list of sections (You, and Hub: Network, AI provider, System & backups, Language & time), each with its own address.

- [#2484](https://github.com/Fiestaboard/FiestaBoard/pull/2484) [`687b0e4`](https://github.com/Fiestaboard/FiestaBoard/commit/687b0e484699d0ddd12250606c758ba7c7c1694f) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Offer installation after a successful save or several sends, with a 30-day snooze. On secure origins that serve the public app shell, allow offline startup with a clearly labelled last-known board; sign-out clears that account’s local frames. Explain HTTPS requirements on insecure addresses and keep authenticated API responses out of the service-worker cache.
  
  Count the shared Home flow's successful timed Show now actions toward the install offer after stack integration.

- [#2479](https://github.com/Fiestaboard/FiestaBoard/pull/2479) [`cfc3b58`](https://github.com/Fiestaboard/FiestaBoard/commit/cfc3b5804b052c79b997b83e44987189779e7d30) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Home and each display's page now show one status banner with its fix: you're offline, can't reach your hub, a display offline (with when it was last connected), paused (Resume), Silence Schedule, or no TV showing a FiestaPanel. The display switcher shows the hub's address and whether it is online, remote or can't be reached.

### Patch Changes

- [#2491](https://github.com/Fiestaboard/FiestaBoard/pull/2491) [`79939b6`](https://github.com/Fiestaboard/FiestaBoard/commit/79939b61ed4848f763ce87f64e2b1e4a1cca1343) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Keep the full release test suite on secure browser origins while retaining plain HTTP PWA checks, and isolate panel migration tests from in-flight display polling between tests.

## 11.0.0-alpha.0

### Major Changes

- [#2445](https://github.com/Fiestaboard/FiestaBoard/pull/2445) [`1e1a4a2`](https://github.com/Fiestaboard/FiestaBoard/commit/1e1a4a25ead5d14fa6b5c92976ea0e55fdcd9138) Thanks [@jeffredodd](https://github.com/jeffredodd)! - FiestaBoard 11: the universal redesign. One design for the web app, TVs, phones and tablets, with a clearer layout, touch-friendly editing, and live board status on every screen.

### Minor Changes

- [#2456](https://github.com/Fiestaboard/FiestaBoard/pull/2456) [`2e23b3c`](https://github.com/Fiestaboard/FiestaBoard/commit/2e23b3ca97a00a98205aa736c0a10fcf98bbcd31) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Each display now says what it can draw — lowercase, colored text, highlights, color tiles, icons, any color, solid shapes and pixel drawings — along with its color model, LED text size and icon names, so editors can offer only the tools that display supports.

- [#2469](https://github.com/Fiestaboard/FiestaBoard/pull/2469) [`23bf754`](https://github.com/Fiestaboard/FiestaBoard/commit/23bf754944be6f0c893c2998eb648a9234b18c09) Thanks [@jeffredodd](https://github.com/jeffredodd)! - The setup wizard can now tell when a display you are adding is already set up on this hub (the same address, cloud key or note-array token).

- [#2455](https://github.com/Fiestaboard/FiestaBoard/pull/2455) [`67f477d`](https://github.com/Fiestaboard/FiestaBoard/commit/67f477d18ca97665c37e9d8ab662a8f3ec97feb0) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Each display now reports its health: when the hub last reached it and how fast, when a frame last landed, and why the last attempt failed (a refused token, an unreachable board, a timeout, and so on).

- [#2432](https://github.com/Fiestaboard/FiestaBoard/pull/2432) [`c7ae9ec`](https://github.com/Fiestaboard/FiestaBoard/commit/c7ae9ec81d53cf0d9a354d4a7aa1e5c9a37e9c33) Thanks [@jeffredodd](https://github.com/jeffredodd)! - The iOS and Android apps can now sign in with a scoped, revocable control token that reaches only the routes the phone apps need, never account, backup, system or install settings; the "TV sign-in" switch is now "Device sign-in" and covers TVs and phones.

- [#2449](https://github.com/Fiestaboard/FiestaBoard/pull/2449) [`b472f19`](https://github.com/Fiestaboard/FiestaBoard/commit/b472f196b79d1b1c00da99ae770715a6258a4d12) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Phones can pair with a one-time QR code from a signed-in browser, approve a TV's sign-in code, and return to the FiestaBoard app after connecting an integration's account.

- [#2452](https://github.com/Fiestaboard/FiestaBoard/pull/2452) [`33772d2`](https://github.com/Fiestaboard/FiestaBoard/commit/33772d26a0532c3920467c0cb81f1ba07eeb9ad6) Thanks [@jeffredodd](https://github.com/jeffredodd)! - `GET /v1/boards/{board}` now says when each display is next expected to change, why, and to which page when that can be known, so apps can show a countdown without re-implementing the schedule.

- [#2463](https://github.com/Fiestaboard/FiestaBoard/pull/2463) [`73dd91a`](https://github.com/Fiestaboard/FiestaBoard/commit/73dd91a1f52c34d925dc3a7a2705475c69985758) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Pages can have a draft that no board shows until you save it to the board, and keep their last 20 saved versions, including how a page looked before its first edit on this release: restore any of them into the draft from the page's history.

- [#2466](https://github.com/Fiestaboard/FiestaBoard/pull/2466) [`bb350b6`](https://github.com/Fiestaboard/FiestaBoard/commit/bb350b6c8ae83842f6a6eb0da23de17667d062dc) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Copy a page for another display at that display's size, with a report of what was cut, and organize pages with tags you can filter the library by. Tags can include emoji, joined ones too. In the API, pages gain an optional `tags` list (on `/v1` as well); a request whose `tags` isn't a list of tags is now rejected.

- [#2464](https://github.com/Fiestaboard/FiestaBoard/pull/2464) [`1d2a871`](https://github.com/Fiestaboard/FiestaBoard/commit/1d2a871263a67bd5bde9307ff5958e63da8d6cc8) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Each page now remembers what happened the last 20 times it was sent: shown on which display, refused while paused or during Silence, held for later, or failed and why. Repeats of the same thing, such as a display that keeps failing or a live page that lands every minute, show as one entry with a count and the last time, so they never push the rest out.

- [#2454](https://github.com/Fiestaboard/FiestaBoard/pull/2454) [`bfaf71b`](https://github.com/Fiestaboard/FiestaBoard/commit/bfaf71b1e7eec24b0663871e7d0eeb13b4e3220d) Thanks [@jeffredodd](https://github.com/jeffredodd)! - TV panel status now says when the display is next expected to change and why, so the TV apps can show "Schedule · next change 9:00 PM".

- [#2431](https://github.com/Fiestaboard/FiestaBoard/pull/2431) [`a29fe69`](https://github.com/Fiestaboard/FiestaBoard/commit/a29fe69fc643a2837ba3d9494b6bd2b4b058e6a5) Thanks [@jeffredodd](https://github.com/jeffredodd)! - `GET /panel/{id}` reports the board's status (override, silence, pause, schedule) so TV viewers can show a status chip.

- [#2470](https://github.com/Fiestaboard/FiestaBoard/pull/2470) [`b422f8e`](https://github.com/Fiestaboard/FiestaBoard/commit/b422f8ebe0899664f54d0cf93062521c79804301) Thanks [@jeffredodd](https://github.com/jeffredodd)! - A lost password can now be reset without deleting your account: run `python -m src.auth.password_reset` inside the container for a one-time code, then choose a new password with it.

- [#2451](https://github.com/Fiestaboard/FiestaBoard/pull/2451) [`7c3332c`](https://github.com/Fiestaboard/FiestaBoard/commit/7c3332cf404e191636ec24f0f3b6ee1e177938e9) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Timed overrides now work per display: each display has its own override, with a start time, and a timed message can be sent to any display, not only the primary one.

- [#2450](https://github.com/Fiestaboard/FiestaBoard/pull/2450) [`3598591`](https://github.com/Fiestaboard/FiestaBoard/commit/3598591f1dac633c3b489d3f55eff13bd9349151) Thanks [@jeffredodd](https://github.com/jeffredodd)! - The phone app can list the TVs signed in to your hub, see which ones it approved, and sign a TV out.

- [#2458](https://github.com/Fiestaboard/FiestaBoard/pull/2458) [`569ac75`](https://github.com/Fiestaboard/FiestaBoard/commit/569ac7593b08d8e88db0d94031a6152ef794d917) Thanks [@jeffredodd](https://github.com/jeffredodd)! - The template preview can now explain itself: what each formula evaluated to (or why it failed), and for each line how many rows it wanted, how many fit on the board, and which line or board edge cut the rest off. Template checks also flag lines that fall past the board's last row.

- [#2460](https://github.com/Fiestaboard/FiestaBoard/pull/2460) [`c58d6ce`](https://github.com/Fiestaboard/FiestaBoard/commit/c58d6cee1d86f4125538823079e5f8d788eb7382) Thanks [@jeffredodd](https://github.com/jeffredodd)! - The template preview can now show "what if": sample values for any variable, a data source treated as missing (so fallbacks can be checked), the board at another time of day, or the last data the hub fetched without waiting for a refresh. Previews never reach a real board.

- [#2462](https://github.com/Fiestaboard/FiestaBoard/pull/2462) [`119c0ce`](https://github.com/Fiestaboard/FiestaBoard/commit/119c0cee8fd566dc7dc4258fc6808d4cccd97074) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Schedules and collections can now be tested ahead of time: ask which page a display's schedule shows at any time of day, or which page a collection's rules would pick at a given time and with sample data, including a timeline of how its choice changes over the day. Rules that read the Date & Time plugin are answered for the time asked, and a timeline too costly to simulate in full says where it stopped.

- [#2467](https://github.com/Fiestaboard/FiestaBoard/pull/2467) [`23c5474`](https://github.com/Fiestaboard/FiestaBoard/commit/23c54741a2f9fcad374f98ede19b548f828c5064) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Signed-in devices now shows which phone or browser approved each TV, and signing out a phone can also sign out the TVs it approved.

- [#2457](https://github.com/Fiestaboard/FiestaBoard/pull/2457) [`a944f23`](https://github.com/Fiestaboard/FiestaBoard/commit/a944f231e9016eeb3ff56706a0d729e0bb4e5974) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Template checks now measure each line at the real width of the display it is for — a Note, a note array, a FiestaPanel, a Pixoo or a TC001 — instead of always 22 columns, honor lines set to wrap, and say what kind of problem each one is.

- [#2433](https://github.com/Fiestaboard/FiestaBoard/pull/2433) [`e516d80`](https://github.com/Fiestaboard/FiestaBoard/commit/e516d80078c41f570243d1175e940baea9786477) Thanks [@jeffredodd](https://github.com/jeffredodd)! - The signed-in devices API (`GET /api/auth/sessions`) now reports when each TV last showed a FiestaPanel, and which panels it showed, for "Shown on" lists in the apps.

### Patch Changes

- [#2471](https://github.com/Fiestaboard/FiestaBoard/pull/2471) [`05c0f1f`](https://github.com/Fiestaboard/FiestaBoard/commit/05c0f1f1f4cda1bd116c77464bfb68c27358aeea) Thanks [@jeffredodd](https://github.com/jeffredodd)! - The web app now builds against @fiestaboard/ui 8.17.0-alpha.2. The alpha adds the touch-size, tint, display-type and editor-mono design tokens and the new redesign components that later updates build on. This makes the released redesign primitives available to subsequent web updates.

- [#2459](https://github.com/Fiestaboard/FiestaBoard/pull/2459) [`34c8916`](https://github.com/Fiestaboard/FiestaBoard/commit/34c8916dd8f4682c5be348dddad5c06479e2339f) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Formulas can no longer build text longer than 64 KB (for example by nesting REPT); such a formula now shows #VALUE instead of tying up the hub for a minute and using gigabytes of memory.

- [#2461](https://github.com/Fiestaboard/FiestaBoard/pull/2461) [`50ca9a9`](https://github.com/Fiestaboard/FiestaBoard/commit/50ca9a99b2781d90a79e0beaf0d858d5270f6dd6) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Formulas now have a work limit: one that would take the hub minutes (for example by nesting FILTER over very long lists) shows #VALUE within a fraction of a second, and a formula nested too deeply shows #SYNTAX instead of breaking the whole preview.

- [#2438](https://github.com/Fiestaboard/FiestaBoard/pull/2438) [`808913a`](https://github.com/Fiestaboard/FiestaBoard/commit/808913a4219f826eea3bab9eac35c8f332df084b) Thanks [@jeffredodd](https://github.com/jeffredodd)! - MQTT's `current_page` sensor now reports the page the board is actually showing (including scheduled, collection, override and silence pages) and publishes as soon as the page changes, instead of reporting the manually selected page.

- [#2468](https://github.com/Fiestaboard/FiestaBoard/pull/2468) [`7b1b9a6`](https://github.com/Fiestaboard/FiestaBoard/commit/7b1b9a65b54cbab4cc8254b1f6daf7d15046f594) Thanks [@jeffredodd](https://github.com/jeffredodd)! - The "Connect a phone" QR code no longer points the phone at localhost when the web app is open on the hub itself; it uses the hub's network name or address instead.

- [#2453](https://github.com/Fiestaboard/FiestaBoard/pull/2453) [`f488d5e`](https://github.com/Fiestaboard/FiestaBoard/commit/f488d5e1551aa6788a3eed55b9159205573f4dbe) Thanks [@jeffredodd](https://github.com/jeffredodd)! - A display's quiet hours can no longer be reset to the install-wide defaults by the deferred silence migration, whatever order startup and edits happen in.

- [#2487](https://github.com/Fiestaboard/FiestaBoard/pull/2487) [`7ea53ae`](https://github.com/Fiestaboard/FiestaBoard/commit/7ea53ae987feeb83eafc23fe26fcdb6db6c8093b) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Keep v11 preview installs isolated from stable and beta updates; update previews manually with the v11-alpha Docker tag.

- [#2489](https://github.com/Fiestaboard/FiestaBoard/pull/2489) [`a774a6e`](https://github.com/Fiestaboard/FiestaBoard/commit/a774a6ec14bb88d5be94f7726662e3f799e4285d) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Keep stable and beta update test scenarios independent of the release version, and verify them alongside v11 update isolation under a v11 alpha package version.

## 10.3.3

### Patch Changes

- [#2428](https://github.com/Fiestaboard/FiestaBoard/pull/2428) [`51f4d33`](https://github.com/Fiestaboard/FiestaBoard/commit/51f4d333c93c54e7717809eb32a4c3578134b1ee) Thanks [@fiestaboard-ci-bot](https://github.com/apps/fiestaboard-ci-bot)! - Upgrade the FiestaUI design system (`@fiestaboard/ui`) to v8.16.0.
