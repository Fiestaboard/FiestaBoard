/**
 * Regression test for issue #943: when a user has only one device type
 * configured (e.g. note) but plugin-created demo pages exist for the other
 * device type (flagship), the Pages page should surface both device tabs
 * so the orphan pages can be edited or deleted.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PagesPage from "../../app/routes/pages._index";
import { server } from "./mocks/server";

const API_BASE = "/api";

vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
  }),
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), loading: vi.fn() },
  Toaster: () => null,
}));

vi.mock("@/components/smart-link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a>,
}));

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <PagesPage />
    </QueryClientProvider>,
  );
}

function mockBoardSettings(devices: ("flagship" | "note")[]) {
  server.use(
    http.get(`${API_BASE}/settings/board`, () =>
      HttpResponse.json({
        board_type: "black",
        boards: devices.map((d, i) => ({ id: `b-${i}`, name: d, device_type: d, board_color: "black" })),
        devices,
      }),
    ),
  );
}

function mockPages(pages: { id: string; name: string; device_type: "flagship" | "note" }[]) {
  server.use(
    http.get(`${API_BASE}/pages`, () =>
      HttpResponse.json({
        pages: pages.map((p) => ({
          ...p,
          type: "template",
          template: [""],
          duration_seconds: 300,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        })),
      }),
    ),
  );
  // Page previews batch is called when grid renders; respond with empty so
  // the component finishes loading.
  server.use(http.post(`${API_BASE}/pages/preview-batch`, () => HttpResponse.json({ previews: {} })));
  // Collections — empty.
  server.use(http.get(`${API_BASE}/collections`, () => HttpResponse.json({ collections: [] })));
}

describe("PagesPage device-type tabs", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("hides tabs when only one device type is configured AND only that device's pages exist", async () => {
    mockBoardSettings(["note"]);
    mockPages([{ id: "p1", name: "Note Only", device_type: "note" }]);

    renderPage();

    await waitFor(() => expect(screen.getByText("Note Only")).toBeInTheDocument());
    expect(screen.queryByRole("tab", { name: "Flagship" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Note" })).not.toBeInTheDocument();
  });

  it("shows both tabs when an orphan flagship page exists on a note-only setup", async () => {
    mockBoardSettings(["note"]);
    mockPages([
      { id: "p1", name: "Note Page", device_type: "note" },
      { id: "p2", name: "Orphan Flagship Demo", device_type: "flagship" },
    ]);

    renderPage();

    await waitFor(() => {
      expect(screen.getByRole("tab", { name: "Flagship" })).toBeInTheDocument();
      expect(screen.getByRole("tab", { name: "Note" })).toBeInTheDocument();
    });
  });

  it("defaults to the user's configured device tab even when an orphan tab exists", async () => {
    mockBoardSettings(["note"]);
    mockPages([
      { id: "p1", name: "My Note", device_type: "note" },
      { id: "p2", name: "Orphan Flagship", device_type: "flagship" },
    ]);

    renderPage();

    await waitFor(() => {
      const noteTab = screen.getByRole("tab", { name: "Note" });
      expect(noteTab.getAttribute("aria-selected")).toBe("true");
    });
  });

  it("clicking the orphan flagship tab reveals the orphan page", async () => {
    const user = userEvent.setup();
    mockBoardSettings(["note"]);
    mockPages([
      { id: "p1", name: "My Note", device_type: "note" },
      { id: "p2", name: "Orphan Flagship Demo", device_type: "flagship" },
    ]);

    renderPage();

    await waitFor(() => expect(screen.getByRole("tab", { name: "Flagship" })).toBeInTheDocument());
    await user.click(screen.getByRole("tab", { name: "Flagship" }));
    await waitFor(() => expect(screen.getByText("Orphan Flagship Demo")).toBeInTheDocument());
  });
});
