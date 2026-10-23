<!-- cspell:ignore Pixoo Divoom tvOS AWTRIX WLED -->

# Display setup and presentation review

Reviewed revision: `next` at `18c4ba43a`, October 22, 2026. This review covers the first-run wizard, **Displays → Add a display**, the display marketplace, and how displays are previewed. It asks two questions. First, does setup treat every display as a plugin, or does it still assume a Vestaboard? Second, will the way devices are shown still work with ten display plugins instead of three?

The findings come from reading the code. Findings 1, 2 and 4 were re-checked against the source before this was written. Nothing here has been fixed yet.

## Summary

Output plugins (v10) did the hard part. Every display is a plugin, the core no longer talks to Vestaboard directly, and a display plugin can declare its own settings screen, device models and actions. Setup has not caught up. The wizard and the **Add a display** dialog still branch on `vestaboard` and `fiestapanel` by id. They also show displays as a flat, text-only list, and nothing tells a new user which display they have.

One finding loses data and should be fixed before v10 ships: re-running the wizard and picking Vestaboard deletes every other display.

## Current flow

1. **First run** is decided by `shouldShowWizard` (`web/src/lib/setup-detection.ts`). It calls `determine_config_validity` (`src/config_api/service.py:97–171`), which still reads the legacy Vestaboard keys first.
2. **Choose a display** (`step-choose-output.tsx`). `GET /outputs/available` (`src/outputs/install.py:74–139`) lists installed displays, then the seeded displays from `outputs.lock.json`, then registry entries with `plugin_type: "output"`. Each is a one-column `ToggleCard` with an icon from a closed list.
3. **Set up** branches by id (`setup-wizard.tsx:169–248`):
   - `fiestapanel` goes to `step-panel-setup.tsx`.
   - Every other plugin goes to `step-output-plugin.tsx`, which is fully driven by the manifest. It installs the plugin, then shows a name, a device-model select, the plugin's settings screen and its actions.
   - `vestaboard` goes to `step-board-setup.tsx`. That step adds Flagship/Note cards, color swatches and the code-62 choice, all hardcoded in core, on top of the plugin's settings screen.
4. **Data sources**, then **finish**, which sends a welcome message.

**Add a display** (`add-display-dialog.tsx`) reuses step 2, but sets up Vestaboard differently from the wizard. It shows only shape buttons and no connection step.

## Findings

