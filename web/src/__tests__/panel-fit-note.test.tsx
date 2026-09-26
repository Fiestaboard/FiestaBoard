/**
 * The quiet "what does this page fit" line.
 *
 * A FiestaPanel is a board like any other, so the app should say which panel a
 * page was sized for. There is no provenance stored on the page — the match is
 * purely the grid — so this line is the only thing that connects the two.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { PanelFitNote } from "@/components/panel-fit-note";

import { server } from "./mocks/server";

const API_BASE = "/api";

function panel(id: string, name: string, notesWide: number, notesTall: number) {
  return {
    id,
    short_code: 1,
    name,
    board_id: `board-${id}`,
    screen_diagonal_inches: 55,
    calibration_scale: 1,
    animations_enabled: false,
    is_display: false,
    backdrop: "wall",
    auto_dim: { enabled: false, start: "22:00", end: "07:00" },
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    device_type: "note_array",
    board_missing: false,
    rows: notesTall * 3,
    cols: notesWide * 15,
    notes_wide: notesWide,
    notes_tall: notesTall,
  };
}

function servePanels(...panels: ReturnType<typeof panel>[]) {
  server.use(http.get(`${API_BASE}/panels`, () => HttpResponse.json({ panels, total: panels.length })));
}

function Wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe("PanelFitNote", () => {
  it("names the panel a page's grid matches", async () => {
    servePanels(panel("p1", "Kitchen TV", 2, 4));
    render(<PanelFitNote deviceType="note_array" notesWide={2} notesTall={4} />, { wrapper: Wrapper });
    expect(await screen.findByText("Fits Kitchen TV")).toBeInTheDocument();
  });

  it("renders nothing when no panel has that grid", async () => {
    servePanels(panel("p1", "Kitchen TV", 2, 4));
    const { container } = render(<PanelFitNote deviceType="note_array" notesWide={3} notesTall={1} />, {
      wrapper: Wrapper,
    });
    // Wait for the panel list to have arrived, so this is a real "no match"
    // and not just an assertion made before the fetch resolved.
    await waitFor(() => expect(screen.queryByText(/Fits/)).not.toBeInTheDocument());
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing for a flagship page", async () => {
    servePanels(panel("p1", "Kitchen TV", 2, 4));
    const { container } = render(<PanelFitNote deviceType="flagship" />, { wrapper: Wrapper });
    await waitFor(() => expect(screen.queryByText(/Fits/)).not.toBeInTheDocument());
    expect(container).toBeEmptyDOMElement();
  });

  it("names the first panel and counts the rest when several are the same shape", async () => {
    servePanels(panel("p1", "Kitchen TV", 2, 4), panel("p2", "Hallway TV", 2, 4), panel("p3", "Office TV", 2, 4));
    render(<PanelFitNote deviceType="note_array" notesWide={2} notesTall={4} />, { wrapper: Wrapper });
    expect(await screen.findByText("Fits Kitchen TV +2 more")).toBeInTheDocument();
  });

  it("renders nothing on an install with no panels", async () => {
    servePanels();
    const { container } = render(<PanelFitNote deviceType="note_array" notesWide={2} notesTall={4} />, {
      wrapper: Wrapper,
    });
    await waitFor(() => expect(screen.queryByText(/Fits/)).not.toBeInTheDocument());
    expect(container).toBeEmptyDOMElement();
  });
});
