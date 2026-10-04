/**
 * Generate the shared message-markup parity fixtures from the REAL FiestaUI
 * parser (`parseLine` / `messageToGrid` in `src/lib/board-characters.ts`).
 *
 * FiestaUI is the reference implementation for the board's message grammar;
 * `src/markup.py` is the Python port. The fixtures this script writes are the
 * contract between the two: `tests/test_markup_parity.py` replays every case
 * against the Python parser.
 *
 * Do not run this on the host. `scripts/markup_fixtures/generate.sh` runs it in
 * a throwaway `node:24-alpine` container against a read-only mount of a
 * FiestaUI checkout, after `npm ci` in a private copy of it.
 *
 * Usage (inside the container):
 *   node generate.mjs <fiestaui-copy-dir> <fixture-out-file> <icons-out-file>
 * Provenance comes from the environment (the host script reads it from git):
 *   FIESTAUI_BRANCH, FIESTAUI_COMMIT, FIESTAUI_DIRTY ("true" | "false"),
 *   FIESTAUI_NOTE (optional free text, e.g. which uncommitted revision)
 *
 * The icon table is written twice on purpose: into the fixture (what the
 * parity test compares against) and into src/markup_icons.json (the data the
 * Python parser loads at runtime), so the Python side never hand-maintains a
 * list of icon names that FiestaUI owns.
 */

import { createHash } from "node:crypto";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const [fiestaUiDir, outFile, iconsFile] = process.argv.slice(2);
if (!fiestaUiDir || !outFile) {
  console.error("usage: node generate.mjs <fiestaui-dir> <fixture-out-file> [<icons-out-file>]");
  process.exit(2);
}

// esbuild comes from FiestaUI's own lockfile, the same tool its unit tests use
// to import this TypeScript module.
const requireFromUi = createRequire(join(fiestaUiDir, "package.json"));
const { build } = requireFromUi("esbuild");

// A FiestaUI commit that predates the icon registry still has the base
// grammar worth checking; it just yields no extended-markup cases.
const HAS_ICONS = existsSync(join(fiestaUiDir, "src/lib/board-icons.ts"));
const SOURCES = ["src/lib/board-characters.ts", ...(HAS_ICONS ? ["src/lib/board-icons.ts"] : []), "src/lib/board-colors.ts"];

const outDir = mkdtempSync(join(tmpdir(), "markup-fixtures-"));
const entry = join(outDir, "entry.ts");
writeFileSync(
  entry,
  [
    `export * from ${JSON.stringify(join(fiestaUiDir, "src/lib/board-characters.ts"))};`,
    ...(HAS_ICONS
      ? [`export { BOARD_ICONS, BOARD_ICON_NAMES } from ${JSON.stringify(join(fiestaUiDir, "src/lib/board-icons.ts"))};`]
      : []),
    `export { ALL_COLOR_CODES } from ${JSON.stringify(join(fiestaUiDir, "src/lib/board-colors.ts"))};`,
  ].join("\n"),
);
const bundle = join(outDir, "board-characters.mjs");
await build({ entryPoints: [entry], bundle: true, format: "esm", platform: "neutral", outfile: bundle, logLevel: "error" });
const ui = await import(pathToFileURL(bundle).href);
rmSync(outDir, { recursive: true, force: true });

// Does this parseLine know `extendedMarkup`? One without it ignores the option
// and would silently record legacy output under "ext/" ids.
const HAS_EXTENDED = ui.parseLine("{red:A}", Infinity, { extendedMarkup: true }).length === 1;
const MODES = HAS_EXTENDED ? [false, true] : [false];
// Icon names are only inputs for the legacy cases (where they are literal text).
const ICON_NAMES = HAS_ICONS
  ? ui.BOARD_ICON_NAMES
  : ["sun", "cloud", "rain", "snow", "bolt", "check", "cross", "up", "down", "star", "bus", "train", "music", "bell"];

// --- flap projection -------------------------------------------------------
// FiestaUI tokens carry a colour tile as its marker code ("63" or "red"); the
// board wants 63-71. Characters project through FiestaUI's own getCharIndex.
const NAMED_TILE = { red: 63, orange: 64, yellow: 65, green: 66, blue: 67, violet: 68, purple: 68, white: 69, black: 70, filled: 71 };
const tileCode = (code) => (/^\d+$/.test(code) ? Number(code) : NAMED_TILE[code]);
const project = (token) => (token.type === "color" ? tileCode(token.code) : ui.getCharIndex(token.value));

