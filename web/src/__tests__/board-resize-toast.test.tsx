/**
 * Saving a board that resizes it in place (an LED board's text size: a Pixoo
 * is 10x16 in the small face and 8x10 in the large one) moves the pages sized
 * for its old grid with it, and leaves warn-only references to pages that
 * still do not fit. `PUT /settings/board` reports both; the settings screen
 * says so in a toast, as the FiestaPanel screen does after a TV-size re-fit.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { toast } from "sonner";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useDisplayBoards } from "@/components/settings/display-settings";

import { server } from "./mocks/server";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}));

const API_BASE = "/api";

const PIXOO = {
  id: "pixoo-1",
  name: "Kitchen sign",
  output: "divoom_pixoo",
  device_model: "divoom_pixoo64",
  device_type: "panel",
  grid_rows: 10,
  grid_cols: 16,
  board_color: "black",
  enabled: true,
  output_config: { host: "192.0.2.50", font: "3x5" },
};

const put = { count: 0 };

function respondWith(extra: Record<string, unknown>) {
  put.count = 0;
  server.use(
    http.get(`${API_BASE}/settings/board`, () =>
      HttpResponse.json({ board_type: "black", boards: [PIXOO], devices: ["panel"] }),
    ),
    http.put(`${API_BASE}/settings/board`, () => {
      put.count += 1;
      return HttpResponse.json({ board_type: "black", boards: [PIXOO], devices: ["panel"], ...extra });
    }),
  );
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

async function saveTextSize() {
  const { result } = renderHook(() => useDisplayBoards(), { wrapper });
  await waitFor(() => expect(result.current.boards).toHaveLength(1));
  act(() => {
    result.current.updateBoard("pixoo-1", { output_config: { host: "192.0.2.50", font: "5x7" } });
  });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("saving a board that resizes it", () => {
  it("says which pages moved to the board's new size", async () => {
    respondWith({
      retargeted_pages: [
        { page_id: "p1", page_name: "Weather", from_size: "panel:10x16", to_size: "panel:8x10" },
        { page_id: "p2", page_name: "Transit", from_size: "panel:10x16", to_size: "panel:8x10" },
      ],
      incompatible_references: [],
    });
    await saveTextSize();
    await waitFor(() =>
      expect(toast.info).toHaveBeenCalledWith(
        "Pages moved to the board's new size: Weather, Transit.",
        expect.anything(),
      ),
    );
    expect(toast.warning).not.toHaveBeenCalled();
  });

  it("warns about pages that no longer fit, once each", async () => {
    respondWith({
      retargeted_pages: [],
      incompatible_references: [
        {
          board_id: "pixoo-1",
          board_name: "Kitchen sign",
          page_id: "p1",
          page_name: "Weather",
          surface: "active_page",
          schedule_id: null,
        },
        {
          board_id: "pixoo-1",
          board_name: "Kitchen sign",
          page_id: "p1",
          page_name: "Weather",
          surface: "schedule",
          schedule_id: "s1",
        },
      ],
    });
    await saveTextSize();
    await waitFor(() =>
      expect(toast.warning).toHaveBeenCalledWith(
        "The board's new size no longer fits these pages: Weather. Edit them or they won't display on this board.",
        expect.anything(),
      ),
    );
    expect(toast.info).not.toHaveBeenCalled();
  });

  it("says nothing when the save resized nothing", async () => {
    respondWith({ retargeted_pages: [], incompatible_references: [] });
    await saveTextSize();
    await waitFor(() => expect(put.count).toBe(1));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(toast.error).not.toHaveBeenCalled();
    expect(toast.info).not.toHaveBeenCalled();
    expect(toast.warning).not.toHaveBeenCalled();
  });
});
