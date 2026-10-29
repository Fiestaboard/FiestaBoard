import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BoardSizeIndicator } from "@/components/board-size-indicator";

describe("BoardSizeIndicator", () => {
  // ── Flagship ──────────────────────────────────────────────────────────────────
  describe("flagship", () => {
    it('renders "6 × 22" for flagship (rows × cols)', () => {
      render(<BoardSizeIndicator deviceType="flagship" />);
      // Visual order is rows × cols, matching the wizard's "6 × 22 characters".
      expect(screen.getByRole("img")).toHaveTextContent("6 × 22");
      // The accessible label names each dimension explicitly (order-independent).
      expect(screen.getByRole("img")).toHaveAttribute("aria-label", "6 rows by 22 columns");
    });

    it("does NOT render the · separator for flagship", () => {
      render(<BoardSizeIndicator deviceType="flagship" />);
      expect(screen.getByRole("img")).not.toHaveTextContent("·");
    });
  });

  // ── Note ─────────────────────────────────────────────────────────────────────
  describe("note", () => {
    it('renders "3 × 15" for note (rows × cols)', () => {
      render(<BoardSizeIndicator deviceType="note" />);
      const el = screen.getByRole("img");
      expect(el).toHaveTextContent("3 × 15");
      expect(el).toHaveAttribute("aria-label", "3 rows by 15 columns");
    });

    it("does NOT render the · separator for note", () => {
      render(<BoardSizeIndicator deviceType="note" />);
      expect(screen.getByRole("img")).not.toHaveTextContent("·");
    });
  });

  // ── note_array — all 5 presets ────────────────────────────────────────────────
  describe("note_array presets", () => {
    it("2 side-by-side: 3 × 30 · 2 side-by-side", () => {
      render(<BoardSizeIndicator deviceType="note_array" notesWide={2} notesTall={1} />);
      expect(screen.getByRole("img")).toHaveTextContent("3 × 30 · 2 side-by-side");
      expect(screen.getByRole("img")).toHaveAttribute("aria-label", "3 rows by 30 columns, 2 side-by-side");
    });

    it("4 side-by-side: 3 × 60 · 4 side-by-side", () => {
      render(<BoardSizeIndicator deviceType="note_array" notesWide={4} notesTall={1} />);
      expect(screen.getByRole("img")).toHaveTextContent("3 × 60 · 4 side-by-side");
      expect(screen.getByRole("img")).toHaveAttribute("aria-label", "3 rows by 60 columns, 4 side-by-side");
    });

    it("2 stacked: 6 × 15 · 2 stacked", () => {
      render(<BoardSizeIndicator deviceType="note_array" notesWide={1} notesTall={2} />);
      expect(screen.getByRole("img")).toHaveTextContent("6 × 15 · 2 stacked");
      expect(screen.getByRole("img")).toHaveAttribute("aria-label", "6 rows by 15 columns, 2 stacked");
    });

    it("4 stacked: 12 × 15 · 4 stacked", () => {
      render(<BoardSizeIndicator deviceType="note_array" notesWide={1} notesTall={4} />);
      expect(screen.getByRole("img")).toHaveTextContent("12 × 15 · 4 stacked");
      expect(screen.getByRole("img")).toHaveAttribute("aria-label", "12 rows by 15 columns, 4 stacked");
    });

    it("2×2 grid: 6 × 30 · 2×2 grid (brief acceptance case)", () => {
      render(<BoardSizeIndicator deviceType="note_array" notesWide={2} notesTall={2} />);
      expect(screen.getByRole("img")).toHaveTextContent("6 × 30 · 2×2 grid");
      expect(screen.getByRole("img")).toHaveAttribute("aria-label", "6 rows by 30 columns, 2×2 grid");
    });
  });

  // ── note_array — custom (no matching preset) ──────────────────────────────────
  describe("note_array custom", () => {
    it("3×2 (custom, no preset): 6 × 45 · Custom", () => {
      render(<BoardSizeIndicator deviceType="note_array" notesWide={3} notesTall={2} />);
      expect(screen.getByRole("img")).toHaveTextContent("6 × 45 · Custom");
    });

    it("1×1 (custom, not a preset): 3 × 15 · Custom", () => {
      render(<BoardSizeIndicator deviceType="note_array" notesWide={1} notesTall={1} />);
      expect(screen.getByRole("img")).toHaveTextContent("3 × 15 · Custom");
    });
  });

  // ── i18n / aria-label ─────────────────────────────────────────────────────────
  describe("i18n / accessibility", () => {
    it("aria-label for flagship uses ariaLabel key: '6 rows by 22 columns'", () => {
      render(<BoardSizeIndicator deviceType="flagship" />);
      expect(screen.getByRole("img")).toHaveAttribute("aria-label", "6 rows by 22 columns");
    });

    it("aria-label for note_array 2×2 uses ariaLabelWithLayout key", () => {
      render(<BoardSizeIndicator deviceType="note_array" notesWide={2} notesTall={2} />);
      expect(screen.getByRole("img")).toHaveAttribute("aria-label", "6 rows by 30 columns, 2×2 grid");
    });
  });

  // ── panel (FiestaPanel, fit per character) ────────────────────────────────────
  describe("panel", () => {
    it("renders the panel's character grid as rows × cols with a Panel label", () => {
      render(<BoardSizeIndicator deviceType="panel" gridRows={12} gridCols={29} />);
      const el = screen.getByRole("img");
      expect(el).toHaveTextContent("12 × 29");
      expect(el).toHaveTextContent("Panel");
      expect(el).toHaveAttribute("aria-label", "12 rows by 29 columns, Panel");
    });

    // #2369: an LED output board's grid can be narrower than a Note (floor
    // 1 × 5, src/devices.py). A 3 × 13 AWTRIX board was labelled 3 × 15.
    it("labels an LED panel narrower than a Note with its own grid (#2369)", () => {
      render(<BoardSizeIndicator deviceType="panel" gridRows={3} gridCols={13} />);
      const el = screen.getByRole("img");
      expect(el).toHaveTextContent("3 × 13 · Panel");
      expect(el).toHaveAttribute("aria-label", "3 rows by 13 columns, Panel");
    });

    it("labels a Pixoo 64's 8 × 10 grid as 8 × 10", () => {
      render(<BoardSizeIndicator deviceType="panel" gridRows={8} gridCols={10} />);
      const el = screen.getByRole("img");
      expect(el).toHaveTextContent("8 × 10 · Panel");
      expect(el).toHaveAttribute("aria-label", "8 rows by 10 columns, Panel");
    });

    // Skipped until @fiestaboard/ui (8.14.2) lowers its own 3 × 10 clamp to the
    // 1 × 5 floor: the kit clamps gridRows/gridCols before this app renders them.
    it.skip("labels a TC001's 1 × 8 grid as 1 × 8", () => {
      render(<BoardSizeIndicator deviceType="panel" gridRows={1} gridCols={8} />);
      const el = screen.getByRole("img");
      expect(el).toHaveTextContent("1 × 8 · Panel");
      expect(el).toHaveAttribute("aria-label", "1 row by 8 columns, Panel");
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
