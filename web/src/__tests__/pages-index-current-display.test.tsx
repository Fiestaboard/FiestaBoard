/** The library filters by real configured displays, retaining every orphan shape in All pages. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CurrentBoardProvider } from "@/components/current-board-context";

import PagesPage from "../../app/routes/pages._index";
import { server } from "./mocks/server";

const push = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/use-router", () => ({ useRouter: () => ({ push, replace: vi.fn(), back: vi.fn() }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));
vi.mock("@/components/smart-link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a>,
}));
const BOARDS = [
  { id: "hall", name: "Hall", device_type: "flagship", board_color: "black" },
  {
    id: "led",
    name: "Pixoo",
    device_type: "panel",
    board_color: "black",
    grid_rows: 10,
    grid_cols: 16,
    output: "divoom_pixoo",
    device_model: "divoom_pixoo64",
    charset: "led_3x5",
  },
  { id: "tv", name: "Lobby TV", device_type: "panel", board_color: "black", grid_rows: 12, grid_cols: 29 },
];
function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <CurrentBoardProvider>
        <PagesPage />
      </CurrentBoardProvider>
    </QueryClientProvider>,
  );
}
describe("Pages library display filter", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    sessionStorage.clear();
    server.use(
      http.get("/api/settings/board", () =>
        HttpResponse.json({ board_type: "black", boards: BOARDS, devices: ["flagship", "panel"] }),
      ),
      http.get("/api/v1/pages", () =>
        HttpResponse.json({
          pages: [
            { id: "hall-page", name: "Hall Page", device_type: "flagship" },
            { id: "led-page", name: "Pixoo Page", device_type: "panel", grid_rows: 10, grid_cols: 16 },
            { id: "tv-page", name: "TV Page", device_type: "panel", grid_rows: 12, grid_cols: 29 },
            { id: "orphan", name: "Orphan Page", device_type: "panel", grid_rows: 8, grid_cols: 30 },
          ].map((p) => ({
            ...p,
            type: "template",
            template: [""],
            created_at: "2026-01-01",
            updated_at: "2026-01-01",
          })),
        }),
      ),
      http.post("/api/pages/preview/batch", () => HttpResponse.json({ previews: {} })),
      http.get("/api/v1/collections", () => HttpResponse.json({ collections: [] })),
      http.get("/api/panels", () => HttpResponse.json({ panels: [], total: 0 })),
    );
  });
  it("opens All pages with orphan geometry reachable even when an LED display is selected", async () => {
    localStorage.setItem("fiestaboard_current_board", "led");
    renderPage();
    expect(await screen.findByText("Orphan Page")).toBeInTheDocument();
    expect(await screen.findByText("Hall Page")).toBeInTheDocument();
    expect(screen.getByLabelText("Display filter")).toHaveTextContent("All pages");
  });
  it("fits an LED display by exact geometry, flagging the rest after the page that fits", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByLabelText("Display filter"));
    await user.click(await screen.findByRole("option", { name: "Pixoo" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /TV Page/ })).toHaveAccessibleDescription(/Made for a 12×29 board/),
    );
    expect(screen.getByRole("button", { name: /Pixoo Page/ })).not.toHaveAttribute("aria-describedby");
    expect(screen.getByRole("button", { name: /Orphan Page/ })).toHaveAccessibleDescription(/Made for a 8×30 board/);
    expect(screen.getByRole("button", { name: /Hall Page/ })).toHaveAccessibleDescription(/Made for a 6×22 board/);
    const names = within(screen.getByRole("group", { name: "Pages" }))
      .getAllByRole("button")
      .map((button) =>
        ["Hall Page", "Pixoo Page", "TV Page", "Orphan Page"].find((n) => button.textContent?.includes(n)),
      );
    expect(names).toEqual(["Pixoo Page", "Hall Page", "TV Page", "Orphan Page"]);
    expect(screen.getByText("1 page")).toBeInTheDocument();
  });
  it("restores the chosen display filter after returning from an editor", async () => {
    const user = userEvent.setup();
    const rendered = renderPage();
    await user.click(screen.getByLabelText("Display filter"));
    await user.click(await screen.findByRole("option", { name: "Lobby TV" }));
    rendered.unmount();
    renderPage();
    expect(await screen.findByText("TV Page")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Pixoo Page/ })).toHaveAccessibleDescription(/Made for a 10×16 board/),
    );
  });
});
