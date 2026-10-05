/**
 * The Pages library opens on the display selected in the sidebar, and
 * "New page" on that display's tab starts a page for that display.
 *
 * An LED display from an output plugin (a Pixoo) is a custom-grid board, so
 * its pages live on the "panel" tab; with the Pixoo selected that tab opens
 * first, and a new page from it asks for no device — the editor then targets
 * the Pixoo exactly (its grid, model and character set). On another tab, New
 * page still asks for that tab's device.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CurrentBoardProvider } from "@/components/current-board-context";

import PagesPage from "../../app/routes/pages._index";
import { server } from "./mocks/server";

const push = vi.hoisted(() => vi.fn());

vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({ push, replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), loading: vi.fn() },
  Toaster: () => null,
}));

vi.mock("@/components/smart-link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a>,
}));

const BOARDS = [
  { id: "b-flag", name: "Hall", device_type: "flagship", board_color: "black" },
  {
    id: "b-pixoo",
    name: "Pixoo",
    device_type: "panel",
    board_color: "black",
    grid_rows: 10,
    grid_cols: 16,
    output: "divoom_pixoo",
    device_model: "divoom_pixoo64",
    charset: "led_3x5",
  },
];

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <CurrentBoardProvider>
        <PagesPage />
      </CurrentBoardProvider>
    </QueryClientProvider>,
  );
}

describe("PagesPage — the selected display", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    server.use(
      http.get("/api/settings/board", () =>
        HttpResponse.json({ board_type: "black", boards: BOARDS, devices: ["flagship", "panel"] }),
      ),
      http.get("/api/v1/pages", () =>
        HttpResponse.json({
          pages: [
            { id: "p1", name: "Hall Page", device_type: "flagship" },
            { id: "p2", name: "Pixoo Page", device_type: "panel", grid_rows: 10, grid_cols: 16 },
          ].map((p) => ({
            ...p,
            type: "template",
            template: [""],
            duration_seconds: 300,
            created_at: "2026-01-01T00:00:00Z",
            updated_at: "2026-01-01T00:00:00Z",
          })),
        }),
      ),
      http.post("/api/pages/preview/batch", () => HttpResponse.json({ previews: {}, total: 0, successful: 0 })),
      http.get("/api/v1/collections", () => HttpResponse.json({ collections: [] })),
      http.get("/api/panels", () => HttpResponse.json({ panels: [], total: 0 })),
    );
  });

  it("opens on the selected LED display's tab, with its page", async () => {
    localStorage.setItem("fiestaboard_current_board", "b-pixoo");
    renderPage();

    await waitFor(() => expect(screen.getByRole("tab", { name: "Panel" })).toHaveAttribute("aria-selected", "true"));
    expect(await screen.findByText("Pixoo Page")).toBeInTheDocument();
  });

  it("opens on the selected Flagship's tab", async () => {
    localStorage.setItem("fiestaboard_current_board", "b-flag");
    renderPage();

    await waitFor(() => expect(screen.getByRole("tab", { name: "Flagship" })).toHaveAttribute("aria-selected", "true"));
  });

  it("starts a new page for the selected display from its tab", async () => {
    localStorage.setItem("fiestaboard_current_board", "b-pixoo");
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(screen.getByRole("tab", { name: "Panel" })).toHaveAttribute("aria-selected", "true"));

    await user.click(screen.getByRole("button", { name: /New page/i }));
    expect(push).toHaveBeenCalledWith("/pages/new");
  });

  it("asks for the tab's device from another tab", async () => {
    localStorage.setItem("fiestaboard_current_board", "b-pixoo");
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole("tab", { name: "Flagship" }));

    await user.click(screen.getByRole("button", { name: /New page/i }));
    expect(push).toHaveBeenCalledWith("/pages/new?device=flagship");
  });
});