// --- cases -----------------------------------------------------------------

const PLAIN = [
  ["plain-upper", "HELLO WORLD"],
  ["plain-lower", "hello world"],
  ["plain-mixed", "Hello, World!"],
  ["plain-empty", ""],
  ["plain-spaces", "   "],
  ["plain-digits", "0123456789"],
  ["plain-punctuation", "!@#$()-+&=;:'\"%,./?"],
  ["plain-unsupported", "~`^*_[]<>\\|"],
  ["plain-accented", "Café crème"],
  ["plain-sharp-s", "straße"],
  ["plain-emoji", "hi 😀!"],
];

const TILES = [
  ...["63", "64", "65", "66", "67", "68", "69", "70", "71"].map((c) => [`tile-${c}`, `{${c}}`]),
  ["tile-62-not-a-tile", "{62}"],
  ["tile-72-not-a-tile", "{72}"],
  ["tile-063-not-a-tile", "{063}"],
  ...["red", "orange", "yellow", "green", "blue", "violet", "white", "black"].map((n) => [`tile-${n}`, `{${n}}`]),
  ["alias-purple", "{purple}"],
  ["alias-purple-upper", "{PURPLE}"],
  ["alias-filled", "{filled}"],
  ["alias-filled-upper", "{FILLED}"],
  ["case-upper-name", "{RED}"],
  ["case-title-name", "{Red}"],
  ["tiles-adjacent", "{63}{64}{red}"],
  ["tile-then-text", "{red}HOT{/red}"],
  ["tile-in-text", "Temp: {green} 62°F"],
];

const END_TAGS = [
  ["end-bare", "A{/}B"],
  ["end-named", "A{/red}B"],
  ["end-named-upper", "A{/RED}B"],
  ["end-filled", "A{/filled}B"],
  ["end-purple", "A{/purple}B"],
  ["end-unknown-name", "A{/foo}B"],
  ["end-numeric", "A{/63}B"],
  ["end-with-colon", "{/white:A}"],
];

const MALFORMED = [
  ["brace-open-only", "{"],
  ["brace-close-only", "}"],
  ["brace-empty", "{}"],
  ["brace-unterminated-name", "{red"],
  ["brace-dangling-close", "red}"],
  ["brace-double", "{{red}}"],
  ["brace-leading-space", "{ red}"],
  ["brace-trailing-space", "{red }"],
  ["brace-colon-only", "{:}"],
  ["brace-empty-head", "{:HOT}"],
  ["brace-run", "{{{"],
  ["brace-mixed-run", "}}}{"],
  ["unknown-marker", "{sun}"],
  ["inherited-key-marker", "{toString}"],
  ["proto-marker", "{__proto__}"],
];

const SPANS = [
  ["span-red", "{red:HOT}"],
  ["span-red-then-text", "{red:HOT}!"],
  ["span-numeric", "{63:A}"],
  ["span-filled-numeric", "{71:A}"],
  ["span-hex-upper", "{#FF8800:a}"],
  ["span-hex-lower", "{#ff8800:a}"],
  ["span-hex-short", "{#ff880:a}"],
  ["span-hex-long", "{#ff88001:a}"],
  ["span-hex-3", "{#f80:a}"],
  ["span-name-title", "{Red:a}"],
  ["span-purple-alias", "{purple:x}"],
  ["span-filled-alias", "{filled:x}"],
  ["span-unknown-head", "{foo:x}"],
  ["span-empty", "A{red:}B"],
  ["span-with-space", "{red:HOT DOG}"],
  ["span-unterminated", "{red:HOT"],
  ["span-unbalanced-tile", "{red:A{66}"],
  ["span-tile-inside", "{red:A{66}B}C"],
  ["span-tile-inside-spaced", "{red:HOT {63}}"],
  ["span-multiple-colons", "{red:A:B}"],
  ["span-proto-head", "{constructor:x}"],
  ["span-degree", "{red:72°}"],
  ["span-mixed-line", "Now {green:OPEN} till {red:9PM}"],
];