| # | Severity | Where | Problem | Recommendation |
|---|---|---|---|---|
| 1 | **Data loss** | `web/src/components/wizard/step-board-setup.tsx:92–105`; `src/settings/routes.py:1111` | The Vestaboard step saves with `updateBoardSettings({ boards: [oneBoard] })`, and `PUT /settings/board` treats `boards` as the full list. Re-running the wizard (offered from Settings and Home) and picking Vestaboard deletes every Pixoo, TV and other board. The same thing happens if you go back after creating a Pixoo and then pick Vestaboard. | Create the board with `POST /outputs/vestaboard/boards`, like every other output. The wizard should never PUT the whole list. Add a regression test that starts with two boards and re-runs the Vestaboard step. |
| 2 | Broken | `src/settings/service.py:318–328` | `BoardSettings.__post_init__` always invents a Vestaboard Flagship called "My Board" when the list is empty. There is no real zero-display state. Skipping the wizard leaves a broken Vestaboard card on **Displays**, and the empty state in `displays._index.tsx` can never show. Non-Vestaboard paths need the `default-board.ts` placeholder heuristic to clean up after it. | Allow `boards: []`, and make the empty **Displays** page a clear "Add your first display" call to action. Once nothing invents a placeholder, remove the placeholder heuristics. This changes stored settings, so it needs a settings migration. |
| 3 | Confusing | `setup-wizard.tsx:89–97, 169–248`; `step-welcome.tsx:36–146`; `add-display-dialog.tsx:83–161` | There are three setup UIs keyed on display id. Vestaboard setup differs between the wizard and **Add a display**. Wizard state carries Vestaboard-only fields (`device_type`, `board_color`, `code62_glyph`). | Move the Vestaboard shape, housing color and code-62 choice into the Vestaboard plugin's manifest (`settings_schema` and `device_models`). Then delete the id branches, so every display goes through the generic `step-output-plugin` step. Keep one optional manifest "setup flavor" for pull displays like FiestaPanel, which show an address instead of testing a connection. |
| 4 | Won't scale | `web/src/components/device-preview.tsx:59`; `display-live-preview.tsx:36–60`; FiestaUI device-model schema | Previews are binary: LED models go to `DisplayPreview`, and anything else falls back to the split-flap renderer. A TV card on **Displays** looks like a Vestaboard, and a future e-ink or LCD display has nowhere to go. The FiestaUI schema closes `technology` to `split_flap` and `led_matrix`, although `plugin-guide.md` already mentions `screen`. | Make `DisplayPreview` the only preview entry point, dispatching on `model.technology`, with a fallback for unknown technologies. Draw FiestaPanel boards inside `TvFrame` in list cards. Widen the schema enum when the first non-flap, non-LED display arrives. |
| 5 | Won't scale | `step-choose-output.tsx:76–104`; `display-marketplace.tsx:104–237` | The picker is one flat column of text cards, with no search, grouping or pictures. With ten or more displays it becomes a wall of names. | Group by technology (split-flap, LED matrix, TV, other) and then by family. Add search once there are more than about eight entries, and put a "Found on your network" group on top (see 8). |
| 6 | Won't scale | `web/src/components/displays/output-boards.tsx:80–91` | Icons come from a closed map of six lucide names. Any other icon a plugin declares silently becomes a generic monitor. | Let a manifest ship an image (an SVG in the plugin repo), or accept any lucide name, and document the allowed values. |
| 7 | Won't scale | `src/outputs/install.py:120–137`; `web/src/lib/api/outputs.ts:68–86` | An uninstalled display (seeded or in the registry) exposes only a name, description and icon. The picker can't group, preview or picture it until after install. | Carry `technology`, `family`, model labels and an image on registry entries (generated by the registry build) and on seeded listings. |
| 8 | UX gap | `src/outputs/hooks.py:204`; `src/outputs/actions.py:132` | Discovery runs only after you pick a display type, inside that plugin's settings screen. Someone who doesn't know what they own, or owns several, gets no help. The loading text "Looking for displays…" suggests a scan that isn't happening. | Add a "Scan my network" step. It runs every installed or seeded display's `discover` action at once, with the browser's address as the hint, and pre-selects what it finds. Until then, change the copy to "Loading displays…". |
| 9 | Confusing | `step-panel-setup.tsx:80–97` | The TV path ends with a plain-text address. There's no QR code (the panel's own settings page has one) and no mention of the native TV apps. | Reuse the QR code and copy button from `FiestaPanelSettings`. Once the apps ship, add "Open in the FiestaBoard TV app". Drive that from the manifest (for example a `viewer_apps` list) with a "Coming soon" state until then. |
| 10 | Confusing | `step-board-setup.tsx:146–149` | If the Vestaboard plugin fails to load, the user sees "connection test failed". | Show a specific "Vestaboard support didn't load" error with a retry. |
| 11 | Copy | `en.json` `wizard.stepDescriptions.chooseOutput`, `welcome.sendWelcomeDescription`; `setup-wizard.tsx:52–61` | The copy says displays can be added "later in **Settings**", but they are added in **Displays**. The welcome text and the wizard's backdrop assume a colorful split-flap board. | Point to **Displays**. Use neutral copy, or pick the backdrop based on the display chosen. |
| 12 | Won't scale | `src/config_api/service.py:120–134`; `src/devices.py:17–37`; `src/board_api/welcome.py:68–85` | First run is still decided from Vestaboard keys. Core's shape vocabulary is `flagship`, `note`, `note_array` and `panel`, and every plugin board is forced to `panel`. Welcome templates branch on Vestaboard shapes. | Decide first run by "has a board whose status is configured". Treat `device_type` as legacy and use `device_model` plus geometry everywhere new. |
| 13 | Won't scale | `page-builder.tsx`, `pages._index.tsx`, `board-dimensions.ts`, `display-settings.tsx`, `picks.tsx` | These files reason in Flagship, Note, Note array and panel terms, with 11–27 hardcoded references each. | Move them onto model-geometry helpers a file at a time. Nothing breaks today, so do it when you touch each file. |
| 14 | Docs | `docs/setup/*`, `docs/intro.md` | The getting-started docs assumed a Vestaboard API key. No user doc mentioned the Pixoo. | **Addressed alongside this review:** a new `docs/displays/` section, plus display-neutral wording in the intro, Quick Start, Beginner's Guide and First 10 Minutes. Still open: surface each display plugin's own `docs/SETUP.md` in the add flow and on its marketplace card (a manifest `setup_doc` field). |
| 15 | Minor | `setup-wizard.tsx:81–84`; `step-output-plugin.tsx:99` | Going back and picking another display leaves the first board behind, orphaned. | Offer to remove it, or reuse it. |
| 16 | Minor | `step-choose-output.tsx` | A display plugin incompatible with this FiestaBoard (`output_api`) is only found out at install time. | Show a compatibility state on the card from registry metadata. |

