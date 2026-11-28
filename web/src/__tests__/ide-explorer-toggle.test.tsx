import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { useScrollOnlyTabStop } from "@/components/board-viewport";
import { IdeExplorerToggle, useExplorerOverlayDismiss, useExplorerToggle } from "@/components/ide/ide-explorer";

// UX-5-1 (DD-W168): one toggle, `aria-pressed`, its name the panel's.
// FABLE-2652 §3.6: the 1024–1279 overlay closes on Esc and on a press outside.

function Harness({ overlay }: { overlay: boolean }) {
  const toggle = useExplorerToggle("flagship");
  const [panel, setPanel] = useState<HTMLElement | null>(null);
  useExplorerOverlayDismiss(toggle, panel, overlay);
  return (
    <>
      <IdeExplorerToggle toggle={toggle} />
      <div ref={setPanel} data-testid="column">
        {toggle.open && (
          <nav aria-label="Explorer">
            <button type="button">inside</button>
          </nav>
        )}
      </div>
      <textarea aria-label="Template" />
      <button type="button">elsewhere</button>
    </>
  );
}

const toggleButton = () => screen.getByRole("button", { name: "Explorer" });
const nav = () => screen.queryByRole("navigation", { name: "Explorer" });

beforeEach(() => localStorage.removeItem("fiestaboard_ide_explorer:flagship"));
afterEach(cleanup);

describe("the Explorer toggle", () => {
  it("is one pressed/unpressed button with a constant name, remembered per board kind", () => {
    render(<Harness overlay={false} />);
    expect(toggleButton()).toHaveAttribute("aria-pressed", "false");
    expect(nav()).toBeNull();
    fireEvent.click(toggleButton());
    expect(toggleButton()).toHaveAttribute("aria-pressed", "true");
    expect(nav()).not.toBeNull();
    expect(localStorage.getItem("fiestaboard_ide_explorer:flagship")).toBe("open");
    fireEvent.click(toggleButton());
    expect(toggleButton()).toHaveAttribute("aria-pressed", "false");
    expect(localStorage.getItem("fiestaboard_ide_explorer:flagship")).toBe("closed");
  });
});

describe("the Explorer overlay (1024–1279 px)", () => {
  it("closes on Esc and puts focus back on the toggle", () => {
    render(<Harness overlay />);
    fireEvent.click(toggleButton());
    screen.getByRole("button", { name: "inside" }).focus();
    fireEvent.keyDown(screen.getByRole("button", { name: "inside" }), { key: "Escape" });
    expect(nav()).toBeNull();
    expect(toggleButton()).toHaveFocus();
  });

  it("leaves Esc to a text field outside it", () => {
    render(<Harness overlay />);
    fireEvent.click(toggleButton());
    fireEvent.keyDown(screen.getByRole("textbox", { name: "Template" }), { key: "Escape" });
    expect(nav()).not.toBeNull();
  });

  it("closes on a press outside it and its toggle, not on one inside", () => {
    render(<Harness overlay />);
    fireEvent.click(toggleButton());
    fireEvent.pointerDown(screen.getByRole("button", { name: "inside" }));
    expect(nav()).not.toBeNull();
    fireEvent.pointerDown(toggleButton());
    expect(nav()).not.toBeNull();
    fireEvent.pointerDown(screen.getByRole("button", { name: "elsewhere" }));
    expect(nav()).toBeNull();
  });

  it("does nothing when the Explorer is a column (1280 and wider)", () => {
    render(<Harness overlay={false} />);
    fireEvent.click(toggleButton());
    fireEvent.keyDown(document.body, { key: "Escape" });
    fireEvent.pointerDown(screen.getByRole("button", { name: "elsewhere" }));
    expect(nav()).not.toBeNull();
  });
});

// FP-5 (UX-9-2): the kit's board scroller is a Tab stop only while it scrolls.
describe("useScrollOnlyTabStop", () => {
  function Viewport({ fit }: { fit: boolean }) {
    const [root, setRoot] = useState<HTMLElement | null>(null);
    useScrollOnlyTabStop(root);
    return (
      <div ref={setRoot}>
        {/* The kit's scroller as it renders: a region, `overflow-x-hidden` at Fit, `-auto` at Actual size. */}
        <div
          data-slot="board-viewport-scroller"
          role="region"
          tabIndex={0}
          aria-label="Board preview"
          className={fit ? "overflow-x-hidden" : "overflow-x-auto"}
        />
      </div>
    );
  }

  it("takes a scroller that can't scroll (Fit) out of the Tab order", async () => {
    render(<Viewport fit />);
    await act(async () => {});
    expect(screen.getByRole("region", { name: "Board preview" })).toHaveAttribute("tabindex", "-1");
  });

  it("keeps a scroller that scrolls (Actual size) in it", async () => {
    render(<Viewport fit={false} />);
    await act(async () => {});
    expect(screen.getByRole("region", { name: "Board preview" })).toHaveAttribute("tabindex", "0");
  });

  it("follows the kit from Fit to Actual size and back", async () => {
    const view = render(<Viewport fit />);
    await act(async () => {});
    const scroller = screen.getByRole("region", { name: "Board preview" });
    expect(scroller).toHaveAttribute("tabindex", "-1");
    view.rerender(<Viewport fit={false} />);
    await act(async () => {});
    expect(scroller).toHaveAttribute("tabindex", "0");
    view.rerender(<Viewport fit />);
    await act(async () => {});
    expect(scroller).toHaveAttribute("tabindex", "-1");
  });
});