const BLOCKS = [
  ["block-inverse", "{black/white:ON}"],
  ["block-white-red", "{white/red:LATE}"],
  ["block-hex-numeric", "{#ffffff/63:a}"],
  ["block-half-head-fg", "{red/:A}"],
  ["block-half-head-bg", "{/red:A}"],
  ["block-three-colours", "{red/blue/green:A}"],
  ["block-unknown-bg", "{red/foo:A}"],
  ["block-case", "{BLACK/White:on}"],
];

const NESTING = [
  ["nest-span-in-span", "{red:A{blue:B}C}"],
  ["nest-span-in-block", "{black/white:A{red:B}C}"],
  ["nest-end-bare-inside", "{red:A{/}B}"],
  ["nest-end-named-inside", "{red:A{/red}B}"],
  ["nest-literal-braces-inside", "{red:A{foo}B}"],
  ["nest-unbalanced-inner", "{red:A{B}"],
  ["nest-deep", "{red:a{blue:b{green:c{63}}d}e}"],
  ["nest-icon-colour-in-span", "{red:{icon:sun}}"],
  ["nest-icon-char-in-span", "{red:{icon:up}}"],
  ["nest-icon-char-in-block", "{black/white:{icon:up}}"],
  ["nest-icon-blank-in-span", "{red:{icon:bus}}"],
];

const ICONS = [
  ...ICON_NAMES.map((n) => [`icon-${n}`, `{icon:${n}}`]),
  ["icon-upper-name", "{icon:SUN}"],
  ["icon-upper-all", "{ICON:SUN}"],
  ["icon-title", "{Icon:Sun}"],
  ["icon-unknown", "{icon:nope}"],
  ["icon-inherited", "{icon:constructor}"],
  ["icon-tostring", "{icon:toString}"],
  ["icon-proto", "{icon:__proto__}"],
  ["icon-empty", "{icon:}"],
  ["icon-leading-space", "{icon: sun}"],
  ["icon-trailing-space", "{icon:sun }"],
  ["icon-in-text", "AQI {icon:up} 3 {icon:sun}"],
  ["icon-run", "{icon:sun}{icon:cloud}{icon:rain}"],
];

const CODE62 = [
  ["code62-degree", "72°"],
  ["code62-degree-alone", "°"],
  ["code62-heart-suit", "♥"],
  ["code62-heart-emoji", "❤"],
];

const LINES = [...PLAIN, ...TILES, ...END_TAGS, ...MALFORMED, ...SPANS, ...BLOCKS, ...NESTING, ...ICONS, ...CODE62];

const PRESERVE_CASE = [
  ["case-preserve-plain", "Hi there"],
  ["case-preserve-span", "{red:Hot}"],
  ["case-preserve-icon", "{icon:sun}x"],
  ["case-preserve-tile", "{Red}x"],
];

const CAPPED_LINES = [
  ["cap-spans-icons", "{red:HOT {66} TODAY} and {icon:sun}{icon:bus} more text"],
  ["cap-long-span", "x{blue:" + "y".repeat(30) + "}z"],
  ["cap-tiles", "{red}{63}AB{/}C"],
];
const CAPS = [0, 1, 3, 7, 22];

// Same check for preserveCase, which arrived in the same options bag.
const HAS_PRESERVE_CASE = ui.parseLine("a", Infinity, { preserveCase: true })[0].value === "a";

const lineCases = [];
for (const extendedMarkup of MODES) {
  const mode = extendedMarkup ? "ext" : "legacy";
  for (const [id, line] of LINES) {
    lineCases.push({ id: `${mode}/${id}`, line, options: { extendedMarkup } });
  }
  for (const [id, line] of HAS_PRESERVE_CASE ? PRESERVE_CASE : []) {
    lineCases.push({ id: `${mode}/${id}`, line, options: { extendedMarkup, preserveCase: true } });
  }
  for (const [id, line] of CAPPED_LINES) {
    for (const cap of CAPS) {
      lineCases.push({ id: `${mode}/${id}/cap-${cap}`, line, options: { extendedMarkup }, maxTokens: cap });
    }
  }
}

for (const c of lineCases) {
  const tokens = ui.parseLine(c.line, c.maxTokens ?? Infinity, c.options);
  c.tokens = tokens;
  // A flap projection only means something for the board's own (uppercase) charset.
  if (!c.options.preserveCase) c.codes = tokens.map(project);
}

