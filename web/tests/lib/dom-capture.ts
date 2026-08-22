/**
 * DOM capture — serialise an app screen as markup instead of rasterising it.
 *
 * The docs site (Fiestaboard/fiestaboard.github.io) renders these instead of
 * PNG screenshots. One capture replaces four PNGs: the markup is identical
 * across light/dark (the theme is a class on the wrapper, and every colour
 * resolves through FiestaUI tokens) and across desktop/mobile (the app is
 * responsive via CSS breakpoints, not JS branching). Only a couple of runtime
 * CSS custom properties differ per breakpoint, so those are recorded per
 * viewport and replayed by the docs site as a media query.
 *
 * Cropping and highlighting happen at RENDER time on the docs side, anchored
 * by CSS selector — never by pixel coordinates, which would reintroduce the
 * drift this whole mechanism exists to remove. That is why an element-level
 * shot still captures the whole screen and merely records the selector.
 */
import type { Page } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

/** Runtime custom properties the app sets on <html> that affect layout. */
const RUNTIME_VARS = ["--mobile-header-height"] as const;

/**
 * The instant every capture is frozen at.
 *
 * Pinned so anything the UI derives from the current time renders the same on
 * every run. Without this the captures churn: /settings\' Animations card
 * drives a demo board from a JS timer, and `reducedMotion` does not stop a
 * timer — it only disables CSS animation — so the board\'s message kept
 * changing between reads ("WATCH ME" one read, "FLIP SPEED" the next).
 */
export const CAPTURE_INSTANT = new Date("2026-01-15T10:30:00.000Z");

/** Breakpoints the docs site can render a capture at. */
export const CAPTURE_VIEWPORTS = {
  desktop: { width: 1280, height: 800 },
  mobile: { width: 390, height: 844 },
} as const;

export interface CaptureEntry {
  /** Capture file, relative to the captures dir. */
  file: string;
  /** Selector the docs site should frame, for shots that targeted an element. */
  frame?: string;
  /** Class list the capture must be wrapped in (e.g. "font-sans antialiased"). */
  wrapperClass: string;
  /** Runtime CSS custom properties, per breakpoint. */
  vars: Record<string, Record<string, string>>;
  /** Viewport the markup was captured at. */
  capturedAt: { width: number; height: number };
  /** True when desktop and mobile produced different markup and both are kept. */
  viewportSpecific?: boolean;
  /**
   * The screen never stops animating on its own (e.g. the Animations card
   * cycles two demo messages forever). Informational: the capture is still
   * deterministic, because the clock is pinned and advanced by a fixed span,
   * so the sample is taken at the same virtual instant every run.
   */
  alwaysAnimating?: boolean;
}

/**
 * Strip what is provably inert, and normalise what is provably unstable.
 *
 * Deliberately conservative. Measured against a real Settings capture, removing
 * every attribute that renders identically saves ~1% of the gzipped bytes — not
 * worth the risk of stripping something a Tailwind selector depends on. Note
 * that `data-slot` and `data-current-char`/`data-target-char` DO change the
 * render (they drive component styling and the split-flap tiles) and must
 * survive; so must `data-orientation` and `data-[state]`, which style tabs.
 *
 * `stripAttrs` may be extended per-screen by `verifyStripsAreSafe`, which
 * proves a candidate is neutral by re-rendering and comparing pixels.
 */
export function sanitize(html: string, stripAttrs: readonly string[] = []): string {
  let out = html;

  // React Router's streaming-hydration scripts come along with outerHTML and
  // throw ("Cannot read properties of undefined (reading 'streamController')")
  // in every docs page that embeds the capture. They can never do useful work
  // outside the app, so they always go.
  out = out.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, "");

  // Toasts are transient by definition — one run caught a Sonner toast that
  // the next had already dismissed, so the capture differed by a whole
  // subtree. A notification that has already faded has no place in a docs
  // screenshot regardless.
  out = out.replace(/<ol\b[^>]*data-sonner-toaster[\s\S]*?<\/ol>/gi, "");

  // Inline event handlers cannot fire (the capture is inert) but should not be
  // shipped either.
  out = out.replace(/\son[a-z]+="[^"]*"/gi, "");

  // Nothing in a capture should be focusable; `inert` on the wrapper already
  // enforces that, this keeps the markup honest.
  out = out.replace(/\stabindex="[^"]*"/gi, "");

  for (const attr of stripAttrs) {
    out = out.replace(new RegExp(`\\s${attr}="[^"]*"`, "gi"), "");
  }

  // Entity ids are minted by the server every time the fixtures are seeded, so
  // the same page created by two runs carries two different UUIDs and every
  // element keyed on one differs (`id="schedule-enabled-48f75126-…"`). Left
  // alone this was the single largest churn source — 24 of 29 captures changed
  // between two identical runs. Renumbering in first-appearance order is a
  // bijection, so distinct entities stay distinct and the diff tracks real
  // change instead of the seed.
  const uuids = [...new Set(out.match(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi) ?? [])];
  uuids.forEach((id, i) => {
    out = out.split(id).join(`00000000-0000-4000-8000-${String(i).padStart(12, "0")}`);
  });

  // React's useId counter is deterministic for an unchanged tree — repeated
  // captures of the same build are byte-identical — but the ids come from
  // render order, so inserting a component upstream renumbers everything after
  // it and turns a small UI change into a large diff. Renaming them in
  // first-appearance order keeps the diff proportional to the actual change.
  const generated = [...new Set(out.match(/base-ui-_r_[0-9a-z]+_/g) ?? [])];
  generated.forEach((id, i) => {
    out = out.split(id).join(`fb-c${i}`);
  });

  return out;
}

