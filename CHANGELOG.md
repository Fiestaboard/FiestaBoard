# fiestaboard

## 11.0.0-alpha.13

### Minor Changes

- [#2624](https://github.com/Fiestaboard/FiestaBoard/pull/2624) [`e943dbf`](https://github.com/Fiestaboard/FiestaBoard/commit/e943dbf73a7beedc1e2637d8746a96073dddbe10) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Settings › Appearance now has a Boards card with "Animate tile flips" and "Show the color strip on Home" (a strip of the six board colours under the Now showing board, remembered per browser); the other motion settings move to a Motion details panel.

### Patch Changes

- [#2629](https://github.com/Fiestaboard/FiestaBoard/pull/2629) [`3466ab1`](https://github.com/Fiestaboard/FiestaBoard/commit/3466ab1493bdd806a9f0c3302e1bb0315365b871) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Variable chips outside the page editor leave the value off through the kit's own optional value (FiestaUI 8.17.0-alpha.5) instead of hiding an empty segment.

- [#2613](https://github.com/Fiestaboard/FiestaBoard/pull/2613) [`4f0decd`](https://github.com/Fiestaboard/FiestaBoard/commit/4f0decd0c82402e14c0ba5fd58c6148a45c20647) Thanks [@jeffredodd](https://github.com/jeffredodd)! - The rail matches 07a: Collections sits indented under Pages, a hairline separates the main destinations from Integrations and the rest, the collapse handle is a small tab that shows on hover or keyboard focus, and every rail row gets the same visible focus ring. On phones, opening More lights only More and dims the header too. (FiestaUI 8.17.0-alpha.5.)

- [#2589](https://github.com/Fiestaboard/FiestaBoard/pull/2589) [`8a013fb`](https://github.com/Fiestaboard/FiestaBoard/commit/8a013fb176e9e5d332b76b307691f2f499d4be44) Thanks [@jeffredodd](https://github.com/jeffredodd)! - The account menu, About dialog, toasts, Language field and skip link match the design: Theme on one row, Help & Docs in the menu, the wider About dialog, toasts at the top right with a close button, a full-width Language select reading "English (US)", and "Skip to content".

- [#2582](https://github.com/Fiestaboard/FiestaBoard/pull/2582) [`d9b7c7f`](https://github.com/Fiestaboard/FiestaBoard/commit/d9b7c7f5b090616c5af7738abd6aeb2e567ef85d) Thanks [@jeffredodd](https://github.com/jeffredodd)! - The page editor's preview marks where a too-long line is cut, says which integrations are switched off when a page shows ??? for them (with a link to Integrations), and Sample mode now fills in a switched-off integration's example values. `GET /v1/variables` lists installed-but-off integrations with their examples in a new `disabled_plugins` field. A line with `{{fill_space}}` (or another fill) is no longer reported as too long: a fill only takes the room the rest of the row leaves.

- [#2583](https://github.com/Fiestaboard/FiestaBoard/pull/2583) [`aff2665`](https://github.com/Fiestaboard/FiestaBoard/commit/aff2665c382c07111bd4c54e5908dddba32cd022) Thanks [@jeffredodd](https://github.com/jeffredodd)! - The page editor keeps your unsaved edits to a saved page as a draft on the hub and brings them back when you return ("Draft restored · Discard"); the live page changes only when you press Save. The desktop header gains a mono meta line (type and size, display, live and save state), 40 px buttons and no Transition or Delete icons beside the title (Delete is in the Inspector's Page tab), and the leave dialog names the page and the lines you changed.

- [#2607](https://github.com/Fiestaboard/FiestaBoard/pull/2607) [`6f4ede6`](https://github.com/Fiestaboard/FiestaBoard/commit/6f4ede6371e37a8920959bfd6b55459bb852c679) Thanks [@jeffredodd](https://github.com/jeffredodd)! - The desktop formula panel and Inspect follow the design more closely: Code and Builder are tabs, the formula panel has a 2 px formula-blue frame with Cancel and Update formula on the right, code and line numbers share the mono font, and "Line N produces" uses the smaller heading. The template tints the line being edited or inspected. Inspect's outline of the clicked tile and its rows now shows on the preview instead of hiding behind the board, the Inspect pane has a 2 px amber frame, and its steps keep each expression on one line.

- [#2607](https://github.com/Fiestaboard/FiestaBoard/pull/2607) [`6f4ede6`](https://github.com/Fiestaboard/FiestaBoard/commit/6f4ede6371e37a8920959bfd6b55459bb852c679) Thanks [@jeffredodd](https://github.com/jeffredodd)! - The phone Formula sheet follows the design: it is titled Formula, the expression sits in one box with its live result ("→ NICE", "weather.temp is 72 now · 4 of 22 columns"), functions are grouped under category chips with each signature over its description, and one full-width "Insert formula" or "Update formula" button confirms. Opening it from the toolbar no longer puts a "new formula" chip into the page or marks it Unsaved before you confirm.

- [#2609](https://github.com/Fiestaboard/FiestaBoard/pull/2609) [`16a496a`](https://github.com/Fiestaboard/FiestaBoard/commit/16a496a179223fcec089843302d0ba9106f01801) Thanks [@jeffredodd](https://github.com/jeffredodd)! - In the page editor console, the Problems, Warnings and Sent tabs share the width, and a formula problem is titled by its error ("#REF · Row 2") with the reason beside it. The editor timeline's week now runs Monday to Sunday.

- [#2588](https://github.com/Fiestaboard/FiestaBoard/pull/2588) [`04c76b1`](https://github.com/Fiestaboard/FiestaBoard/commit/04c76b1834a77e4f44760acf4a8c1d11913a1a14) Thanks [@jeffredodd](https://github.com/jeffredodd)! - On a phone, tapping a formula chip in the page editor opens the Formula sheet for it again, so an existing formula can be edited or inspected. The tap's own click no longer closes the sheet the moment it opens.

- [#2591](https://github.com/Fiestaboard/FiestaBoard/pull/2591) [`a6c37d6`](https://github.com/Fiestaboard/FiestaBoard/commit/a6c37d6b27a6323a0807d34b7242d1c27852242e) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Variable chips in the template editor match formula chips: the same 22 px atom with a `{}` glyph and, in the page editor, the value the preview sees ("= 62"). Formula and variable chips show their source as written instead of in capitals. A missing variable reads ??? as it does on the board.

- [#2603](https://github.com/Fiestaboard/FiestaBoard/pull/2603) [`6629cec`](https://github.com/Fiestaboard/FiestaBoard/commit/6629cecfe666bd54dba6559adc2c9ceae8709e1a) Thanks [@jeffredodd](https://github.com/jeffredodd)! - A Pages library card's ··· menu follows the design: the page's name, Edit (E), Change Page… to show it now, Add to Schedule, Duplicate (⌘D / Ctrl+D), Export share string, and Pause or Resume the current display. On touch it keeps Delete page… instead of Pause; on a desktop pages are deleted from the editor.

- [#2595](https://github.com/Fiestaboard/FiestaBoard/pull/2595) [`aa9f67c`](https://github.com/Fiestaboard/FiestaBoard/commit/aa9f67c52f3c304b2dba6dd10e3eeeefb9f32988) Thanks [@jeffredodd](https://github.com/jeffredodd)! - The Pages library header and toolbar follow the design: a grid icon and new subtitle, a "Search pages" field with an in-field clear button and no standing help text, a text Grid / List switch shared with Collections, an outline Import button, and sort options with parallel wording that fill the row on a phone.

- [#2587](https://github.com/Fiestaboard/FiestaBoard/pull/2587) [`b8793ee`](https://github.com/Fiestaboard/FiestaBoard/commit/b8793ee5ba6207e0ad59d1c4f12ca87b115378ca) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Compose a message matches its design: the 560 px dialog with a plain message field and a preview that hugs the board, and on a phone a shorter sheet with no display picker and Show now above the fold.

- [#2596](https://github.com/Fiestaboard/FiestaBoard/pull/2596) [`0bd4352`](https://github.com/Fiestaboard/FiestaBoard/commit/0bd43524292c1d0268645a3dedcb0b501ea73edb) Thanks [@jeffredodd](https://github.com/jeffredodd)! - A display's page puts Pause and Change Page… in its header with a size, connection and address line under the name, and the Displays list's detail pane has Change Page… in its header.

- [#2596](https://github.com/Fiestaboard/FiestaBoard/pull/2596) [`0bd4352`](https://github.com/Fiestaboard/FiestaBoard/commit/0bd43524292c1d0268645a3dedcb0b501ea73edb) Thanks [@jeffredodd](https://github.com/jeffredodd)! - A display's Playback tab uses its design's card titles and Silence Schedule wording, without icons in the titles or a colon after "Default page for gaps".

- [#2599](https://github.com/Fiestaboard/FiestaBoard/pull/2599) [`a938af0`](https://github.com/Fiestaboard/FiestaBoard/commit/a938af041fedcca5ce16862aaa1af58d2a837d7a) Thanks [@jeffredodd](https://github.com/jeffredodd)! - At medium width, Home's board hugs its bezel (or fills it when it nearly fits) instead of sitting in a full-width black slab.

- [#2598](https://github.com/Fiestaboard/FiestaBoard/pull/2598) [`d8a0009`](https://github.com/Fiestaboard/FiestaBoard/commit/d8a00092b0eb01351084d8580c6e6c0211f88834) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Home's Now showing card uses 40 px action buttons on wider screens and, on a desktop, names the hub after the display's type and size.

- [#2590](https://github.com/Fiestaboard/FiestaBoard/pull/2590) [`4c1bf0b`](https://github.com/Fiestaboard/FiestaBoard/commit/4c1bf0bc6f7ffdeb879339838d31b4c1c78d0fd7) Thanks [@jeffredodd](https://github.com/jeffredodd)! - The Integrations list sits on the page without a card, with Check for updates under a "…" button, plain "Installed · n" tabs, a compact search, and inset rows led by a status dot.

- [#2590](https://github.com/Fiestaboard/FiestaBoard/pull/2590) [`4c1bf0b`](https://github.com/Fiestaboard/FiestaBoard/commit/4c1bf0bc6f7ffdeb879339838d31b4c1c78d0fd7) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Settings sections read at the design's scale: a smaller section title with the hub under it, compact card titles without icons, and index rows inset in their card without dividers.

## 11.0.0-alpha.12

### Patch Changes

- [#2605](https://github.com/Fiestaboard/FiestaBoard/pull/2605) [`0635c39`](https://github.com/Fiestaboard/FiestaBoard/commit/0635c397a603aac2ad2dff3eebb8b4422e09c559) Thanks [@jeffredodd](https://github.com/jeffredodd)! - When FiestaBot creates a page on a slow device or with a large Pages list, it now always ends on the saved page: if the new editor opens late, the assistant waits for it before typing, so it no longer stops at a "Discard unsaved changes?" dialog.

- [#2579](https://github.com/Fiestaboard/FiestaBoard/pull/2579) [`f567c73`](https://github.com/Fiestaboard/FiestaBoard/commit/f567c733835eeec8399a6b9d7d56c4b32d5fa8d9) Thanks [@jeffredodd](https://github.com/jeffredodd)! - The page editor's preview card is calmer: its header is one row, the target, board size and board colour sit behind the header's "Kitchen · Flagship 22 × 6" meta instead of a third board picker and a separate size row, and edits update the board instantly. A new Replay button plays the split-flap animation on demand.

- [#2581](https://github.com/Fiestaboard/FiestaBoard/pull/2581) [`3b043f9`](https://github.com/Fiestaboard/FiestaBoard/commit/3b043f9b4fb3b6288ce604b86fa4ee96512e5b1a) Thanks [@jeffredodd](https://github.com/jeffredodd)! - The desktop page editor gets the window: the nav collapses to the icon rail while you edit (your own choice comes back when you leave, and a toggle made in the editor becomes your choice), the Explorer can be hidden, starts closed for single Flagship and Note pages, and now shows only the open page's boards, parts and snippets instead of a list of every page, and the page name always keeps room beside the header actions.

- [#2584](https://github.com/Fiestaboard/FiestaBoard/pull/2584) [`10e5a13`](https://github.com/Fiestaboard/FiestaBoard/commit/10e5a133e197b3ab9dbde6102f9dcd0dbf05205c) Thanks [@jeffredodd](https://github.com/jeffredodd)! - The desktop page editor is one workspace: the Explorer, the template with its Console and Timeline, and the preview with its Inspector sit in three columns under a header and toolbar that stay put while you scroll; a new page has the same layout as a saved one, so the first save moves nothing; and Tab goes column by column.

- [#2576](https://github.com/Fiestaboard/FiestaBoard/pull/2576) [`12a4352`](https://github.com/Fiestaboard/FiestaBoard/commit/12a4352561c21f6b98fd64d8a2cdcdc625aad669) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Home lands a display's board at once on a display switch, and Compose's preview no longer flaps from blank as you type; the display switcher shows each display's type, size and page; the schedule entry sheet on a phone is the short form with Save in view; switching release channel confirms with a destructive button.

- [#2568](https://github.com/Fiestaboard/FiestaBoard/pull/2568) [`8b9c0e4`](https://github.com/Fiestaboard/FiestaBoard/commit/8b9c0e4e742a2cb7e5ea753e2215e82bc6d226d2) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Displays on a phone follow 07d: no card around the section, the list titled "Displays" with Add display beside it, a display page with one "‹ Displays" link over its name and the board edge to edge, causes no longer cut short, and an unknown display reads "Display not found" with Back to Displays and Add a display.

- [#2564](https://github.com/Fiestaboard/FiestaBoard/pull/2564) [`0153d0e`](https://github.com/Fiestaboard/FiestaBoard/commit/0153d0e329c8f6a27b1560e1d8bec6e9b171fd63) Thanks [@jeffredodd](https://github.com/jeffredodd)! - An unknown URL shows a "Page not found" page inside the app shell with a way Home; the app opts into FiestaUI's touch layer so default-sized controls reach 44 px on a phone; Change Page no longer opens the phone keyboard over its list; and the board's scroll hint always reads "swipe" on a touch screen.

- [#2573](https://github.com/Fiestaboard/FiestaBoard/pull/2573) [`db7f641`](https://github.com/Fiestaboard/FiestaBoard/commit/db7f6419ec59861bf3a72e9171990cc531db0b67) Thanks [@jeffredodd](https://github.com/jeffredodd)! - The editor preview on desktop shows a whole Flagship board instead of its first 13 columns, and "Now in this Collection" fits the board to the card instead of cropping it on phones. A new Collection opens on its name and says what Create still needs, and Add page shows each page's size and stays open for several picks. Rule reordering gives touch instructions on touch screens, and a rule's whole expression is readable.

- [#2577](https://github.com/Fiestaboard/FiestaBoard/pull/2577) [`71c87ee`](https://github.com/Fiestaboard/FiestaBoard/commit/71c87ee8ac8aa3b18d5a3020621062e5fb4df9f8) Thanks [@jeffredodd](https://github.com/jeffredodd)! - The page editor measures what the board draws: a colour tile from the rich editor is one column (a 22-tile art row no longer reports "66 of 22 · 44 cut off"), blank padding rows on a smaller board no longer trip the line limit, and an overflow is reported once — one card for every cut line, no repeated banner or status.

- [#2580](https://github.com/Fiestaboard/FiestaBoard/pull/2580) [`4e28410`](https://github.com/Fiestaboard/FiestaBoard/commit/4e2841088d0bf20a2ea2732c6d128dc1605b9752) Thanks [@jeffredodd](https://github.com/jeffredodd)! - The rich template behaves like a text field: multi-line text pasted from another app lands on consecutive rows, copying no longer carries invisible zero-width spaces, Esc from a toolbar picker puts the caret back, the template card shows a focus ring, long rows stay inside the card, and Undo starts disabled on an untouched page.

- [#2592](https://github.com/Fiestaboard/FiestaBoard/pull/2592) [`c25427d`](https://github.com/Fiestaboard/FiestaBoard/commit/c25427df35dccb78b9c0b4c208841546f73263a9) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Pages library cards, list rows and collection cards draw the same three-stop focus ring as every other control, with no white band in dark mode, and list rows use a 1 px border like the grid cards.

- [#2593](https://github.com/Fiestaboard/FiestaBoard/pull/2593) [`6e6a1ed`](https://github.com/Fiestaboard/FiestaBoard/commit/6e6a1ed0d560c0818294aec1453509dda203b9f8) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Variable Collections: each rule row now picks its page from a menu in the row and shows whether the rule is true right now, the Default row says what is showing, and Re-check interval and Pages in Collection open as proper sections.

- [#2585](https://github.com/Fiestaboard/FiestaBoard/pull/2585) [`d94ff42`](https://github.com/Fiestaboard/FiestaBoard/commit/d94ff42402513d827106e691d0e097651453a63d) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Compose a message opens with the caret in the message field, so typing no longer switches the "Show on" display.

## 11.0.0-alpha.11

### Patch Changes

- [#2560](https://github.com/Fiestaboard/FiestaBoard/pull/2560) [`9fdca30`](https://github.com/Fiestaboard/FiestaBoard/commit/9fdca30bcd9c9d852cae5f6780db1ec593a6d0d6) Thanks [@jeffredodd](https://github.com/jeffredodd)! - About FiestaBoard names the real release channel (Alpha preview no longer reads as Stable), shows this page's and the hub's versions and any waiting update, and opens as a bottom sheet on phones.

- [#2555](https://github.com/Fiestaboard/FiestaBoard/pull/2555) [`6d4156c`](https://github.com/Fiestaboard/FiestaBoard/commit/6d4156c2a2e108ae5783fe8465743100e50449e6) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Exporting a backup while the hub can't be reached now says so and keeps you in the app, an export error is reported instead of a false "download started", a hub that refuses the connection shows "Can't reach your hub" within seconds instead of 30 s of "Waiting to start…", and the backup and AI provider messages are translated.

- [#2566](https://github.com/Fiestaboard/FiestaBoard/pull/2566) [`c605e2b`](https://github.com/Fiestaboard/FiestaBoard/commit/c605e2b9845034e5edcfca234b613d7df2eb8a96) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Settings › System & backups now opens its Version card with the running version and whether it is up to date, shows version numbers as written (the running channel shows its own version instead of "Version unavailable"), no longer shows server setup instructions when channel switching is unavailable, and the leave-preview warning names the real Backup & Restore section.

- [#2556](https://github.com/Fiestaboard/FiestaBoard/pull/2556) [`307349e`](https://github.com/Fiestaboard/FiestaBoard/commit/307349e511e530193479cd6a6fc34c5ba0cf3e94) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Add a display: an address with a port is caught at the field instead of a raw server error and is never mistaken for a board already connected, keeping an already connected board reads "Go to <name>" and says nothing was added, and a new FiestaPanel keeps the name you typed instead of gaining " (Panel)".

- [#2569](https://github.com/Fiestaboard/FiestaBoard/pull/2569) [`7598431`](https://github.com/Fiestaboard/FiestaBoard/commit/75984313a75624cf913ae9446cc2caffb67ac2d2) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Setup and Add a display: each display choice shows one short line, so the choices and Continue fit a phone screen, and step 2 of Add a display is titled "Connect <display>" with a back arrow, "Step 2 of 2 · Only what this display needs" and a full-width Test connection on phones.

- [#2553](https://github.com/Fiestaboard/FiestaBoard/pull/2553) [`df25354`](https://github.com/Fiestaboard/FiestaBoard/commit/df253542e5e568e618477269b4a238c847b0416d) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Home, Compose and Change Page agree with the board: the preview catches up within seconds of Show now, the "Until <next Schedule change>" chip stays offered while an Override runs, display detail names the Override's page, Up next lists up to three changes, a Schedule gap reads in plain words, and the display switcher marks a display that needs a look. `GET /v1/boards/{board}` adds `schedule_next_change_at`, `schedule_next_page_id`, `upcoming_changes` and `override_page_id`.

- [#2559](https://github.com/Fiestaboard/FiestaBoard/pull/2559) [`7eda35e`](https://github.com/Fiestaboard/FiestaBoard/commit/7eda35efa66539e7d13a20f2205f34c2310bb6aa) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Phones follow the 07a frames more closely: Home leads with the whole board edge to edge and gives the page title its own line, Compose is a bottom sheet, the board's actions open as a sheet on touch, Back closes Change Page and Compose instead of leaving Home, focus scrolls clear of the bottom nav and header, and a landscape phone keeps the bottom nav.

- [#2570](https://github.com/Fiestaboard/FiestaBoard/pull/2570) [`30d9765`](https://github.com/Fiestaboard/FiestaBoard/commit/30d97652a93d4d0942e185d8ebf4805acbac2d6c) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Page editor fixes:
  - An unknown or deleted page shows "This page doesn't exist" with a way back.
  - Opening a formula on desktop scrolls its editor into view.
  - Builder no longer shows a hand-written formula as an empty recipe.
  - The phone discard sheet names the page and matches the design.
  - Delete and Page transition are labelled in the phone More sheet.
  - Opening or deleting a page no longer logs 404s.
  - The empty band under the preview settings is gone.

- [#2552](https://github.com/Fiestaboard/FiestaBoard/pull/2552) [`7182051`](https://github.com/Fiestaboard/FiestaBoard/commit/71820517551335a8c7eff4612370b61d6a4460f3) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Measure a formula by the value it renders to, so a line with a formula beside other text is no longer reported as cut off; the Problems list now holds the formula errors the board shows (`#DIV/0`, `#VALUE`) and drops a missing source that `IFERROR` handles, and the Data tab lists the data a formula reads.

- [#2561](https://github.com/Fiestaboard/FiestaBoard/pull/2561) [`553d0c2`](https://github.com/Fiestaboard/FiestaBoard/commit/553d0c29650c1d223e65020f679b4f6ca2001c17) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Phone formula editing uses the Formula sheet. It has an Inspect button, and the caret goes back into the template after Done or Cancel. A space typed before a chip is stored as a plain space, lowercase that the board shows in capitals no longer gives one warning per letter, and the Variables picker no longer brings up the keyboard on touch screens.

- [#2574](https://github.com/Fiestaboard/FiestaBoard/pull/2574) [`ef59287`](https://github.com/Fiestaboard/FiestaBoard/commit/ef59287165954238db91373c6960a6c59d44bc3b) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Creator IDE and library polish:
  - The console and timeline get half the width, so problems no longer wrap onto four lines.
  - Copying a page to another display shows its result in a sheet on phones, with one close control.
  - Library cards are named consistently, and list rows keep room for the page name.
  - The editor's small controls grow to 44px on touch screens.

- [#2567](https://github.com/Fiestaboard/FiestaBoard/pull/2567) [`924c2db`](https://github.com/Fiestaboard/FiestaBoard/commit/924c2db4452603b3db17b14984a1c7dce2337b94) Thanks [@jeffredodd](https://github.com/jeffredodd)! - The Pages library can search page names and saved content and sort by name, created or updated date, keeping the display filter and preview caching (ported from alpha [#2408](https://github.com/Fiestaboard/FiestaBoard/issues/2408)). Each page card has a menu, opened from its ··· button, a right-click or a long-press, to edit the page, add it to the Schedule, duplicate it or delete it.

- [#2557](https://github.com/Fiestaboard/FiestaBoard/pull/2557) [`bc552b5`](https://github.com/Fiestaboard/FiestaBoard/commit/bc552b5d7caca670c223ff6c895d58ebc5a3177a) Thanks [@jeffredodd](https://github.com/jeffredodd)! - The page editor fills the screen as Figma draws it. On a phone the page name is readable on two lines, the preview stays docked under the header while you type, the line you are typing stays above the toolbar with the keyboard up, and the editor toolbar replaces the tab bar. A landscape phone gets the same full-screen editor, and on a tablet the toolbar no longer covers the rail. At every width the section's card header and breadcrumb no longer sit above the editor, whose own header has the way back to Pages.

- [#2563](https://github.com/Fiestaboard/FiestaBoard/pull/2563) [`84f41a4`](https://github.com/Fiestaboard/FiestaBoard/commit/84f41a48de7238f8bd19e7f6a503b026b98f1559) Thanks [@jeffredodd](https://github.com/jeffredodd)! - After a new page's first save the editor moves to the page's own URL, so a reload, a shared link and Back all find it. The Add to Home Screen offer no longer opens over the editor at the moment of saving; it waits until you leave the editor.

- [#2558](https://github.com/Fiestaboard/FiestaBoard/pull/2558) [`b48de05`](https://github.com/Fiestaboard/FiestaBoard/commit/b48de05d429db096feb87c11c75c29d610a1fe37) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Settings on a phone now opens with "‹ More" and a plain title. Its rows show their current values: account and signed-in device count, notifications on/off, theme, FiestaBot provider, and Wi-Fi network. Signed-in devices sit directly on the page and read times as "just now" or "yesterday, 9:12 PM". Browsers are named "Chrome on macOS", and password sign-ins from apps or scripts are no longer listed as older TV apps.

- [#2554](https://github.com/Fiestaboard/FiestaBoard/pull/2554) [`f394d89`](https://github.com/Fiestaboard/FiestaBoard/commit/f394d89aa360a76e84422330d3ac2e66fbf23415) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Sign-in now follows the 07e design: the hub address and status under the title, a password reveal, "Keep me signed in on this browser", and a forgotten-password line that links to the reset page. A wrong password is explained, cleared and focused, and the sign-in card no longer shows the "change this later" footnote.

- [#2562](https://github.com/Fiestaboard/FiestaBoard/pull/2562) [`75fbf74`](https://github.com/Fiestaboard/FiestaBoard/commit/75fbf74291538c44c277a586b837a32777e4c813) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Integration settings now point at the field the hub rejected (for example a refresh interval below the plugin's minimum) and say so beside Save instead of in a toast over it, ask before leaving with unsaved edits, name each list item and its remove button for screen readers, and show Save Changes in your language.

- [#2572](https://github.com/Fiestaboard/FiestaBoard/pull/2572) [`a45a0c3`](https://github.com/Fiestaboard/FiestaBoard/commit/a45a0c35b13bdad03567e80af1a4ab280b98bddc) Thanks [@jeffredodd](https://github.com/jeffredodd)! - On a phone, the Integrations list now leads with its title and a full-width Installed · n / Marketplace switch, shows each integration's state as a coloured dot, and keeps Check for updates and Auto-update under the list. An integration's settings page drops its second Back link and keeps the demo-page text readable in long languages such as German.

- [#2520](https://github.com/Fiestaboard/FiestaBoard/pull/2520) [`67d8abc`](https://github.com/Fiestaboard/FiestaBoard/commit/67d8abcb3050a42a0836a87d663906e27c1d59bc) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Add CI bundle-size checks against measured published v11 alpha assets to catch unexpected web-code growth.

- [#2565](https://github.com/Fiestaboard/FiestaBoard/pull/2565) [`19dd0d7`](https://github.com/Fiestaboard/FiestaBoard/commit/19dd0d7cb9d8ae701e024dc1ce749791dcbd9c6e) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Schedule: the entry sheet now warns before you save when an entry overlaps another one, says which page the board actually shows during the overlap and offers a one-tap fix; saving an overlapping entry shows a warning instead of "Schedule created", and the conflicts list is translated, names both entries, uses your 12/24-hour setting and no longer hides schedule gaps.

- [#2571](https://github.com/Fiestaboard/FiestaBoard/pull/2571) [`e96e76b`](https://github.com/Fiestaboard/FiestaBoard/commit/e96e76b0c49ee430f3ebe611a86b0539c9793315) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Schedule on a phone: the title sits beside Add, one Schedule Mode row names the display, the day chips and agenda come next (week and "Which page at…" controls move below it), the Week grid is no longer offered, and the current entry or gap is marked "Now". Overnight entries read as their whole range (11:30 PM – 2:00 AM), the day ends at 12:00 AM instead of 11:59 PM, "Which page at…" no longer offers a quick moment that has passed, the entry sheet's subtitle names the display and its days, and the side sheet reaches the bottom of the screen in landscape.

- [#2575](https://github.com/Fiestaboard/FiestaBoard/pull/2575) [`8750829`](https://github.com/Fiestaboard/FiestaBoard/commit/87508295eddeb53760c743aeda058926e404d201) Thanks [@jeffredodd](https://github.com/jeffredodd)! - A sheet or dialog reopened right after closing no longer closes itself again when the browser finishes taking back the old history entry.

## 11.0.0-alpha.10

### Minor Changes

- [#2542](https://github.com/Fiestaboard/FiestaBoard/pull/2542) [`26bb476`](https://github.com/Fiestaboard/FiestaBoard/commit/26bb476a3ead45bd9bf81594b9f23ec98649ad54) Thanks [@jeffredodd](https://github.com/jeffredodd)! - The page editor now helps with big boards and note arrays: a zoom control, column ruler, board overview and "where lines are cut" map for large displays, Go to row and column, movable row bands, Note focus with seam checks, a canvas tool rail with undo and a layers list, and per-line warnings when the hub finds a line wider than the board.

- [#2540](https://github.com/Fiestaboard/FiestaBoard/pull/2540) [`ad8c90d`](https://github.com/Fiestaboard/FiestaBoard/commit/ad8c90d42260dd901ce58a6315230567cba3ac58) Thanks [@jeffredodd](https://github.com/jeffredodd)! - The page editor becomes a Creator IDE on wide screens: an Explorer of pages and collections, a status row that says where the page is showing and whether your edits are a draft, Inspector tabs for Data, Logic, Page, Shows on and History, and a docked Problems / Warnings / Sent console with a week timeline. While a display shows the page you can Save draft or Save & update board, restore an earlier version into a draft, and make a copy sized for another display.

- [#2541](https://github.com/Fiestaboard/FiestaBoard/pull/2541) [`8fffb2b`](https://github.com/Fiestaboard/FiestaBoard/commit/8fffb2bfdb2ff8cdae60bad1bcde743e008c0ddb) Thanks [@jeffredodd](https://github.com/jeffredodd)! - The page editor's formulas now show their live values, open in a docked Code or Builder editor with autocomplete and recipes, and can be inspected step by step; the preview can also show sample data, missing data, or a chosen time.

### Patch Changes

- [#2546](https://github.com/Fiestaboard/FiestaBoard/pull/2546) [`7db3048`](https://github.com/Fiestaboard/FiestaBoard/commit/7db3048031e4beb24c0fa1ef10c86dc0f5a17495) Thanks [@jeffredodd](https://github.com/jeffredodd)! - Undo after cancelling a timed message on one display now keeps working when another display changes in the meantime.

- [#2545](https://github.com/Fiestaboard/FiestaBoard/pull/2545) [`9f3e533`](https://github.com/Fiestaboard/FiestaBoard/commit/9f3e533472837492f3c44b9884aa58f33451e835) Thanks [@jeffredodd](https://github.com/jeffredodd)! - The phone app now asks for a key again in a few more cases where saved settings change, and no longer asks for it when a display edit doesn't need it.

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
