/**
 * TvPreview draws a panel's auto-fit grid on its TV outline. Panels are fit
 * per character, so the preview shows the character grid (rows × cols) and how
 * much of the screen it covers — not a count of 15×3 Note blocks.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TvPreview } from "@/components/panel/tv-preview";

describe("TvPreview", () => {
  it("states the per-character grid a 55-inch TV fits", () => {
    render(<TvPreview diagonalInches={55} aspectW={16} aspectH={9} />);
    expect(screen.getByTestId("tv-preview-meta")).toHaveTextContent("29 × 12 flaps at life size");
  });

  it("draws the character grid, not Note blocks", () => {
    render(<TvPreview diagonalInches={85} aspectW={16} aspectH={9} />);
    const grid = screen.getByTestId("tv-preview-grid");
    expect(grid).toHaveAttribute("data-cols", "45");
    expect(grid).toHaveAttribute("data-rows", "18");
    expect(screen.queryByTestId("tv-preview-block")).not.toBeInTheDocument();
  });

  it("covers nearly the whole width of the screen once fit per character", () => {
    // 29 columns at 24.5/15 in each is ~47.4 in of a 55" TV's ~47.9 in width.
    render(<TvPreview diagonalInches={55} aspectW={16} aspectH={9} />);
    const width = parseFloat(screen.getByTestId("tv-preview-grid").style.width);
    expect(width).toBeGreaterThan(95);
    expect(width).toBeLessThanOrEqual(100);
  });

  it("caps the drawn coverage at the full screen for a pocket display", () => {
    // A 3" screen still gets the minimum (Note-sized) grid, which the viewer
    // shrinks to fit — the preview must not draw it overflowing the outline.
    render(<TvPreview diagonalInches={3} aspectW={16} aspectH={9} />);
    const grid = screen.getByTestId("tv-preview-grid");
    expect(grid.style.width).toBe("100%");
    expect(grid.style.height).toBe("100%");
    expect(screen.getByTestId("tv-preview-meta")).toHaveTextContent("15 × 3 flaps at life size");
  });

  it("draws FiestaUI's television at the chosen size and aspect", () => {
    const { container } = render(<TvPreview diagonalInches={65} aspectW={21} aspectH={9} />);
    const tv = container.querySelector('[data-slot="tv-frame"]');
    expect(tv).toHaveAttribute("data-diagonal", "65");
    expect(tv).toHaveAttribute("data-aspect", (21 / 9).toFixed(4));
  });

  it("renders nothing for a non-positive diagonal", () => {
    const { container } = render(<TvPreview diagonalInches={0} aspectW={16} aspectH={9} />);
    expect(container).toBeEmptyDOMElement();
  });
});
