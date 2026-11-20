import { act, fireEvent, render, renderHook, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef } from "react";
import { describe, expect, it, vi } from "vitest";

import {
  BigBoardZoom,
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
    noteArray: false,
    rows: 24,
    cols: 96,
    notesWide: 1,
    notesTall: 1,
    zoom: "sm",
    setZoom: vi.fn(),
    previewMode: "actual",
    previewSize: "sm",
    minimapOpen: true,
    setMinimapOpen: vi.fn(),
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
    expect(result.current.zoom).toBe("sm");
    act(() => result.current.setZoom("lg"));
    expect(onPreviewModeChange).not.toHaveBeenCalled();
    act(() => result.current.setZoom("fit"));
    expect(onPreviewModeChange).toHaveBeenCalledWith("fit");
  });
});

describe("complex preview tools", () => {
  const board = { message: "HELLO", deviceType: "panel" as const, gridRows: 24, gridCols: 96 };

  function Preview({ complex, onJump = vi.fn() }: { complex: ComplexEditing; onJump?: () => void }) {
    return (
      <>
        <ComplexPreviewRuler complex={complex} />
        <div className="relative">
          <div>board</div>
          <ComplexPreviewSeams complex={complex} />
        </div>
        <ComplexPreviewOverview
          complex={complex}
          board={board}
          rendered={["ROSA'S CAFE"]}
          overflows={[{ line: 24, columns: 98, maxColumns: 96, cut: 2 }]}
          minimapId="map"
          onJump={onJump}
        />
      </>
    );
  }

  it("adds nothing when no lens applies", () => {
    render(<Preview complex={fakeComplex({ active: false, bigBoard: false })} />);
    expect(screen.getByText("board")).toBeInTheDocument();
    expect(document.querySelector('[data-slot^="complex-preview"]')).toBeNull();
  });

  it("adds the ruler, caption, minimap and truncation map around a big board", async () => {
    const onJump = vi.fn();
    render(<Preview complex={fakeComplex()} onJump={onJump} />);
    expect(screen.getByRole("img", { name: "Column ruler · 96 columns" })).toBeInTheDocument();
    expect(screen.getByText("Overview · 96 × 24")).toBeInTheDocument();
    expect(document.getElementById("map")).not.toBeNull();
    expect(screen.getByText("Where lines are cut")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Row 24 · 98 of 96 columns · 2 cut off/ }));
    expect(onJump).toHaveBeenCalledWith(expect.objectContaining({ row: 24 }));
  });

  it("waits for the board to be measured before drawing the ruler", () => {
    const complex = fakeComplex();
    render(<Preview complex={{ ...complex, geometry: { ...complex.geometry, pitch: 0 } }} />);
    expect(document.querySelector('[data-slot="complex-preview-ruler"]')).toBeNull();
  });

  it("hides the minimap when the zoom control closes it", () => {
    render(<Preview complex={fakeComplex({ minimapOpen: false })} />);
    expect(document.getElementById("map")).toBeNull();
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

describe("BigBoardZoom", () => {
  it("reports zoom intent and minimap visibility to the host", async () => {
    const complex = fakeComplex();
    render(<BigBoardZoom complex={complex} minimapId="map" />);
    await userEvent.click(screen.getByRole("radio", { name: "Tile md" }));
    expect(complex.setZoom).toHaveBeenCalledWith("md");
    await userEvent.click(screen.getByRole("button", { name: "Show overview map" }));
    expect(complex.setMinimapOpen).toHaveBeenCalledWith(false);
  });
});

describe("ComplexTemplateHeader", () => {
  it("goes to a typed row and column on a big board", async () => {
    const onGo = vi.fn();
    render(<ComplexTemplateHeader complex={fakeComplex()} editorRootRef={createRef()} onGo={onGo} />);
    const input = screen.getByRole("textbox", { name: "Go to row and column" });
    await userEvent.type(input, "4 10{Enter}");
    expect(onGo).toHaveBeenCalledWith({ row: 4, column: 10 });
  });

  it("adds no ⌘J/Ctrl+J binding or kbd outside the editor's shortcut registry (DD-W130)", () => {
    render(<ComplexTemplateHeader complex={fakeComplex()} editorRootRef={createRef()} onGo={vi.fn()} />);
    const input = screen.getByRole("textbox", { name: "Go to row and column" });
    expect(document.querySelector("kbd")).toBeNull();
    const event = new KeyboardEvent("keydown", {
      key: "j",
      code: "KeyJ",
      ctrlKey: true,
      bubbles: true,
      cancelable: true,
    });
    document.body.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
    expect(document.activeElement).not.toBe(input);
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

  it("shows the hub's verdict and offers to wrap the line", async () => {
    const onWrap = vi.fn();
    render(
      <LineOverflowWarnings
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
        overflows={[overflow]}
        checkedAt={null}
        touch
        wrapped={[false, false, false, true]}
        onWrap={vi.fn()}
      />,
    );
    expect(screen.queryByRole("button", { name: "Wrap line 4" })).toBeNull();
    rerender(<LineOverflowWarnings overflows={[]} checkedAt={null} touch wrapped={[]} onWrap={vi.fn()} />);
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

  it("names each band and moves it down from its menu", async () => {
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
      cb(0);
      return 0;
    });
    const { onChange } = setup(["HEADER", "", "TONIGHT", "OPEN MIC", "", "", "", ""]);
    const list = await screen.findByRole("list", { name: "Row bands" });
    expect(within(list).getByText("HEADER")).toBeInTheDocument();
    expect(within(list).getByText("Rows 3–4")).toBeInTheDocument();
    fireEvent.contextMenu(within(list).getByText("HEADER"));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Move down" }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ lines: ["TONIGHT", "OPEN MIC", "", "HEADER", "", "", "", ""] }),
    );
    vi.restoreAllMocks();
  });

  it("renders no gutter when off", () => {
    setup(["HEADER"], false);
    expect(screen.queryByRole("list", { name: "Row bands" })).toBeNull();
  });
});
