/**
 * Matching pages to FiestaPanels by geometry.
 *
 * A panel's board is a `panel` grid fit per character (rows × cols), so a
 * "panel page" is a `panel` page whose grid_rows × grid_cols equals the
 * panel's board. Panels created before per-character fitting were note-array
 * boards; those payloads are still accepted. Nothing is stored on the page to
 * say which panel it was made for — the grid is the whole relationship — so
 * these helpers are the one place that comparison lives.
 */
import { describe, expect, it } from "vitest";

import type { BoardInstance, Panel } from "@/lib/api";
import { displayTargets, panelsFittingGrid, panelTargets, targetValue } from "@/lib/panel-page-fit";

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

/** A per-character `panel` board, as the API reports one after the re-fit. */
function gridPanel(id: string, name: string, rows: number, cols: number): Panel {
  return panel({ id, name, device_type: "panel", rows, cols, notes_wide: null, notes_tall: null });
}

describe("panelTargets", () => {
  it("reads the note grid the API reports for a legacy note-array panel", () => {
    const [target] = panelTargets([panel({ id: "p1", name: "Kitchen TV" })]);
    expect(target).toEqual({
      id: "p1",
      name: "Kitchen TV",
      deviceType: "note_array",
      notesWide: 2,
      notesTall: 4,
      gridRows: null,
      gridCols: null,
      rows: 12,
      cols: 30,
    });
  });

  it("reads a panel board's character grid as its grid_rows × grid_cols", () => {
    const [target] = panelTargets([gridPanel("p1", "Kitchen TV", 12, 29)]);
    expect(target).toEqual({
      id: "p1",
      name: "Kitchen TV",
      deviceType: "panel",
      notesWide: 1,
      notesTall: 1,
      gridRows: 12,
      gridCols: 29,
      rows: 12,
      cols: 29,
    });
  });

  it("skips a panel board whose payload has no grid", () => {
    const stale = panel({ id: "p1", name: "Kitchen TV", device_type: "panel", rows: null, cols: null });
    expect(panelTargets([stale])).toEqual([]);
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

describe("panelsFittingGrid — per-character panel boards", () => {
  const living = panelTargets([gridPanel("p1", "Living Room TV", 12, 29)])[0];
  const den = panelTargets([gridPanel("p2", "Den TV", 14, 34)])[0];

  it("names the panel whose grid is exactly this panel page's grid", () => {
    expect(panelsFittingGrid([living, den], "panel", 1, 1, 12, 29)).toEqual([living]);
  });

  it("matches nothing when the panel page is one column off", () => {
    expect(panelsFittingGrid([living, den], "panel", 1, 1, 12, 30)).toEqual([]);
  });

  it("does not match a note-array page of the same dimensions against a panel board", () => {
    const sixByThirty = panelTargets([gridPanel("p3", "Hall TV", 6, 30)])[0];
    expect(panelsFittingGrid([sixByThirty], "note_array", 2, 2)).toEqual([]);
  });

  it("does not match a panel page without a grid against any panel", () => {
    const noteSized = panelTargets([gridPanel("p4", "Tiny TV", 3, 15)])[0];
    expect(panelsFittingGrid([noteSized], "panel")).toEqual([]);
  });
});

describe("displayTargets — every board with a custom grid", () => {
  /** A board as GET /settings/board reports it. */
  function board(overrides: Partial<BoardInstance> & Pick<BoardInstance, "id" | "name">): BoardInstance {
    return {
      device_type: "flagship",
      board_color: "black",
      enabled: true,
      api_mode: "local",
      host: "",
      local_api_key: "",
      cloud_key: "",
      ...overrides,
    } as BoardInstance;
  }

  const pixoo = board({
    id: "b-pixoo",
    name: "Pixoo",
    device_type: "panel",
    grid_rows: 10,
    grid_cols: 16,
    output: "divoom_pixoo",
    device_model: "divoom_pixoo64",
    charset: "led_3x5",
  });

  it("lists an output plugin's board as a display, named for its board and model", () => {
    const [target] = displayTargets([], [pixoo]);
    expect(target).toMatchObject({
      id: "b-pixoo",
      name: "Pixoo",
      kind: "display",
      boardId: "b-pixoo",
      led: true,
      deviceType: "panel",
      gridRows: 10,
      gridCols: 16,
    });
    expect(target.modelLabel).toMatch(/Pixoo/);
    expect(targetValue(target)).toBe("display:b-pixoo");
  });

  it("matches a page of the display's grid", () => {
    const targets = displayTargets([], [pixoo]);
    expect(panelsFittingGrid(targets, "panel", 1, 1, 10, 16).map(targetValue)).toEqual(["display:b-pixoo"]);
  });

  it("lists the panels first, and a panel's own board only once", () => {
    const kitchen = gridPanel("p1", "Kitchen TV", 12, 29);
    const kitchenBoard = board({
      id: "board-p1",
      name: "Kitchen TV",
      device_type: "panel",
      grid_rows: 12,
      grid_cols: 29,
    });
    const targets = displayTargets([kitchen], [kitchenBoard, pixoo]);
    expect(targets.map(targetValue)).toEqual(["panel:p1", "display:b-pixoo"]);
    expect(targets[0].boardId).toBe("board-p1");
  });

  it("skips boards with a fixed shape or no grid", () => {
    const flagship = board({ id: "b-flag", name: "Hall" });
    const ungridded = board({ id: "b-bare", name: "Bare", device_type: "panel", grid_rows: null, grid_cols: null });
    expect(displayTargets(undefined, [flagship, ungridded])).toEqual([]);
  });

  it("marks a custom-grid board without an LED model as not LED", () => {
    const sign = board({ id: "b-sign", name: "Sign", device_type: "panel", grid_rows: 4, grid_cols: 20 });
    expect(displayTargets([], [sign])[0]).toMatchObject({ kind: "display", led: false, modelLabel: null });
  });
});
