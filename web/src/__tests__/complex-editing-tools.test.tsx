import { act, fireEvent, render, renderHook, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef } from "react";
import { describe, expect, it, vi } from "vitest";

import { measureLineBoxes } from "@/lib/complex-editing-dom";

vi.mock("@/lib/complex-editing-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/complex-editing-dom")>();
  return { ...actual, measureLineBoxes: vi.fn(actual.measureLineBoxes) };
});

import {
  ComplexPreviewOverview,
  ComplexPreviewRuler,
  ComplexPreviewSeams,
} from "@/components/complex-editing/complex-preview-tools";
import {
  ComplexTemplateHeader,
  NoteSeamSummary,
  RowBandGutter,
} from "@/components/complex-editing/complex-template-tools";
import { LineOverflowWarnings } from "@/components/complex-editing/line-overflow-warnings";
import { type ComplexEditing, useComplexEditing } from "@/components/complex-editing/use-complex-editing";

function fakeComplex(overrides: Partial<ComplexEditing> = {}): ComplexEditing {
  return {
    active: true,
    bigBoard: true,
    ownsZoom: true,
    noteArray: false,
    rows: 24,
    cols: 96,
    notesWide: 1,
    notesTall: 1,
    zoom: "sm",
    setZoom: vi.fn(),
    previewMode: "actual",
    previewSize: "sm",
    tile: "sm",
    setMode: vi.fn(),
    rulerOpen: true,
    setRulerOpen: vi.fn(),
    note: null,
    setNote: vi.fn(),
    geometry: {
      first: 1,
      last: 44,
      pitch: 16,
      originX: 12,
      originY: 16,
      tileWidth: 13,
      tileHeight: 18,
      columnGap: 3,
      rowGap: 3,
      seamGap: 0,
      clip: { x: 0, y: 0, width: 720, height: 480 },
    },
    scrollToColumn: vi.fn(),
    ...overrides,
  } as ComplexEditing;
}

describe("useComplexEditing", () => {
  it("turns on the big-board lenses only on the desktop pane", () => {
    const big = { rows: 24, cols: 96, deviceType: "panel", notesWide: 1, notesTall: 1, stage: null };
    expect(renderHook(() => useComplexEditing({ ...big, enabled: true })).result.current.bigBoard).toBe(true);
    expect(renderHook(() => useComplexEditing({ ...big, enabled: false })).result.current.active).toBe(false);
    const flagship = {
      rows: 6,
      cols: 22,
      deviceType: "flagship",
      notesWide: 1,
      notesTall: 1,
      enabled: true,
      stage: null,
    };
    expect(renderHook(() => useComplexEditing(flagship)).result.current.active).toBe(false);
  });

  it("drives the preview from the zoom and forgets a Note the array no longer has", () => {
    const { result, rerender } = renderHook((props) => useComplexEditing(props), {
      initialProps: {
        rows: 6,
        cols: 30,
        deviceType: "note_array",
        notesWide: 2,
        notesTall: 2,
        enabled: true,
        stage: null as HTMLElement | null,
      },
    });
    expect(result.current.noteArray).toBe(true);
    act(() => result.current.setZoom("sm"));
    expect(result.current.previewSize).toBe("sm");
    act(() => result.current.setZoom("fit"));
    expect(result.current.previewMode).toBe("fit");
    act(() => result.current.setNote(4));
    expect(result.current.note).toBe(4);
    rerender({ rows: 3, cols: 30, deviceType: "note_array", notesWide: 2, notesTall: 1, enabled: true, stage: null });
    expect(result.current.note).toBeNull();
  });
});

