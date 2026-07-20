import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import React from "react";
import { describe, expect, it } from "vitest";

import { BoardDisplay } from "@/components/board-display";
import { StaticBoardDisplay } from "@/components/static-board-display";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <ConfigOverridesProvider>
        <ThemeProvider attribute="class" defaultTheme="light">
          {children}
        </ThemeProvider>
      </ConfigOverridesProvider>
    </QueryClientProvider>
  );
}

describe("StaticBoardDisplay variable-size grid rendering", () => {
  it("test 1: renders 3×30 grid for note_array 2 wide × 1 tall (90 tiles)", () => {
    const { container } = render(
      <StaticBoardDisplay message="" deviceType="note_array" notesWide={2} notesTall={1} />,
      { wrapper: TestWrapper },
    );
    const tiles = container.querySelectorAll("[data-note-tile]");
    expect(tiles).toHaveLength(90); // 3 rows × 30 cols

    const rows = container.querySelectorAll("[data-note-row]");
    expect(rows).toHaveLength(3);
    // Each row should have 30 tiles
    rows.forEach((row) => {
      expect(row.querySelectorAll("[data-note-tile]")).toHaveLength(30);
    });
  });

  it("test 2: renders 3×60 grid for note_array 4 wide × 1 tall (180 tiles)", () => {
    const { container } = render(
      <StaticBoardDisplay message="" deviceType="note_array" notesWide={4} notesTall={1} />,
      { wrapper: TestWrapper },
    );
    const tiles = container.querySelectorAll("[data-note-tile]");
    expect(tiles).toHaveLength(180); // 3 rows × 60 cols

    const rows = container.querySelectorAll("[data-note-row]");
    expect(rows).toHaveLength(3);
    rows.forEach((row) => {
      expect(row.querySelectorAll("[data-note-tile]")).toHaveLength(60);
    });
  });

  it("test 3: renders 6×15 grid for note_array 1 wide × 2 tall (90 tiles)", () => {
    const { container } = render(
      <StaticBoardDisplay message="" deviceType="note_array" notesWide={1} notesTall={2} />,
      { wrapper: TestWrapper },
    );
    const tiles = container.querySelectorAll("[data-note-tile]");
    expect(tiles).toHaveLength(90); // 6 rows × 15 cols

    const rows = container.querySelectorAll("[data-note-row]");
    expect(rows).toHaveLength(6);
    rows.forEach((row) => {
      expect(row.querySelectorAll("[data-note-tile]")).toHaveLength(15);
    });
  });

  it("test 4: renders 12×15 grid for note_array 1 wide × 4 tall (180 tiles)", () => {
    const { container } = render(
      <StaticBoardDisplay message="" deviceType="note_array" notesWide={1} notesTall={4} />,
      { wrapper: TestWrapper },
    );
    const tiles = container.querySelectorAll("[data-note-tile]");
    expect(tiles).toHaveLength(180); // 12 rows × 15 cols

    const rows = container.querySelectorAll("[data-note-row]");
    expect(rows).toHaveLength(12);
  });

  it("test 5: renders 6×30 grid for note_array 2 wide × 2 tall (180 tiles)", () => {
    const { container } = render(
      <StaticBoardDisplay message="" deviceType="note_array" notesWide={2} notesTall={2} />,
      { wrapper: TestWrapper },
    );
    const tiles = container.querySelectorAll("[data-note-tile]");
    expect(tiles).toHaveLength(180); // 6 rows × 30 cols

    const rows = container.querySelectorAll("[data-note-row]");
    expect(rows).toHaveLength(6);
  });

  it("test 6: renders 6×45 grid for note_array 3 wide × 2 tall (270 tiles, custom)", () => {
    const { container } = render(
      <StaticBoardDisplay message="" deviceType="note_array" notesWide={3} notesTall={2} />,
      { wrapper: TestWrapper },
    );
    const tiles = container.querySelectorAll("[data-note-tile]");
    expect(tiles).toHaveLength(270); // 6 rows × 45 cols
  });

  it("test 7: flagship renders 132 tiles (6×22) with no seam attributes", () => {
    const { container } = render(<StaticBoardDisplay message="" deviceType="flagship" />, { wrapper: TestWrapper });
    const tiles = container.querySelectorAll("[data-note-tile]");
    expect(tiles).toHaveLength(132); // 6 rows × 22 cols

    const colSeams = container.querySelectorAll("[data-note-col-seam]");
    expect(colSeams).toHaveLength(0);

    const rowSeams = container.querySelectorAll("[data-note-row-seam]");
    expect(rowSeams).toHaveLength(0);
  });

  it("test 8: note renders 45 tiles (3×15) with no seam attributes", () => {
    const { container } = render(<StaticBoardDisplay message="" deviceType="note" />, { wrapper: TestWrapper });
    const tiles = container.querySelectorAll("[data-note-tile]");
    expect(tiles).toHaveLength(45); // 3 rows × 15 cols

    const colSeams = container.querySelectorAll("[data-note-col-seam]");
    expect(colSeams).toHaveLength(0);

    const rowSeams = container.querySelectorAll("[data-note-row-seam]");
    expect(rowSeams).toHaveLength(0);
  });

  it("test 9: note_array 4×1 (3×60) has col seams at colIdx 15, 30, 45 but not 0", () => {
    const { container } = render(
      <StaticBoardDisplay message="" deviceType="note_array" notesWide={4} notesTall={1} />,
      { wrapper: TestWrapper },
    );
    // Each row should have seams at cols 15, 30, 45 (3 seams per row × 3 rows = 9 total)
    const colSeams = container.querySelectorAll("[data-note-col-seam='true']");
    expect(colSeams).toHaveLength(9); // 3 seams × 3 rows

    // Tile at colIdx 0 in any row should NOT have seam
    const rows = container.querySelectorAll("[data-note-row]");
    rows.forEach((row) => {
      const tilesInRow = row.querySelectorAll("[data-note-tile]");
      expect(tilesInRow[0]).not.toHaveAttribute("data-note-col-seam");
      // Tiles at index 15, 30, 45 should have seam
      expect(tilesInRow[15]).toHaveAttribute("data-note-col-seam", "true");
      expect(tilesInRow[30]).toHaveAttribute("data-note-col-seam", "true");
      expect(tilesInRow[45]).toHaveAttribute("data-note-col-seam", "true");
    });
  });

  it("test 10: note_array 2×2 (6×30) has row seam at rowIdx 3 but not rowIdx 0", () => {
    const { container } = render(
      <StaticBoardDisplay message="" deviceType="note_array" notesWide={2} notesTall={2} />,
      { wrapper: TestWrapper },
    );
    const rows = container.querySelectorAll("[data-note-row]");
    expect(rows).toHaveLength(6);

    // Row at index 0 should NOT have seam
    expect(rows[0]).not.toHaveAttribute("data-note-row-seam");
    // Row at index 3 should have seam
    expect(rows[3]).toHaveAttribute("data-note-row-seam", "true");
  });
});

