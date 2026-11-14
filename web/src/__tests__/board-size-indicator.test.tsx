import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BoardSizeIndicator } from "@/components/board-size-indicator";

describe("BoardSizeIndicator", () => {
  // ── Flagship ──────────────────────────────────────────────────────────────────
  describe("flagship", () => {
    it('renders "22 × 6" for flagship (cols × rows, 07 57:27771)', () => {
      render(<BoardSizeIndicator deviceType="flagship" />);
      // Visual order is cols × rows, as 07 `57:27771` reads "45 × 3" (slice 2.4).
      expect(screen.getByRole("img")).toHaveTextContent("22 × 6");
      // The accessible label names each dimension explicitly (order-independent).
      expect(screen.getByRole("img")).toHaveAttribute("aria-label", "22 columns by 6 rows");
    });

    it("does NOT render the · separator for flagship", () => {
      render(<BoardSizeIndicator deviceType="flagship" />);
      expect(screen.getByRole("img")).not.toHaveTextContent("·");
    });
  });

  // ── Note ─────────────────────────────────────────────────────────────────────
  describe("note", () => {
    it('renders "15 × 3" for note (cols × rows, 07 57:27771)', () => {
      render(<BoardSizeIndicator deviceType="note" />);
      const el = screen.getByRole("img");
      expect(el).toHaveTextContent("15 × 3");
      expect(el).toHaveAttribute("aria-label", "15 columns by 3 rows");
    });

    it("does NOT render the · separator for note", () => {
      render(<BoardSizeIndicator deviceType="note" />);
      expect(screen.getByRole("img")).not.toHaveTextContent("·");
    });
  });

  // ── note_array — all 5 presets ────────────────────────────────────────────────
  describe("note_array presets", () => {
    it("2 side-by-side: 30 × 3 · 2 side-by-side", () => {
      render(<BoardSizeIndicator deviceType="note_array" notesWide={2} notesTall={1} />);
      expect(screen.getByRole("img")).toHaveTextContent("30 × 3 · 2 side-by-side");
      expect(screen.getByRole("img")).toHaveAttribute("aria-label", "30 columns by 3 rows, 2 side-by-side");
    });

    it("4 side-by-side: 60 × 3 · 4 side-by-side", () => {
      render(<BoardSizeIndicator deviceType="note_array" notesWide={4} notesTall={1} />);
      expect(screen.getByRole("img")).toHaveTextContent("60 × 3 · 4 side-by-side");
      expect(screen.getByRole("img")).toHaveAttribute("aria-label", "60 columns by 3 rows, 4 side-by-side");
    });

    it("2 stacked: 15 × 6 · 2 stacked", () => {
      render(<BoardSizeIndicator deviceType="note_array" notesWide={1} notesTall={2} />);
      expect(screen.getByRole("img")).toHaveTextContent("15 × 6 · 2 stacked");
      expect(screen.getByRole("img")).toHaveAttribute("aria-label", "15 columns by 6 rows, 2 stacked");
    });

    it("4 stacked: 15 × 12 · 4 stacked", () => {
      render(<BoardSizeIndicator deviceType="note_array" notesWide={1} notesTall={4} />);
      expect(screen.getByRole("img")).toHaveTextContent("15 × 12 · 4 stacked");
      expect(screen.getByRole("img")).toHaveAttribute("aria-label", "15 columns by 12 rows, 4 stacked");
    });

    it("2×2 grid: 30 × 6 · 2×2 grid (brief acceptance case)", () => {
      render(<BoardSizeIndicator deviceType="note_array" notesWide={2} notesTall={2} />);
      expect(screen.getByRole("img")).toHaveTextContent("30 × 6 · 2×2 grid");
      expect(screen.getByRole("img")).toHaveAttribute("aria-label", "30 columns by 6 rows, 2×2 grid");
    });
  });

  // ── note_array — custom (no matching preset) ──────────────────────────────────
  describe("note_array custom", () => {
    it("3×2 (custom, no preset): 45 × 6 · Custom", () => {
      render(<BoardSizeIndicator deviceType="note_array" notesWide={3} notesTall={2} />);
      expect(screen.getByRole("img")).toHaveTextContent("45 × 6 · Custom");
    });

    it("1×1 (custom, not a preset): 15 × 3 · Custom", () => {
      render(<BoardSizeIndicator deviceType="note_array" notesWide={1} notesTall={1} />);
      expect(screen.getByRole("img")).toHaveTextContent("15 × 3 · Custom");
    });
  });

  // ── i18n / aria-label ─────────────────────────────────────────────────────────
  describe("i18n / accessibility", () => {
    it("aria-label for flagship uses ariaLabelColsRows key: '22 columns by 6 rows'", () => {
      render(<BoardSizeIndicator deviceType="flagship" />);
      expect(screen.getByRole("img")).toHaveAttribute("aria-label", "22 columns by 6 rows");
    });

    it("aria-label for note_array 2×2 uses ariaLabelColsRowsWithLayout key", () => {
      render(<BoardSizeIndicator deviceType="note_array" notesWide={2} notesTall={2} />);
      expect(screen.getByRole("img")).toHaveAttribute("aria-label", "30 columns by 6 rows, 2×2 grid");
    });
  });

  // ── panel (FiestaPanel, fit per character) ────────────────────────────────────
  describe("panel", () => {
    it("renders the panel's character grid as cols × rows with a Panel label", () => {
      render(<BoardSizeIndicator deviceType="panel" gridRows={12} gridCols={29} />);
      const el = screen.getByRole("img");
      expect(el).toHaveTextContent("29 × 12");
      expect(el).toHaveTextContent("Panel");
      expect(el).toHaveAttribute("aria-label", "29 columns by 12 rows, Panel");
    });

    // #2369: an LED output board's grid can be narrower than a Note (floor
    // 1 row by 5 columns, src/devices.py). A 13 × 3 AWTRIX board was labelled 15 × 3.
    it("labels an LED panel narrower than a Note with its own grid (#2369)", () => {
      render(<BoardSizeIndicator deviceType="panel" gridRows={3} gridCols={13} />);
      const el = screen.getByRole("img");
      expect(el).toHaveTextContent("13 × 3 · Panel");
      expect(el).toHaveAttribute("aria-label", "13 columns by 3 rows, Panel");
    });

    it("labels a Pixoo 64's 10 × 8 grid as 10 × 8", () => {
      render(<BoardSizeIndicator deviceType="panel" gridRows={8} gridCols={10} />);
      const el = screen.getByRole("img");
      expect(el).toHaveTextContent("10 × 8 · Panel");
      expect(el).toHaveAttribute("aria-label", "10 columns by 8 rows, Panel");
    });

    // The released UI must preserve the small-LED floor used by core.
    it("labels a TC001's 8 × 1 grid as 8 × 1", () => {
      render(<BoardSizeIndicator deviceType="panel" gridRows={1} gridCols={8} />);
      const el = screen.getByRole("img");
      expect(el).toHaveTextContent("8 × 1 · Panel");
      expect(el).toHaveAttribute("aria-label", "8 columns by 1 row, Panel");
    });
  });

  // ── className prop forwarding ─────────────────────────────────────────────────
  describe("className prop", () => {
    it("forwards extra className to wrapper element", () => {
      const { container } = render(<BoardSizeIndicator deviceType="flagship" className="my-custom-class" />);
      expect(container.querySelector(".my-custom-class")).toBeInTheDocument();
    });
  });
});
