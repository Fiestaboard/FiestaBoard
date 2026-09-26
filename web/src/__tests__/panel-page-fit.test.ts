/**
 * Matching pages to FiestaPanels by geometry.
 *
 * A panel's board IS a note-array grid, so a "panel page" is a note_array
 * page whose grid equals the panel's board. Nothing is stored on the page to
 * say which panel it was made for — the grid is the whole relationship — so
 * these helpers are the one place that comparison lives.
 */
import { describe, expect, it } from "vitest";

import type { Panel } from "@/lib/api";
import { panelsFittingGrid, panelTargets } from "@/lib/panel-page-fit";

function panel(overrides: Partial<Panel> & Pick<Panel, "id" | "name">): Panel {
  return {
    short_code: 1,
    board_id: `board-${overrides.id}`,
    screen_diagonal_inches: 55,
    calibration_scale: 1,
    animations_enabled: false,
    is_display: false,
    backdrop: "wall",
    auto_dim: { enabled: false, start: "22:00", end: "07:00" },
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    device_type: "note_array",
    board_missing: false,
    rows: 12,
    cols: 30,
    notes_wide: 2,
    notes_tall: 4,
    ...overrides,
  };
}

describe("panelTargets", () => {
  it("reads the note grid the API reports rather than dividing rows and cols", () => {
    const [target] = panelTargets([panel({ id: "p1", name: "Kitchen TV" })]);
    expect(target).toEqual({
      id: "p1",
      name: "Kitchen TV",
      deviceType: "note_array",
      notesWide: 2,
      notesTall: 4,
      rows: 12,
      cols: 30,
    });
  });

  it("skips a panel whose board was deleted out from under it", () => {
    const orphan = panel({
      id: "p1",
      name: "Kitchen TV",
      board_missing: true,
      device_type: null,
      rows: null,
      cols: null,
      notes_wide: null,
      notes_tall: null,
    });
    expect(panelTargets([orphan])).toEqual([]);
  });

  it("skips a panel from a payload cached before the note grid was reported", () => {
    // Optional-with-null on the wire: an older cached payload has no grid, and
    // guessing one would size a page wrong.
    const stale = panel({ id: "p1", name: "Kitchen TV", notes_wide: undefined, notes_tall: undefined });
    expect(panelTargets([stale])).toEqual([]);
  });

  it("is empty while the panel list is still loading", () => {
    expect(panelTargets(undefined)).toEqual([]);
  });
});

describe("panelsFittingGrid", () => {
  const kitchen = panelTargets([panel({ id: "p1", name: "Kitchen TV" })])[0];
  const office = panelTargets([
    panel({ id: "p2", name: "Office TV", rows: 6, cols: 15, notes_wide: 1, notes_tall: 2 }),
  ])[0];
  const hallway = panelTargets([panel({ id: "p3", name: "Hallway TV" })])[0];

  it("names the panel whose board is exactly this page's grid", () => {
    expect(panelsFittingGrid([kitchen, office], "note_array", 2, 4)).toEqual([kitchen]);
  });

  it("matches nothing when no panel has that grid", () => {
    expect(panelsFittingGrid([kitchen, office], "note_array", 3, 3)).toEqual([]);
  });

  it("returns every panel of that shape, first one first", () => {
    expect(panelsFittingGrid([kitchen, hallway, office], "note_array", 2, 4)).toEqual([kitchen, hallway]);
  });

  it("matches a flagship page against nothing, whatever the notes arguments say", () => {
    // 6 × 22 is not a multiple of a Note, so no panel can ever be that shape —
    // and notesWide/notesTall are meaningless outside note_array.
    expect(panelsFittingGrid([kitchen, office], "flagship", 2, 4)).toEqual([]);
  });

  // A 1×1 panel is easy to get: compute_autofit_grid returns 1×1 for screens
  // under about 25 inches. Both a plain Note page and a 1×1 note-array page
  // resolve to 3×15 flaps, but the platform's own compatibility rule
  // (sizeKey / pagesCompatibleWithBoard, mirrored in src/devices.py) is
  // FAMILY-aware and refuses the first — page-grid-selector filters that page
  // out for the panel's board and schedule-entry-form warns about it. The
  // label has to agree with the rest of the app, not promise a fit the app
  // then refuses.
  it("does not match a plain Note page against a 1×1 panel, because the families differ", () => {
    const tiny = panelTargets([
      panel({ id: "p4", name: "Tiny TV", rows: 3, cols: 15, notes_wide: 1, notes_tall: 1 }),
    ])[0];
    expect(panelsFittingGrid([tiny], "note", 1, 1)).toEqual([]);
  });

  it("matches a 1×1 note-array page against a 1×1 panel", () => {
    const tiny = panelTargets([
      panel({ id: "p4", name: "Tiny TV", rows: 3, cols: 15, notes_wide: 1, notes_tall: 1 }),
    ])[0];
    expect(panelsFittingGrid([tiny], "note_array", 1, 1)).toEqual([tiny]);
  });

  it("is empty when the install has no panels", () => {
    expect(panelsFittingGrid([], "note_array", 2, 4)).toEqual([]);
  });
});
