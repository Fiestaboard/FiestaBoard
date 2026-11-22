import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ActivePageDisplay } from "@/components/active-page-display";
import { ReduceMotionApplier } from "@/components/reduce-motion-applier";
import { AccessibilitySettings } from "@/components/settings/accessibility-settings";
import { useBoardAnimationsEnabled } from "@/hooks/use-board-animations";
import { BROWSER_A11Y_KEYS } from "@/hooks/use-browser-a11y";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

import { mockDisplaySettings } from "./mocks/handlers";
import { server } from "./mocks/server";

// BB-FC-12: 07e Accessibility (`333:57132`) "Motion and reading · For this
// browser." with four switches, each stored in this browser and wired to
// what it changes.

vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
}));

vi.mock("@/components/smart-link", () => ({
  default: ({ children, href, ...rest }: { children: React.ReactNode; href: string }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

function Wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
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

function withHub(display: Partial<typeof mockDisplaySettings> = {}) {
  const writes: unknown[] = [];
  server.use(
    http.get("/api/settings/all", () => HttpResponse.json({ display: { ...mockDisplaySettings, ...display } })),
    http.put("/api/settings/display", async ({ request }) => {
      writes.push(await request.json());
      return HttpResponse.json({ status: "success" });
    }),
  );
  return writes;
}

function osReducesMotion(matches: boolean) {
  vi.mocked(window.matchMedia).mockImplementation(
    (query: string) =>
      ({
        matches: query === "(prefers-reduced-motion: reduce)" ? matches : false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }) as unknown as MediaQueryList,
  );
}

const html = document.documentElement;

afterEach(() => {
  for (const key of Object.values(BROWSER_A11Y_KEYS)) localStorage.removeItem(key);
  html.classList.remove("reduce-motion", "board-animations-off", "a11y-large-targets", "a11y-board-high-contrast");
  osReducesMotion(false);
});

const SWITCHES = [
  [
    "Reduce motion",
    "Follows your phone's setting. Turns off tile flips and the hopping-taco animation.",
    "reduceMotion",
  ],
  ["Read board changes aloud", "Screen readers announce what changed on the board, line by line.", "readAloud"],
  ["Larger touch targets", "48 px rows and buttons everywhere.", "largeTargets"],
  ["High-contrast board text", "Brighter glyphs on board black.", "boardContrast"],
] as const;

describe("Accessibility › Motion and reading", () => {
  it("draws the 07e card: four switches for this browser", async () => {
    withHub();
    render(<AccessibilitySettings />, { wrapper: Wrapper });
    expect(screen.getByText("Motion and reading")).toBeInTheDocument();
    expect(screen.getByText("For this browser.")).toBeInTheDocument();
    for (const [name, hint] of SWITCHES) {
      const toggle = await screen.findByRole("switch", { name });
      expect(toggle).toHaveAccessibleDescription(hint);
      expect(toggle).not.toBeChecked();
    }
  });

  it.each(SWITCHES)("stores %s in this browser and never writes the hub", async (name, _hint, pref) => {
    const writes = withHub();
    render(<AccessibilitySettings />, { wrapper: Wrapper });
    const toggle = await screen.findByRole("switch", { name });
    await userEvent.click(toggle);
    expect(localStorage.getItem(BROWSER_A11Y_KEYS[pref])).toBe("on");
    expect(toggle).toBeChecked();
    expect(writes).toEqual([]);
  });

  it("follows the phone's reduced-motion setting until this browser chooses", async () => {
    osReducesMotion(true);
    withHub();
    render(<AccessibilitySettings />, { wrapper: Wrapper });
    const toggle = await screen.findByRole("switch", { name: "Reduce motion" });
    expect(toggle).toBeChecked();
  });

  it("shows Reduce motion on and locked while the hub turns it on for everyone", async () => {
    withHub({ reduce_motion: true });
    render(<AccessibilitySettings />, { wrapper: Wrapper });
    const toggle = await screen.findByRole("switch", { name: "Reduce motion" });
    await waitFor(() => expect(toggle).toBeChecked());
    expect(toggle).toBeDisabled();
    expect(screen.getByText(/Reduce motion is on for everyone on this hub/)).toBeInTheDocument();
  });
});

describe("Per-browser preferences reach the app", () => {
  it("Reduce motion in this browser stops board flips and site motion", async () => {
    withHub({ reduce_motion: false, board_animations: "on" });
    localStorage.setItem(BROWSER_A11Y_KEYS.reduceMotion, "on");
    const { result } = renderHook(() => useBoardAnimationsEnabled(), { wrapper: Wrapper });
    render(<ReduceMotionApplier />, { wrapper: Wrapper });
    await waitFor(() => expect(html).toHaveClass("reduce-motion"));
    expect(html).toHaveClass("board-animations-off");
    await waitFor(() => expect(result.current).toBe(false));
  });

  it("the hub's Reduce motion still applies when this browser has it off", async () => {
    withHub({ reduce_motion: true });
    localStorage.setItem(BROWSER_A11Y_KEYS.reduceMotion, "off");
    render(<ReduceMotionApplier />, { wrapper: Wrapper });
    await waitFor(() => expect(html).toHaveClass("reduce-motion"));
  });

  it("Larger touch targets and High-contrast board text mark the document", async () => {
    withHub();
    render(
      <Wrapper>
        <AccessibilitySettings />
        <ReduceMotionApplier />
      </Wrapper>,
    );
    expect(html).not.toHaveClass("a11y-large-targets");
    await userEvent.click(await screen.findByRole("switch", { name: "Larger touch targets" }));
    expect(html).toHaveClass("a11y-large-targets");
    await userEvent.click(screen.getByRole("switch", { name: "High-contrast board text" }));
    expect(html).toHaveClass("a11y-board-high-contrast");
    await userEvent.click(screen.getByRole("switch", { name: "Larger touch targets" }));
    expect(html).not.toHaveClass("a11y-large-targets");
  });

  it("another tab's change is picked up", async () => {
    withHub();
    render(<ReduceMotionApplier />, { wrapper: Wrapper });
    localStorage.setItem(BROWSER_A11Y_KEYS.boardContrast, "on");
    act(() => {
      window.dispatchEvent(new StorageEvent("storage", { key: BROWSER_A11Y_KEYS.boardContrast }));
    });
    expect(html).toHaveClass("a11y-board-high-contrast");
  });
});

describe("Read board changes aloud", () => {
  function withBoard() {
    withHub();
    server.use(
      http.get("/api/board/current-message", () =>
        HttpResponse.json({
          characters: [],
          message: "HELLO",
          rows: 6,
          cols: 22,
          expected_characters: null,
          cached_at: null,
          api_mode: "local",
        }),
      ),
    );
  }

  it("gives Home's live board a polite live region when on", async () => {
    localStorage.setItem(BROWSER_A11Y_KEYS.readAloud, "on");
    withBoard();
    const { container } = render(<ActivePageDisplay />, { wrapper: Wrapper });
    await waitFor(() => expect(screen.getByTestId("char-tile-0-0")).toBeInTheDocument());
    const region = container.querySelector('[data-slot="board-display-announcer"]');
    expect(region).toHaveAttribute("aria-live", "polite");
  });

  it("stays silent by default", async () => {
    withBoard();
    const { container } = render(<ActivePageDisplay />, { wrapper: Wrapper });
    await waitFor(() => expect(screen.getByTestId("char-tile-0-0")).toBeInTheDocument());
    expect(container.querySelector('[data-slot="board-display-announcer"]')).toBeNull();
  });
});