describe("useComplexEditing zoom and the session preview mode", () => {
  const big = { rows: 24, cols: 96, deviceType: "panel", notesWide: 1, notesTall: 1, enabled: true, stage: null };

  // UX-4-2: Den TV opened at Tile sm, cropped at column 28, when Fit shows all 34.
  it("opens a big board at Fit, even when the session last chose Actual size", () => {
    expect(renderHook(() => useComplexEditing(big)).result.current.zoom).toBe("fit");
    expect(renderHook(() => useComplexEditing({ ...big, previewMode: "actual" })).result.current.zoom).toBe("fit");
  });

  it("returns to the last tile size for Actual size", () => {
    const { result } = renderHook(() => useComplexEditing({ ...big, previewMode: "fit" }));
    act(() => result.current.setZoom("lg"));
    act(() => result.current.setMode("fit"));
    expect(result.current.zoom).toBe("fit");
    act(() => result.current.setMode("actual"));
    expect(result.current.zoom).toBe("lg");
  });

  it("keeps a big board's zoom through draw mode while the lenses step aside", () => {
    const { result, rerender } = renderHook((props) => useComplexEditing(props), {
      initialProps: { ...big, paused: false },
    });
    act(() => result.current.setZoom("md"));
    rerender({ ...big, paused: true });
    expect(result.current.bigBoard).toBe(false);
    expect(result.current.ownsZoom).toBe(true);
    expect(result.current.previewSize).toBe("md");
  });

  it("keeps the ruler off by default except over a note array (DD-W131 seams)", () => {
    expect(renderHook(() => useComplexEditing(big)).result.current.rulerOpen).toBe(false);
    const notes = { ...big, deviceType: "note_array", notesWide: 4, notesTall: 4 };
    expect(renderHook(() => useComplexEditing(notes)).result.current.rulerOpen).toBe(true);
  });

  it("starts from the session's Fit and reports Fit-or-Actual intent back", () => {
    const onPreviewModeChange = vi.fn();
    const { result } = renderHook(() => useComplexEditing({ ...big, previewMode: "fit", onPreviewModeChange }));
    expect(result.current.zoom).toBe("fit");
    act(() => result.current.setZoom("md"));
    expect(onPreviewModeChange).toHaveBeenLastCalledWith("actual");
    expect(result.current.previewSize).toBe("md");
  });

  it("does not report a mode the session already has", () => {
    const onPreviewModeChange = vi.fn();
    const { result } = renderHook(() => useComplexEditing({ ...big, previewMode: "actual", onPreviewModeChange }));
    act(() => result.current.setZoom("sm"));
    onPreviewModeChange.mockClear();
    act(() => result.current.setZoom("lg"));
    expect(onPreviewModeChange).not.toHaveBeenCalled();
    act(() => result.current.setZoom("fit"));
    expect(onPreviewModeChange).toHaveBeenCalledWith("fit");
  });
});

describe("complex preview tools", () => {
  const board = { message: "HELLO", deviceType: "panel" as const, gridRows: 24, gridCols: 96 };

  function Preview({ complex }: { complex: ComplexEditing }) {
    return (
      <>
        <ComplexPreviewRuler complex={complex} />
        <div className="relative">
          <div>board</div>
          <ComplexPreviewSeams complex={complex} />
        </div>
        <ComplexPreviewOverview complex={complex} board={board} minimapId="map" />
      </>
    );
  }

  it("adds nothing when no lens applies", () => {
    render(<Preview complex={fakeComplex({ active: false, bigBoard: false })} />);
    expect(screen.getByText("board")).toBeInTheDocument();
    expect(document.querySelector('[data-slot^="complex-preview"]')).toBeNull();
  });

  it("adds the ruler and the minimap around a big board the zoom crops, and no cut chart (UX-4-3)", () => {
    render(<Preview complex={fakeComplex()} />);
    expect(screen.getByRole("img", { name: "Column ruler · 96 columns" })).toBeInTheDocument();
    expect(screen.getByText("Overview · 96 × 24")).toBeInTheDocument();
    expect(document.getElementById("map")).not.toBeNull();
    expect(screen.queryByText("Where lines are cut")).toBeNull();
  });

  it("shows the minimap only while the zoom crops the board (UX-4-2)", () => {
    const complex = fakeComplex();
    const { rerender } = render(<Preview complex={{ ...complex, zoom: "fit" }} />);
    expect(document.getElementById("map")).toBeNull();
    rerender(<Preview complex={{ ...complex, geometry: { ...complex.geometry, first: 1, last: 96 } }} />);
    expect(document.getElementById("map")).toBeNull();
  });

  it("draws the ruler only when the View menu turns it on", () => {
    render(<Preview complex={fakeComplex({ rulerOpen: false })} />);
    expect(document.querySelector('[data-slot="complex-preview-ruler"]')).toBeNull();
  });

  it("waits for the board to be measured before drawing the ruler", () => {
    const complex = fakeComplex();
    render(<Preview complex={{ ...complex, geometry: { ...complex.geometry, pitch: 0 } }} />);
    expect(document.querySelector('[data-slot="complex-preview-ruler"]')).toBeNull();
  });

  it("draws Note seams over a measured note array, without big-board tools", () => {
    render(
      <Preview
        complex={fakeComplex({
          bigBoard: false,
          noteArray: true,
          notesWide: 2,
          notesTall: 2,
          note: 2,
          cols: 30,
          rows: 6,
        })}
      />,
    );
    expect(document.querySelector('[data-slot="complex-preview-seams"]')).not.toBeNull();
    expect(screen.queryByText("Where lines are cut")).toBeNull();
    expect(document.querySelector('[data-slot="complex-preview-ruler"]')).toBeNull();
  });
});

