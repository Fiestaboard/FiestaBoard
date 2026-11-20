import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CurrentBoardProvider } from "@/components/current-board-context";

import PagesPage from "../../app/routes/pages._index";
import { server } from "./mocks/server";

vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
}));
vi.mock("@/components/smart-link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a>,
}));

const pages = [
  { id: "alpha", name: "Alpha", device_type: "flagship", template: ["X"], created_at: "2024-01-01T00:00:00Z" },
  {
    id: "den",
    name: "Den TV Family Board",
    device_type: "panel",
    grid_rows: 14,
    grid_cols: 34,
    template: ["X"],
    created_at: "2024-01-02T00:00:00Z",
  },
].map((page) => ({ ...page, type: "template", duration_seconds: 300 }));

function renderLibrary() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <CurrentBoardProvider>
        <PagesPage />
      </CurrentBoardProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  server.use(
    http.get("/api/settings/board", () =>
      HttpResponse.json({ board_type: "black", devices: ["flagship"], boards: [] }),
    ),
    http.get("/api/v1/pages", () => HttpResponse.json({ pages, total: pages.length })),
    http.get("/api/v1/collections", () => HttpResponse.json({ collections: [], total: 0 })),
    http.get("/api/panels", () => HttpResponse.json({ panels: [], total: 0 })),
  );
});

// BB-B-28: the board picture inside a card is decorative, so every card is
// named the same way (its name and size), whether or not the preview has
// rendered; and in the list the page name keeps its room before the fit note.
describe("Pages library card names (BB-B-28)", () => {
  it("names grid cards by page and size only, never by the board text", async () => {
    localStorage.setItem("fiestaboard_pages_view_mode", "grid");
    server.use(
      http.post("/api/pages/preview/batch", () =>
        HttpResponse.json({
          previews: { alpha: { page_id: "alpha", message: "DEBUG ME", formatted: "DEBUG ME" } },
          total: 1,
          successful: 1,
        }),
      ),
    );
    renderLibrary();
    const card = (await screen.findByText("Alpha")).closest("button")!;
    await new Promise((resolve) => setTimeout(resolve, 300));
    expect(card).toHaveAccessibleName(/^Alpha/);
    expect(card.getAttribute("aria-label") ?? card.textContent).not.toMatch(/DEBUG ME/);
    expect(card.querySelector("[data-card-preview]")).toHaveAttribute("aria-hidden", "true");
  });

  it("lets the list name take its room before the fit note", async () => {
    localStorage.setItem("fiestaboard_pages_view_mode", "list");
    renderLibrary();
    const name = await screen.findByText("Alpha");
    expect(name).toHaveClass("shrink-0");
  });
});
