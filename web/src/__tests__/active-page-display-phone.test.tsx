import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ActivePageDisplay } from "@/components/active-page-display";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

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

function TestWrapper({ children }: { children: React.ReactNode }) {
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

const original = window.matchMedia;
function setPhone(phone: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: phone && /max-width: 76[67]/.test(query),
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

// BB-A-6 / BB-A-16 (07a `306:53086`): on a phone the board leads, edge to
// edge in the phone-hero placement, with no type-and-size row; the title has
// its own line.
describe("ActivePageDisplay on a phone", () => {
  beforeEach(() => setPhone(true));
  afterEach(() => {
    window.matchMedia = original;
  });

  it("leads with the board in the phone-hero placement, above the card", async () => {
    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    const card = await screen.findByTestId("now-showing");
    const hero = await screen.findByTestId("home-phone-board");
    expect(hero.querySelector('[data-layout="phone-hero"]')).not.toBeNull();
    expect(hero.compareDocumentPosition(card) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(card.querySelector('[data-slot="board-viewport"]')).toBeNull();
    expect(screen.queryByText(/Flagship 22 × 6/)).not.toBeInTheDocument();
  });

  it("gives the title its own line, so it is not cut short beside the mode", async () => {
    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    const title = await screen.findByRole("heading", { level: 2, name: "Weather Page" });
    // The mode badge moves to the header, so the title row is the title alone.
    expect(title.parentElement?.children).toHaveLength(1);
    const header = screen.getByTestId("now-showing").querySelector('[data-slot="now-showing-header"]');
    expect(header).toHaveTextContent("Manual Mode");
  });

  it("keeps the desktop card unchanged", async () => {
    setPhone(false);
    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    const card = await screen.findByTestId("now-showing");
    await waitFor(() =>
      expect(card.querySelector('[data-slot="board-viewport"], [data-slot="device-preview"]')).not.toBeNull(),
    );
    expect(screen.queryByTestId("home-phone-board")).not.toBeInTheDocument();
  });
});

// BB-FH-12 (07a `307:61756`, DD-W61): at medium width (768–1023) the Home
// board is the medium hero, whose bezel hugs a board that fits and settles a
// near fit to fill it, instead of the 02 viewport's full-width slab. Desktop
// keeps the 02 viewport until DD-W61's hug-vs-fill ask for >= 1024 is ruled.
function atWidth(width: number) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => {
    const min = /min-width:\s*(\d+)/.exec(query);
    const max = /max-width:\s*(\d+(?:\.\d+)?)/.exec(query);
    return {
      matches: (!min || width >= Number(min[1])) && (!max || width <= Number(max[1])),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    };
  });
}

describe("ActivePageDisplay above a phone", () => {
  afterEach(() => {
    window.matchMedia = original;
  });

  it("places the board as the medium hero at medium width", async () => {
    atWidth(900);
    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    const board = await screen.findByTestId("home-board-state");
    await waitFor(() => expect(board.querySelector('[data-layout="medium-hero"]')).not.toBeNull());
  });

  it("keeps the desktop board in the 02 viewport", async () => {
    atWidth(1280);
    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    const board = await screen.findByTestId("home-board-state");
    await waitFor(() => expect(board.querySelector("[data-slot=board-viewport]")).not.toBeNull());
    expect(board.querySelector("[data-layout]")).toBeNull();
  });
});
