import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

import { server } from "./mocks/server";

const API_BASE = "/api";
import { PageBuilder } from "@/components/page-builder";

vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
  }),
}));

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

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

describe("PageBuilder — Sync from Board", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows the Sync from Board button when creating a new page", async () => {
    render(<PageBuilder onClose={vi.fn()} />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Sync from current board display" })).toBeInTheDocument();
    });
  });

  it("does not show the Sync from Board button when editing an existing page", async () => {
    render(<PageBuilder pageId="page-1" onClose={vi.fn()} />, {
      wrapper: TestWrapper,
    });

    // Wait for the page data to load
    await waitFor(() => {
      expect(screen.queryByText("Syncing...")).not.toBeInTheDocument();
    });

    // The button must not be present in edit mode
    expect(screen.queryByRole("button", { name: "Sync from current board display" })).not.toBeInTheDocument();
  });

  it("populates template lines and shows a success toast on successful sync", async () => {
    const toastSpy = vi.spyOn((await import("sonner")).toast, "success");
    const user = userEvent.setup();

    render(<PageBuilder onClose={vi.fn()} />, { wrapper: TestWrapper });

    const syncBtn = await screen.findByRole("button", {
      name: "Sync from current board display",
    });
    await user.click(syncBtn);

    await waitFor(() => {
      expect(toastSpy).toHaveBeenCalledWith(expect.stringContaining("Weather Page"));
    });
  });

  it("shows an error toast when the sync API call fails", async () => {
    const toastSpy = vi.spyOn((await import("sonner")).toast, "error");
    const user = userEvent.setup();

    server.use(
      http.get(`${API_BASE}/pages/current-display`, () => {
        return HttpResponse.json({ detail: "No active page set" }, { status: 404 });
      }),
    );

    render(<PageBuilder onClose={vi.fn()} />, { wrapper: TestWrapper });

    const syncBtn = await screen.findByRole("button", {
      name: "Sync from current board display",
    });
    await user.click(syncBtn);

    await waitFor(() => {
      expect(toastSpy).toHaveBeenCalled();
    });
  });
});

describe("PageBuilder — note-array dimensions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // A 4×1 note array → 4*15 = 60 cols × 1*3 = 3 rows. The BoardSizeIndicator
  // renders width × height (cols × rows), so a real note-array preview shows
  // "60 × 3". A 1×1 (flagship/note default) note array would only ever show
  // "15 × 3", so asserting "60 × 3" proves the real dims were threaded through.
  function configureNoteArrayBoard(notesWide: number, notesTall: number) {
    server.use(
      http.get(`${API_BASE}/settings/board`, () => {
        return HttpResponse.json({
          board_type: "black",
          boards: [
            {
              id: "na-1",
              name: "Note Array",
              device_type: "note_array",
              board_color: "black",
              notes_wide: notesWide,
              notes_tall: notesTall,
            },
          ],
          devices: ["note_array"],
        });
      }),
    );
  }

  it("previews a NEW note_array page at the configured board's real size", async () => {
    // Configured note array is 4 wide × 1 tall → 60 × 3.
    configureNoteArrayBoard(4, 1);

    render(<PageBuilder deviceType="note_array" onClose={vi.fn()} />, { wrapper: TestWrapper });

    // The size indicator reflects the seeded grid dims (cols × rows), not 1×1.
    await waitFor(() => {
      expect(screen.getByRole("img", { name: /3 rows by 60 columns/i })).toBeInTheDocument();
    });
    const indicator = screen.getByRole("img", { name: /3 rows by 60 columns/i });
    expect(indicator).toHaveTextContent("60 × 3");
  });

  it("seeds dims from an EDITED note_array page", async () => {
    // Editing a 2×2 note array page (persisted notes_wide/notes_tall) →
    // 2*15 = 30 cols × 2*3 = 6 rows → "30 × 6".
    server.use(
      http.get(`${API_BASE}/pages/:id`, () => {
        return HttpResponse.json({
          id: "na-page",
          name: "My Note Array Page",
          type: "template",
          device_type: "note_array",
          template: ["", "", "", "", "", ""],
          notes_wide: 2,
          notes_tall: 2,
          duration_seconds: 300,
          created_at: "2024-01-01T00:00:00Z",
        });
      }),
    );

    render(<PageBuilder pageId="na-page" onClose={vi.fn()} />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("img", { name: /6 rows by 30 columns/i })).toBeInTheDocument();
    });
    const indicator = screen.getByRole("img", { name: /6 rows by 30 columns/i });
    expect(indicator).toHaveTextContent("30 × 6");
  });

  it("leaves a flagship page at its fixed 22 × 6 size", async () => {
    render(<PageBuilder deviceType="flagship" onClose={vi.fn()} />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("img", { name: /6 rows by 22 columns/i })).toBeInTheDocument();
    });
    const indicator = screen.getByRole("img", { name: /6 rows by 22 columns/i });
    expect(indicator).toHaveTextContent("22 × 6");
  });
});