## How devices should be shown

The goal is that the tenth display plugin looks as good as the first three, with no core changes. That means everything the picker, cards and previews need comes from the plugin's manifest, and core holds no per-display knowledge.

What a display plugin should declare, in addition to today's `device_models` and `settings_schema`:

| Field | Used for |
|---|---|
| `technology` (from its device models) | Grouping in the picker and marketplace, and choosing the preview renderer |
| `family` | Second-level grouping, such as Vestaboard, Divoom or AWTRIX |
| `image` | Picker and marketplace thumbnail: a photo or drawing of the device |
| `setup_doc` | A "Setup guide" link in the add flow and on the marketplace card |
| `setup_flavor` | `push` (test a connection, the default) or `pull` (show an address and QR code, like FiestaPanel) |
| `viewer_apps` | Optional native apps, each with a state (available or coming soon) and a link |

The picker then becomes:

1. **Found on your network.** Displays that `discover` found, pre-selected.
2. **Split-flap**, **LED matrix**, **TV**, and **Other**. Each group lists its families, with a thumbnail, a live preview of the device's grid, and a state badge where one applies (New, Coming soon, Not compatible).
3. **Find more displays** in the registry, plus **Bring your own display** (git URL).

Badges stay state-only. A device's name, size or family is shown as data on the card, never in a badge.

## Suggested order

| Step | Covers | Size | Where |
|---|---|---|---|
| 1. Stop the wizard replacing the board list, and allow zero boards | 1, 2, 15 | M | FiestaBoard (settings service and migration, wizard, `default-board.ts`) |
| 2. Fix setup copy and the TV step's QR code | 8 (copy only), 9, 10, 11 | S | FiestaBoard web |
| 3. One manifest-driven setup step for every display | 3, 12 | L | FiestaBoard web, plus the Vestaboard output plugin's manifest |
| 4. Presentation metadata and a grouped picker | 5, 6, 7, 16, 14 (`setup_doc`) | M–L | FiestaBoard (`install.py`, manifest schema, picker), the registry build, each output repo |
| 5. Technology-dispatched previews | 4 | M | FiestaUI (`DisplayPreview`, schema), then FiestaBoard `device-preview.tsx` |
| 6. Scan the network first | 8 | M | FiestaBoard (API and wizard) |
| 7. Retire the legacy shape vocabulary | 13 | Ongoing | FiestaBoard, file by file |

Step 1 should land before v10 ships. The other steps don't block v10.