describe("ComplexTemplateHeader", () => {
  it("adds no Row · Col pill or explanatory caption on a big board (UX-3-2)", () => {
    const { container } = render(<ComplexTemplateHeader complex={fakeComplex()} editorRootRef={createRef()} />);
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByRole("textbox", { name: "Go to row and column" })).toBeNull();
    expect(screen.queryByText(/rendered length per row/)).toBeNull();
  });

  it("focuses a Note and scrolls the preview to it", async () => {
    const complex = fakeComplex({ bigBoard: false, noteArray: true, notesWide: 2, notesTall: 2, cols: 30, rows: 6 });
    render(<ComplexTemplateHeader complex={complex} editorRootRef={createRef()} onGo={vi.fn()} />);
    await userEvent.click(screen.getByRole("radio", { name: "Note 2" }));
    expect(complex.setNote).toHaveBeenCalledWith(2);
    expect(complex.scrollToColumn).toHaveBeenCalledWith(16);
  });

  it("renders nothing without a lens", () => {
    const { container } = render(
      <ComplexTemplateHeader complex={fakeComplex({ active: false })} editorRootRef={createRef()} onGo={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe("NoteSeamSummary", () => {
  it("says when nothing straddles and names each straddle", () => {
    const { rerender } = render(<NoteSeamSummary straddles={[]} />);
    expect(screen.getByRole("status")).toHaveTextContent("nothing straddles a seam");
    rerender(<NoteSeamSummary straddles={[{ row: 2, column: 15, word: "4.75MOCHA" }]} />);
    expect(screen.getByRole("status")).toHaveTextContent("Row 2: “4.75MOCHA” runs across the seam after column 15.");
  });
});

describe("LineOverflowWarnings", () => {
  const overflow = { line: 4, columns: 24, maxColumns: 22, cut: 2 };

  it("disables Wrap with the reason when the rows below are full (W-1)", async () => {
    const onWrap = vi.fn();
    render(
      <LineOverflowWarnings
        overflows={[{ line: 5, columns: 46, maxColumns: 22, cut: 24 }]}
        lines={["", "", "", "HELLO WORLD", "LUNCH AT NOON TODAY FOR EVERYONE IN THE OFFICE", ""]}
        rows={6}
        boardName="Kitchen"
        checkedAt={null}
        touch={false}
        wrapped={[]}
        onWrap={onWrap}
      />,
    );
    const wrap = screen.getByRole("button", { name: "Wrap line 5" });
    expect(wrap).toBeDisabled();
    expect(wrap).toHaveAccessibleDescription("Needs 1 more row");
    expect(screen.getByText("Needs 1 more row")).toBeVisible();
  });

  it("names a row past the board as the Problems console does (W-1)", () => {
    const message = "Line 5 wraps past the board's 6 rows · 1 row won't show";
    const { container } = render(
      <LineOverflowWarnings
        overflows={[]}
        pastBoard={[{ line: 5, message, kind: "beyond_board" }]}
        lines={[]}
        rows={6}
        checkedAt={null}
        touch={false}
        wrapped={[]}
        onWrap={vi.fn()}
      />,
    );
    const card = container.querySelector('[data-slot="editor-warning"]');
    expect(card).toHaveTextContent("Past the last row");
    expect(card).toHaveTextContent(message);
  });

  // FABLE-2659: a wrap a line below stops short is named for what happened.
  it("names a wrap stopped by a line below in the hub's words", () => {
    const message = "Line 4 wraps into line 5 · 2 rows won't show";
    const { container } = render(
      <LineOverflowWarnings
        overflows={[]}
        pastBoard={[{ line: 4, message, kind: "wrap_stopped" }]}
        lines={[]}
        rows={6}
        checkedAt={null}
        touch={false}
        wrapped={[]}
        onWrap={vi.fn()}
      />,
    );
    const card = container.querySelector('[data-slot="editor-warning"]');
    expect(card).toHaveTextContent("Wrap cut short");
    expect(card).not.toHaveTextContent("Past the last row");
    expect(card).toHaveTextContent(message);
  });

  it("shows the hub's verdict and offers to wrap the line", async () => {
    const onWrap = vi.fn();
    render(
      <LineOverflowWarnings
        lines={[]}
        rows={6}
        overflows={[overflow]}
        boardName="Kitchen board"
        checkedAt={new Date(2026, 10, 17, 18, 5)}
        touch={false}
        wrapped={[]}
        onWrap={onWrap}
      />,
    );
    expect(screen.getByText("Line 4")).toBeInTheDocument();
    expect(screen.getByText("24 of 22 columns · 2 cut off")).toBeInTheDocument();
    expect(screen.getByText(/Checked by the hub at Kitchen board's real width/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Wrap line 4" }));
    expect(onWrap).toHaveBeenCalledWith(4);
  });

  it("reports several cut lines in one card, not one card per line (BB-E-10)", async () => {
    const onWrap = vi.fn();
    const { container } = render(
      <LineOverflowWarnings
        lines={[]}
        rows={6}
        overflows={[
          { line: 1, columns: 63, maxColumns: 22, cut: 41 },
          { line: 2, columns: 34, maxColumns: 22, cut: 12 },
          { line: 3, columns: 51, maxColumns: 22, cut: 29 },
        ]}
        boardName="Kitchen"
        checkedAt={new Date(2026, 10, 17, 18, 5)}
        touch={false}
        wrapped={[false, true, false]}
        onWrap={onWrap}
      />,
    );
    expect(container.querySelectorAll('[data-slot="editor-warning"]')).toHaveLength(1);
    expect(screen.getAllByText(/Checked by the hub/)).toHaveLength(1);
    expect(screen.getByText("63 of 22 columns · 41 cut off")).toBeInTheDocument();
    expect(screen.getByText("Also cut off: Line 2, Line 3")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Wrap line 2" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Wrap line 3" }));
    expect(onWrap).toHaveBeenCalledWith(3);
  });

  it("drops the wrap action once the line wraps, and renders nothing without overflow", () => {
    const { rerender, container } = render(
      <LineOverflowWarnings
        lines={[]}
        rows={6}
        overflows={[overflow]}
        checkedAt={null}
        touch
        wrapped={[false, false, false, true]}
        onWrap={vi.fn()}
      />,
    );
    expect(screen.queryByRole("button", { name: "Wrap line 4" })).toBeNull();
    rerender(
      <LineOverflowWarnings overflows={[]} lines={[]} rows={6} checkedAt={null} touch wrapped={[]} onWrap={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe("RowBandGutter", () => {
  function setup(lines: string[], enabled = true) {
    const editorRootRef = createRef<HTMLDivElement>();
    const onChange = vi.fn();
    const state = { lines, alignments: lines.map(() => "left"), wraps: lines.map(() => false) };
    const view = render(
      <div ref={editorRootRef}>
        <RowBandGutter
          enabled={enabled}
          state={state}
          rows={lines.length}
          editorRootRef={editorRootRef}
          onChange={onChange}
        />
        <div contentEditable="true" suppressContentEditableWarning>
          <p>{lines.join("")}</p>
        </div>
      </div>,
    );
    return { onChange, ...view };
  }

  it("names each data band for its part and moves it down from its menu (W-10)", async () => {
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
      cb(0);
      return 0;
    });
    const header = "HI {{weather.temp}}";
    const { onChange } = setup([header, "", "TONIGHT", "{{red}} OPEN MIC", "", "PLAIN TEXT", "", ""]);
    const list = await screen.findByRole("list", { name: "Row bands" });
    expect(within(list).getByText("weather")).toBeInTheDocument();
    expect(within(list).getByText("red")).toBeInTheDocument();
    expect(within(list).getByText("Rows 3–4")).toBeInTheDocument();
    // A plain-text row gets no band: it would only repeat the row beside it.
    expect(within(list).getAllByTestId("row-band")).toHaveLength(2);
    expect(within(list).queryByText(/PLAIN|TONIGHT|HI/)).toBeNull();
    fireEvent.contextMenu(within(list).getByText("weather"));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Move down" }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ lines: ["TONIGHT", "{{red}} OPEN MIC", "", header, "", "PLAIN TEXT", "", ""] }),
    );
    vi.restoreAllMocks();
  });

  it("names an unnamed band by its rows once, and keeps every label to one clamped line (UX-3-1)", () => {
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
      cb(0);
      return 0;
    });
    setup(["A REALLY LONG ROW {{a_really_long_integration.field}}", "", "", "", "", "{63}", "", "x"]);
    const list = screen.getByRole("list", { name: "Row bands" });
    const bands = within(list).getAllByTestId("row-band");
    // Row 6 holds only a character code, so it has no name: "Row 6", never "Rows 6–6" over "Row 6".
    expect(within(list).queryByText("Rows 6–6")).toBeNull();
    expect(within(list).getAllByText("Row 6")).toHaveLength(1);
    for (const band of bands) {
      expect(band).toHaveClass("min-h-0", "overflow-hidden", "[&_[data-slot=row-band-label]]:truncate");
      expect(band.getAttribute("title")).toBeTruthy();
    }
    expect(bands[0].getAttribute("title")).toBe("a_really_long_integration · Row 1");
    vi.restoreAllMocks();
  });

  it("stops a band's bracket at the next row with text, not at the next band (W-10)", () => {
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
      cb(0);
      return 0;
    });
    const actual = vi.mocked(measureLineBoxes).getMockImplementation()!;
    vi.mocked(measureLineBoxes).mockImplementation((_root, _gutter, count) =>
      Array.from({ length: count }, (_, i) => ({ top: i * 24, height: 24 })),
    );
    setup(["{{a.b}}", "", "PLAIN HEADLINE", "", "", "{{c.d}}"]);
    const [first] = within(screen.getByRole("list", { name: "Row bands" })).getAllByTestId("row-band");
    // Rows 1–2 (the band and its blank row), stopping 4 px above row 3's text.
    expect(first.style.height).toBe("44px");
    vi.mocked(measureLineBoxes).mockImplementation(actual);
    vi.restoreAllMocks();
  });

  it("re-measures for template edits only, and not while the editor is hidden (BB-E-31)", async () => {
    const frames: FrameRequestCallback[] = [];
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
      frames.push(cb);
      return frames.length;
    });
    const flush = () => frames.splice(0).forEach((cb) => cb(0));
    const measure = vi.mocked(measureLineBoxes);
    measure.mockClear();
    setup(["HEADER", "", "TONIGHT", ""]);
    flush();
    expect(measure).toHaveBeenCalledTimes(1);
    const root = document.querySelector('[contenteditable="true"]')!.parentElement!;

    // A sibling of the template (a placeholder, the host's own chrome) changing.
    const sibling = document.createElement("span");
    root.appendChild(sibling);
    await new Promise((r) => setTimeout(r, 0));
    flush();
    expect(measure).toHaveBeenCalledTimes(1);

    // The template text changing.
    document.querySelector('[contenteditable="true"] p')!.appendChild(document.createTextNode("!"));
    await new Promise((r) => setTimeout(r, 0));
    flush();
    expect(measure).toHaveBeenCalledTimes(2);

    // Hidden under draw mode: no measurement at all.
    const editable = document.querySelector('[contenteditable="true"]') as HTMLElement & {
      checkVisibility?: () => boolean;
    };
    editable.checkVisibility = () => false;
    editable.querySelector("p")!.appendChild(document.createTextNode("?"));
    await new Promise((r) => setTimeout(r, 0));
    flush();
    expect(measure).toHaveBeenCalledTimes(2);
    vi.restoreAllMocks();
  });

  it("watches the editable's own size, so it re-measures when draw mode shows it again (BB-E-31)", () => {
    const observed: Element[] = [];
    const Original = window.ResizeObserver;
    window.ResizeObserver = class {
      observe(el: Element) {
        observed.push(el);
      }
      unobserve() {}
      disconnect() {}
    } as unknown as typeof ResizeObserver;
    setup(["HEADER", ""]);
    expect(observed).toContain(document.querySelector('[contenteditable="true"]'));
    window.ResizeObserver = Original;
  });

  it("renders no gutter when off", () => {
    setup(["HEADER"], false);
    expect(screen.queryByRole("list", { name: "Row bands" })).toBeNull();
  });
});
