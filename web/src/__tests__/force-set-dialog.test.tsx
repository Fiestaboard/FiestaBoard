// Tests for ForceSetDialog component
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ForceSetDialog } from "@/components/force-set-dialog";
import { ThemeProvider } from "@/hooks/use-theme";

import { server } from "./mocks/server";

const API_BASE = "/api";

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider attribute="class" defaultTheme="light">
        {children}
      </ThemeProvider>
    </QueryClientProvider>
  );
}

function renderDialog(props: Partial<React.ComponentProps<typeof ForceSetDialog>> = {}) {
  return render(
    <ForceSetDialog open={true} onOpenChange={vi.fn()} pageId="page-1" pageName="Weather Page" {...props} />,
    { wrapper: TestWrapper },
  );
}

describe("ForceSetDialog", () => {
  afterEach(() => {
    server.resetHandlers();
  });

  it("renders with title", () => {
    renderDialog();
    expect(screen.getByText(/force set board/i)).toBeInTheDocument();
  });

  it("shows the page name in description", () => {
    renderDialog({ pageName: "Weather Page" });
    expect(screen.getByText(/weather page/i)).toBeInTheDocument();
  });

  it("shows all duration presets", () => {
    renderDialog();
    expect(screen.getByRole("button", { name: /^5 min$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^15 min$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^30 min$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^1 hr$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^custom$/i })).toBeInTheDocument();
  });

  it("5 min is selected by default", () => {
    renderDialog();
    const btn5 = screen.getByRole("button", { name: /^5 min$/i });
    expect(btn5.className).toContain("bg-primary");
  });

  it("shows custom input when Custom is selected", async () => {
    renderDialog();
    fireEvent.click(screen.getByRole("button", { name: /custom/i }));
    await waitFor(() => expect(screen.getByPlaceholderText(/1.?480/i)).toBeInTheDocument());
  });

  it("does not show revert mode options", () => {
    renderDialog();
    expect(screen.queryByText(/resume schedule/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/go blank/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/switch to page/i)).not.toBeInTheDocument();
  });

  it("clicking Cancel calls onOpenChange(false)", () => {
    const onOpenChange = vi.fn();
    render(<ForceSetDialog open={true} onOpenChange={onOpenChange} pageId="page-1" pageName="Weather" />, {
      wrapper: TestWrapper,
    });
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("clicking Force Set calls POST /settings/temporary-override with revert_mode=schedule", async () => {
    let capturedBody: unknown = null;
    server.use(
      http.post(`${API_BASE}/settings/temporary-override`, async ({ request }) => {
        capturedBody = await request.json();
        return HttpResponse.json({
          active: true,
          page_id: "page-1",
          expires_at: new Date(Date.now() + 300000).toISOString(),
          remaining_seconds: 299.5,
          revert_mode: "schedule",
          revert_page_id: null,
        });
      }),
      http.post(`${API_BASE}/force-refresh`, () => HttpResponse.json({ message: "Refreshed", sent: true })),
    );
    renderDialog();
    fireEvent.click(screen.getByRole("button", { name: /force set/i }));
    await waitFor(() => {
      expect(capturedBody).toMatchObject({
        page_id: "page-1",
        duration_minutes: 5,
        revert_mode: "schedule",
      });
    });
  });

  it("shows error toast on API failure", async () => {
    server.use(
      http.post(`${API_BASE}/settings/temporary-override`, () =>
        HttpResponse.json({ detail: "Page not found" }, { status: 404 }),
      ),
    );
    renderDialog();
    fireEvent.click(screen.getByRole("button", { name: /force set/i }));
    await waitFor(() => expect(screen.queryByText(/setting…/i)).not.toBeInTheDocument());
  });

  it("Force Set button is disabled while submitting", async () => {
    server.use(
      http.post(`${API_BASE}/settings/temporary-override`, async () => {
        await new Promise((r) => setTimeout(r, 200));
        return HttpResponse.json({
          active: true,
          page_id: "page-1",
          expires_at: new Date().toISOString(),
          remaining_seconds: 0,
          revert_mode: "schedule",
          revert_page_id: null,
        });
      }),
      http.post(`${API_BASE}/force-refresh`, () => HttpResponse.json({ message: "Refreshed", sent: true })),
    );
    renderDialog();
    const btn = screen.getByRole("button", { name: /force set/i });
    fireEvent.click(btn);
    await waitFor(() => expect(screen.queryByText(/setting…/i)).toBeInTheDocument());
  });
});

describe("ForceSetDialog during silence (#1943, #949)", () => {
  afterEach(() => {
    server.resetHandlers();
  });

  it("warns that it wakes the board and relabels the confirm button", () => {
    renderDialog({ silencedUntil: "7:00 AM" });
    const notice = screen.getByTestId("force-set-silence");
    expect(notice).toHaveTextContent("Silenced until 7:00 AM");
    expect(notice).toHaveTextContent("Force Set shows this page right away and wakes the board.");
    expect(screen.getByRole("button", { name: "Show now anyway" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^force set$/i })).not.toBeInTheDocument();
  });

  it("still warns when the end time is unknown", () => {
    renderDialog({ silenced: true, silencedUntil: null });
    expect(screen.getByTestId("force-set-silence")).toHaveTextContent("The board is silenced");
    expect(screen.getByRole("button", { name: "Show now anyway" })).toBeInTheDocument();
  });

  it("is exactly today's dialog when the board is not silenced", () => {
    renderDialog();
    expect(screen.queryByTestId("force-set-silence")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^force set$/i })).toBeInTheDocument();
  });

  it("confirming still posts the same temporary override", async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(`${API_BASE}/settings/temporary-override`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ active: true });
      }),
    );
    renderDialog({ silencedUntil: "7:00 AM" });
    fireEvent.click(screen.getByRole("button", { name: "Show now anyway" }));
    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toEqual({ page_id: "page-1", duration_minutes: 5, revert_mode: "schedule" });
  });
});

it("warns before setting an override on a paused board", () => {
  renderDialog({ silenced: true, paused: true });
  expect(screen.getByTestId("force-set-paused")).toHaveTextContent(
    "When paused, FiestaBoard does not push anything to this board",
  );
});

it("a paused refresh after Force Set does not claim the page was shown", async () => {
  server.use(http.post(`${API_BASE}/force-refresh`, () => HttpResponse.json({ sent: false })));
  const info = vi.spyOn((await import("sonner")).toast, "info");
  renderDialog({ silenced: true });
  fireEvent.click(screen.getByRole("button", { name: "Show now anyway" }));
  await waitFor(() => expect(info).toHaveBeenCalledWith("Nothing was sent (board paused or output set to UI only)"));
});
