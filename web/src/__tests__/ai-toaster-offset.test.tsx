import { act, render, screen, waitFor } from "@testing-library/react";
import { useEffect } from "react";
import { toast } from "sonner";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SpotlightProvider, useSpotlight } from "@/components/ai-spotlight/spotlight-provider";
import { GlobalAiPanelProvider, useGlobalAiPanel } from "@/components/global-ai-panel-context";
import { Toaster } from "@/components/ui/sonner";

// Toasts and the drawer both live bottom-right, so "Schedule created · Undo"
// landed on the composer the user was typing in (#2024). These pin where the
// toasts go instead.

function OpenTheDrawer() {
  const { open } = useGlobalAiPanel();
  useEffect(() => open(), [open]);
  return null;
}

/** Puts a walkthrough on screen, the way the choreography engine starts one. */
function StartWalkthrough() {
  const { show } = useSpotlight();
  useEffect(() => show({ anchor: "#page-name", caption: "Naming the page…" }), [show]);
  return null;
}

function setViewport(isDesktop: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: isDesktop && query.includes("1024px"),
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

/** Sonner draws the list only once something is in it. */
async function toaster(): Promise<HTMLElement> {
  act(() => {
    toast.success("Schedule created.");
  });
  let element: HTMLElement | null = null;
  await waitFor(() => {
    element = document.querySelector<HTMLElement>("[data-sonner-toaster]");
    expect(element).not.toBeNull();
  });
  return element!;
}

/** Sonner's own default corner offset, in every direction. */
const DEFAULT_OFFSET = "24px";

describe("Toaster beside the FiestaBot drawer", () => {
  beforeEach(() => {
    setViewport(true);
  });

  it("stays in its usual corner while the drawer is closed", async () => {
    render(
      <GlobalAiPanelProvider>
        <Toaster />
      </GlobalAiPanelProvider>,
    );
    const element = await toaster();
    expect(element.style.getPropertyValue("--offset-right")).toBe(DEFAULT_OFFSET);
    expect(element).toHaveAttribute("data-y-position", "bottom");
  });

  it("steps left of the open drawer, by the drawer's live width", async () => {
    render(
      <GlobalAiPanelProvider>
        <OpenTheDrawer />
        <Toaster />
      </GlobalAiPanelProvider>,
    );
    const element = await toaster();
    // The drawer's own width variable, so a drag moves the toasts with it.
    expect(element.style.getPropertyValue("--offset-right")).toBe("calc(var(--ai-drawer-width, 384px) + 1.5rem)");
    expect(element).toHaveAttribute("data-y-position", "bottom");
  });

  it("goes to the top of the screen on a phone, where the drawer is the screen", async () => {
    setViewport(false);
    render(
      <GlobalAiPanelProvider>
        <OpenTheDrawer />
        <Toaster />
      </GlobalAiPanelProvider>,
    );
    const element = await toaster();
    expect(element).toHaveAttribute("data-y-position", "top");
    expect(element.style.getPropertyValue("--offset-right")).toBe(DEFAULT_OFFSET);
  });

  it("goes to the top while a walkthrough is on screen, whose caption owns the bottom centre", async () => {
    render(
      <SpotlightProvider>
        <GlobalAiPanelProvider>
          <OpenTheDrawer />
          <StartWalkthrough />
          <Toaster />
        </GlobalAiPanelProvider>
      </SpotlightProvider>,
    );
    const element = await toaster();
    // The spotlight caption is fixed at bottom-centre with its own Stop
    // button; a toast offset left of the drawer lands exactly on it (#2024
    // over #2010), and a toast that covers Stop is a toast that cancels the
    // only way out of a walkthrough.
    expect(element).toHaveAttribute("data-y-position", "top");
    expect(element.style.getPropertyValue("--offset-right")).toBe(DEFAULT_OFFSET);
  });

  it("renders without a drawer context at all", () => {
    render(<Toaster />);
    expect(screen.getByLabelText(/notifications/i)).toBeInTheDocument();
  });
});