describe("BoardDisplay (isStatic=true) variable-size grid rendering", () => {
  it("test 11: note_array 4×1 (3×60) renders 180 tiles", () => {
    const { container } = render(
      <BoardDisplay message="" deviceType="note_array" notesWide={4} notesTall={1} isStatic={true} />,
      { wrapper: TestWrapper },
    );
    const tiles = container.querySelectorAll("[data-note-tile]");
    expect(tiles).toHaveLength(180); // 3 rows × 60 cols
  });

  it("test 12: flagship (isStatic=true) renders 132 tiles with no seam attributes", () => {
    const { container } = render(<BoardDisplay message="" deviceType="flagship" isStatic={true} />, {
      wrapper: TestWrapper,
    });
    const tiles = container.querySelectorAll("[data-note-tile]");
    expect(tiles).toHaveLength(132); // 6 rows × 22 cols

    const colSeams = container.querySelectorAll("[data-note-col-seam]");
    expect(colSeams).toHaveLength(0);

    const rowSeams = container.querySelectorAll("[data-note-row-seam]");
    expect(rowSeams).toHaveLength(0);
  });
});

describe("BoardDisplay (isStatic=false / animated) seam rendering", () => {
  it("test 13: animated note_array 4×1 (3×60) has 9 col seams (cols 15/30/45 × 3 rows)", () => {
    const { container } = render(
      <BoardDisplay message="" deviceType="note_array" notesWide={4} notesTall={1} isStatic={false} />,
      { wrapper: TestWrapper },
    );
    const tiles = container.querySelectorAll("[data-note-tile]");
    expect(tiles).toHaveLength(180); // 3 rows × 60 cols
    const colSeams = container.querySelectorAll("[data-note-col-seam='true']");
    expect(colSeams).toHaveLength(9); // 3 seams/row (cols 15,30,45) × 3 rows
  });

  it("test 14: animated note_array 2×2 (6×30) has a row seam at rowIdx 3", () => {
    const { container } = render(
      <BoardDisplay message="" deviceType="note_array" notesWide={2} notesTall={2} isStatic={false} />,
      { wrapper: TestWrapper },
    );
    const rowSeams = container.querySelectorAll("[data-note-row-seam='true']");
    expect(rowSeams).toHaveLength(1); // single row boundary at row 3 (6 rows total)
  });

  it("test 15: animated flagship has no seam attributes", () => {
    const { container } = render(<BoardDisplay message="" deviceType="flagship" isStatic={false} />, {
      wrapper: TestWrapper,
    });
    expect(container.querySelectorAll("[data-note-col-seam]")).toHaveLength(0);
    expect(container.querySelectorAll("[data-note-row-seam]")).toHaveLength(0);
  });
});
