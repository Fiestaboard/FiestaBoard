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
      expect(screen.queryByText("·")).not.toBeInTheDocument();
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
      expect(screen.queryByText("·")).not.toBeInTheDocument();
    });
  });

  // ── note_array — all 5 presets ────────────────────────────────────────────────
  describe("note_array presets", () => {
    it("2 side-by-side: 3 × 30 · 2 side-by-side", () => {
      render(<BoardSizeIndicator deviceType="note_array" notesWide={2} notesTall={1} />);
      expect(screen.getByRole("img")).toHaveTextContent("3 × 30");
      expect(screen.getByText("·")).toBeInTheDocument();
      expect(screen.getByText("2 side-by-side")).toBeInTheDocument();
      expect(screen.getByRole("img")).toHaveAttribute("aria-label", "3 rows by 30 columns, 2 side-by-side");
    });

    it("4 side-by-side: 3 × 60 · 4 side-by-side", () => {
      render(<BoardSizeIndicator deviceType="note_array" notesWide={4} notesTall={1} />);
      expect(screen.getByRole("img")).toHaveTextContent("3 × 60");
      expect(screen.getByText("·")).toBeInTheDocument();
      expect(screen.getByText("4 side-by-side")).toBeInTheDocument();
      expect(screen.getByRole("img")).toHaveAttribute("aria-label", "3 rows by 60 columns, 4 side-by-side");
    });

    it("2 stacked: 6 × 15 · 2 stacked", () => {
      render(<BoardSizeIndicator deviceType="note_array" notesWide={1} notesTall={2} />);
      expect(screen.getByRole("img")).toHaveTextContent("6 × 15");
      expect(screen.getByText("·")).toBeInTheDocument();
      expect(screen.getByText("2 stacked")).toBeInTheDocument();
      expect(screen.getByRole("img")).toHaveAttribute("aria-label", "6 rows by 15 columns, 2 stacked");
    });

    it("4 stacked: 12 × 15 · 4 stacked", () => {
      render(<BoardSizeIndicator deviceType="note_array" notesWide={1} notesTall={4} />);
      expect(screen.getByRole("img")).toHaveTextContent("12 × 15");
      expect(screen.getByText("·")).toBeInTheDocument();
      expect(screen.getByText("4 stacked")).toBeInTheDocument();
      expect(screen.getByRole("img")).toHaveAttribute("aria-label", "12 rows by 15 columns, 4 stacked");
    });

    it("2×2 grid: 6 × 30 · 2×2 grid (brief acceptance case)", () => {
      render(<BoardSizeIndicator deviceType="note_array" notesWide={2} notesTall={2} />);
      expect(screen.getByRole("img")).toHaveTextContent("6 × 30");
      expect(screen.getByText("·")).toBeInTheDocument();
      expect(screen.getByText("2×2 grid")).toBeInTheDocument();
      expect(screen.getByRole("img")).toHaveAttribute("aria-label", "6 rows by 30 columns, 2×2 grid");
    });
  });

  // ── note_array — custom (no matching preset) ──────────────────────────────────
  describe("note_array custom", () => {
    it("3×2 (custom, no preset): 6 × 45 · Custom", () => {
      render(<BoardSizeIndicator deviceType="note_array" notesWide={3} notesTall={2} />);
      expect(screen.getByRole("img")).toHaveTextContent("6 × 45");
      expect(screen.getByText("·")).toBeInTheDocument();
      expect(screen.getByText("Custom")).toBeInTheDocument();
    });

    it("1×1 (custom, not a preset): 3 × 15 · Custom", () => {
      render(<BoardSizeIndicator deviceType="note_array" notesWide={1} notesTall={1} />);
      expect(screen.getByRole("img")).toHaveTextContent("3 × 15");
      expect(screen.getByText("·")).toBeInTheDocument();
      expect(screen.getByText("Custom")).toBeInTheDocument();
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

  // ── className prop forwarding ─────────────────────────────────────────────────
  describe("className prop", () => {
    it("forwards extra className to wrapper element", () => {
      const { container } = render(<BoardSizeIndicator deviceType="flagship" className="my-custom-class" />);
      expect(container.querySelector(".my-custom-class")).toBeInTheDocument();
    });
  });
});