/**
 * Remove UI whose content depends on the outside world.
 *
 * Two things here reflect state no capture can own. The "Update available"
 * banner reports whether a newer FiestaBoard release exists, so every release
 * would rewrite every capture that shows it — one run in testing picked up
 * v8.28.1 mid-session and 20 elements appeared out of nowhere. Toasts are
 * transient in the same way: one run caught a Sonner toast the next had
 * already dismissed.
 *
 * Done through the DOM rather than a regex over the serialised markup, so
 * nested children go with their parent instead of leaving orphaned tags.
 */
async function removeVolatileUi(page: Page) {
  await page.evaluate(() => {
    const gone = ['[aria-label^="Update available"]', "[data-sonner-toaster]", "[data-sonner-toast]"];
    // The variable picker renders a live sample beside each variable — the
    // Date/Time plugin's `time`, `minute`, `time_12h` and friends, computed on
    // the SERVER, so pinning the browser clock cannot reach them. They moved
    // 14:44 -> 14:48 between two runs and were the last thing still churning.
    // The samples are incidental to what these pages teach (which variables
    // exist, and how to insert one), so they go rather than leaving CI's
    // reproducibility gate failing every few minutes.
    document.querySelectorAll('[data-slot="tooltip-trigger"] span[class*="opacity-70"]').forEach((el) => el.remove());

    // Drop focus. The page editor highlights whichever gutter line the caret
    // sits on, and where the caret lands depends on how the test's typing
    // settled — one run highlighted line 1, the next line 6. A still image has
    // no caret, so the highlight is noise either way. Blur does not dispatch an
    // outside-click, so popovers held open by state (the variable picker) stay
    // open.
    (document.activeElement as HTMLElement | null)?.blur?.();

    for (const sel of gone) {
      document.querySelectorAll(sel).forEach((el) => {
        // The banner is a button inside a row that also holds its label; drop
        // the row when removing the button would leave it empty.
        const parent = el.parentElement;
        el.remove();
        if (parent && parent.children.length === 0 && !parent.textContent?.trim()) parent.remove();
      });
    }
  });
}

/**
 * Block until no board tile is still animating.
 *
 * Mirrors the spec's own `waitForBoard`, but has to run again here: the tests
 * time their wait for the PNG, and the DOM capture happens afterwards, by
 * which point a board may have started another transition.
 */
async function settleBoards(page: Page, timeoutMs = 12_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const moving = await page.locator('[data-is-transitioning="true"], [data-is-animating="true"]').count();
    if (moving === 0) return;
    await page.waitForTimeout(300);
  }
}

/**
 * Read the screen twice and require the two to agree.
 *
 * A capture that changes between reads would produce a diff on every
 * regeneration, drowning real UI changes in noise. That is not hypothetical:
 * /settings' Animations card runs a demo board that cycles its message, and
 * three reads four seconds apart produced three different documents until
 * `reducedMotion: "reduce"` was turned on in the screenshot config.
 *
 * This is the guard that keeps the next such component from slipping in
 * silently — it retries, then marks the entry `unstable` and warns, rather
 * than quietly committing churn.
 */
async function readStable(page: Page) {
  let last = await readScreen(page);
  for (let attempt = 0; attempt < 3; attempt++) {
    await page.waitForTimeout(800);
    const next = await readScreen(page);
    if (next.html === last.html) return { ...next, unstable: false };
    last = next;
  }
  return { ...last, unstable: true };
}

/** Read the wrapper class + runtime vars + markup for the current viewport. */
async function readScreen(page: Page) {
  return page.evaluate(
    (vars: readonly string[]) => {
      const root = document.querySelector("#root") ?? document.body;
      const cs = getComputedStyle(document.documentElement);
      const collected: Record<string, string> = {};
      for (const v of vars) {
        const value = cs.getPropertyValue(v).trim();
        if (value) collected[v] = value;
      }
      return {
        html: root.outerHTML,
        wrapperClass: document.body.className,
        vars: collected,
      };
    },
    RUNTIME_VARS as unknown as string[],
  );
}

/**
 * Capture one screen at every breakpoint and write the markup once.
 *
 * The page is re-measured at each viewport. When the markup matches (the usual
 * case — the app's responsiveness is pure CSS) a single file is written and
 * only the runtime vars are recorded per breakpoint. When it differs, both are
 * kept and `viewportSpecific` is set so the docs site loads the right one.
 */
