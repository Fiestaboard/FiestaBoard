/** All pages replaces the fixed family tabs: every orphan device/shape stays reachable. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PagesPage from "../../app/routes/pages._index";
import { server } from "./mocks/server";
vi.mock("@/hooks/use-router", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PagesPage />
    </QueryClientProvider>,
  );
}
describe("Pages library orphan reachability", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
  it.each([
    { device_type: "flagship" },
    { device_type: "note_array", notes_wide: 3, notes_tall: 2 },
    { device_type: "panel", grid_rows: 12, grid_cols: 29 },
    { device_type: "panel", grid_rows: 8, grid_cols: 10 },
  ])("shows an unconfigured $device_type page in All pages", async (shape) => {
    server.use(
      http.get("/api/settings/board", () =>
        HttpResponse.json({
          board_type: "black",
          devices: ["note"],
          boards: [{ id: "note", name: "Desk", device_type: "note", board_color: "black" }],
        }),
      ),
      http.get("/api/v1/pages", () =>
        HttpResponse.json({
          pages: [
            { id: "my-note", name: "My Note", device_type: "note" },
            { id: "orphan", name: "Orphan", ...shape },
          ].map((page) => ({
            ...page,
            type: "template",
            template: [""],
            created_at: "2026-01-01",
            updated_at: "2026-01-01",
          })),
        }),
      ),
      http.post("/api/pages/preview/batch", () => HttpResponse.json({ previews: {} })),
      http.get("/api/v1/collections", () => HttpResponse.json({ collections: [] })),
    );
    renderPage();
    expect(await screen.findByText("My Note")).toBeInTheDocument();
    expect(await screen.findByText("Orphan")).toBeInTheDocument();
    expect(screen.getByLabelText("Display filter")).toHaveTextContent("All pages");
    expect(screen.queryByRole("tab")).not.toBeInTheDocument();
  });
});