const GRID_MESSAGES = [
  ["grid-plain", "HELLO\nWORLD"],
  ["grid-overflow", "ABCDEFGHIJKLMNOPQRSTUVWXYZ\nrow two\nrow three\nrow four"],
  ["grid-span-overflow", "{red:ABCDEFGHIJKLMNOPQRSTUVWXYZ}"],
  ["grid-degree", "72°\n{red:°}"],
  ["grid-icons", "{icon:sun} 72°\n{icon:rain}{icon:up}"],
  ["grid-literal", "{red:HOT}\n{icon:sun}"],
];
const GRID_SHAPES = [
  ["flagship", 6, 22, undefined],
  ["flagship", 6, 22, "heart"],
  ["note", 3, 15, undefined],
  ["panel", 2, 5, undefined],
];
const gridCases = [];
for (const extendedMarkup of MODES) {
  const mode = extendedMarkup ? "ext" : "legacy";
  for (const [id, message] of GRID_MESSAGES) {
    for (const [deviceType, rows, cols, code62Glyph] of GRID_SHAPES) {
      const options = { extendedMarkup };
      const grid = ui.messageToGrid(message, rows, cols, deviceType, code62Glyph, options);
      gridCases.push({
        id: `${mode}/${id}/${deviceType}-${rows}x${cols}${code62Glyph ? `-${code62Glyph}` : ""}`,
        message,
        rows,
        cols,
        deviceType,
        code62Glyph: code62Glyph ?? null,
        options,
        // Spread drops the frozen-blank identity; only the contents matter here.
        grid: grid.map((row) => row.map((t) => ({ ...t }))),
      });
    }
  }
}

const icons = HAS_ICONS ? Object.fromEntries(ui.BOARD_ICON_NAMES.map((n) => [n, { ...ui.BOARD_ICONS[n] }])) : null;

const fileHashes = Object.fromEntries(
  SOURCES.map((p) => [p, createHash("sha256").update(readFileSync(join(fiestaUiDir, p))).digest("hex")]),
);

const header = {
  description:
    "Message-markup parity fixtures generated from FiestaUI's parseLine/messageToGrid. Do not edit by hand: regenerate with scripts/markup_fixtures/generate.sh.",
  fiestaui: {
    branch: process.env.FIESTAUI_BRANCH || "unknown",
    commit: process.env.FIESTAUI_COMMIT || "unknown",
    dirty: process.env.FIESTAUI_DIRTY === "true",
    sources_sha256: fileHashes,
    ...(process.env.FIESTAUI_NOTE ? { note: process.env.FIESTAUI_NOTE } : {}),
  },
  generator: "scripts/markup_fixtures/generate.mjs",
  // What this FiestaUI commit can parse; absent modes have no cases here.
  modes: MODES.map((ext) => (ext ? "ext" : "legacy")),
  preserve_case: HAS_PRESERVE_CASE,
};

// One case per line keeps diffs reviewable when FiestaUI changes a behaviour.
const out = [
  "{",
  `"header": ${JSON.stringify(header)},`,
  `"colors": ${JSON.stringify(Object.keys(ui.ALL_COLOR_CODES))},`,
  `"icons": ${JSON.stringify(icons)},`,
  `"lines": [`,
  lineCases.map((c) => JSON.stringify(c)).join(",\n"),
  `],`,
  `"grids": [`,
  gridCases.map((c) => JSON.stringify(c)).join(",\n"),
  `]`,
  "}",
  "",
].join("\n");
writeFileSync(outFile, out);
console.log(`wrote ${lineCases.length} line cases and ${gridCases.length} grid cases to ${outFile}`);

if (iconsFile && icons) {
  const iconsData = {
    header: {
      description:
        "Icon table for {icon:NAME} markup, vendored from FiestaUI src/lib/board-icons.ts. Do not edit by hand: regenerate with scripts/markup_fixtures/generate.sh.",
      fiestaui: header.fiestaui,
    },
    icons,
  };
  writeFileSync(iconsFile, JSON.stringify(iconsData, null, 2) + "\n");
  console.log(`wrote icons to ${iconsFile}`);
}