export async function captureScreen(
  page: Page,
  outDir: string,
  name: string,
  opts: { frame?: string; stripAttrs?: readonly string[] } = {},
): Promise<CaptureEntry> {
  const original = page.viewportSize() ?? CAPTURE_VIEWPORTS.desktop;

  // Let the screen finish arriving before reading it. The tests time their
  // own waits for the PNG, which is forgiving — a half-settled raster still
  // looks plausible — but a capture taken mid-settle is committed markup that
  // differs from the next run's. Three fresh loads of /settings with this wait
  // are byte-identical; without it they were not.
  await page.waitForLoadState("networkidle").catch(() => {
    // A screen that never reaches network idle (polling) still gets the
    // settle delay below, and readStable is the real guard.
  });
  await page.waitForTimeout(800);

  // Let every split-flap board finish flipping BEFORE the clock stops. A tile
  // mid-flap renders extra leaf elements, so pausing too early freezes boards
  // in whatever state they happened to reach — that alone left 18 captures
  // differing between two runs, one of them by 52 elements.
  await removeVolatileUi(page);
  await settleBoards(page);

  // Prove the screen is settled BEFORE freezing the clock. Checking afterwards
  // is worthless — a paused clock makes anything look stable, including a demo
  // board frozen halfway through a flip.
  const settled = await readStable(page);

  // Then stop the clock so timer-driven UI cannot change mid-capture. Paused
  // only for the duration of the capture — the PNG for this screen has already
  // been taken, and a test may take more shots afterwards.
  await page.clock.pauseAt(CAPTURE_INSTANT);

  // Then advance VIRTUAL time by a fixed amount. Some screens animate forever —
  // the Animations card alternates two demo messages on a setInterval — so
  // there is no moment at which they are naturally settled. Pausing alone
  // freezes them wherever they happened to be, which differs run to run.
  // Advancing a fixed span instead lands them in the same place every time,
  // and lets any in-flight flip finish rather than freezing mid-flap.
  await page.clock.runFor(6000);
  await page.waitForTimeout(400);
  const byViewport: Record<
    string,
    { html: string; wrapperClass: string; vars: Record<string, string>; unstable: boolean }
  > = {};

  for (const [label, size] of Object.entries(CAPTURE_VIEWPORTS)) {
    await page.setViewportSize(size);
    // Let the breakpoint change settle before reading layout-derived vars.
    await page.waitForTimeout(400);
    byViewport[label] = { ...(await readStable(page)), unstable: settled.unstable };
  }
  await page.setViewportSize(original);
  await page.clock.resume();

  const labels = Object.keys(CAPTURE_VIEWPORTS);
  const sanitised = Object.fromEntries(labels.map((l) => [l, sanitize(byViewport[l].html, opts.stripAttrs)]));
  const identical = labels.every((l) => sanitised[l] === sanitised[labels[0]]);

  fs.mkdirSync(outDir, { recursive: true });

  const vars = Object.fromEntries(labels.map((l) => [l, byViewport[l].vars]));
  const entry: CaptureEntry = {
    file: `${name}.html`,
    wrapperClass: byViewport.desktop.wrapperClass,
    vars,
    capturedAt: CAPTURE_VIEWPORTS.desktop,
    ...(opts.frame ? { frame: opts.frame } : {}),
  };

  const unstable = labels.some((l) => byViewport[l].unstable);
  if (unstable) {
    entry.alwaysAnimating = true;

    console.warn(
      `[dom-capture] ${name}: never settles on its own — sampled at a fixed ` +
        `virtual instant instead. The capture is still deterministic; this is ` +
        `only a note that the screen contains a perpetual animation.`,
    );
  }

  if (identical) {
    fs.writeFileSync(path.join(outDir, `${name}.html`), sanitised[labels[0]]);
  } else {
    entry.viewportSpecific = true;
    for (const l of labels) {
      fs.writeFileSync(path.join(outDir, `${name}.${l}.html`), sanitised[l]);
    }
  }

  return entry;
}

/** Merge a capture entry into the on-disk manifest the docs site reads. */
export function writeManifestEntry(outDir: string, name: string, entry: CaptureEntry) {
  const manifestPath = path.join(outDir, "manifest.json");
  let manifest: { version: number; captures: Record<string, CaptureEntry> } = {
    version: 1,
    captures: {},
  };
  if (fs.existsSync(manifestPath)) {
    try {
      manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
    } catch {
      // A corrupt manifest is regenerated from scratch rather than failing the
      // run — every entry is rewritten on a full pass anyway.
    }
  }
  manifest.captures[name] = entry;
  // Stable key order so the committed manifest diffs cleanly.
  const ordered = Object.fromEntries(
    Object.keys(manifest.captures)
      .sort()
      .map((k) => [k, manifest.captures[k]]),
  );
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(manifestPath, `${JSON.stringify({ version: 1, captures: ordered }, null, 2)}\n`);
}
