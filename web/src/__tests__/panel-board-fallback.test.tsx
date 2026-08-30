/**
 * PanelBoard measurement fallback: when the tile grid can never be measured
 * (jsdom's zero-size layout stands in for a config/DOM disagreement on a
 * real TV), the board must become visible unscaled after the grace period —
 * never stay a silent, fully transparent black screen.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PanelBoard } from "@/components/panel/panel-board";

describe("PanelBoard measurement fallback", () => {
  it("reveals the board unscaled when measurement never succeeds", async () => {
    render(
      <PanelBoard
        message="HELLO"
        animationsEnabled={false}
        deviceType="note_array"
        notesWide={2}
        notesTall={4}
        rows={12}
        cols={30}
        boardColor="black"
        code62Glyph="heart"
        diagonalInches={55}
        calibration={1}
      />,
    );

    // Pre-measurement the crop window hides the board to avoid a flash of
    // unscaled content…
    const crop = screen.getByTestId("panel-board-crop");
    expect(crop.style.opacity).toBe("0");

    // …but a failed measurement must not leave the TV black forever.
    await waitFor(() => expect(crop.style.opacity).not.toBe("0"), { timeout: 4000 });
  });
});
