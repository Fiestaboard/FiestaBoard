// Tests for ForceSetDialog component
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { ThemeProvider } from "@/hooks/use-theme";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ForceSetDialog } from "@/components/force-set-dialog";

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
      http.post(`${API_BASE}/force-refresh`, () => HttpResponse.json({ status: "ok", message: "Refreshed" })),
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
      http.post(`${API_BASE}/force-refresh`, () => HttpResponse.json({ status: "ok", message: "Refreshed" })),
    );
    renderDialog();
    const btn = screen.getByRole("button", { name: /force set/i });
    fireEvent.click(btn);
    await waitFor(() => expect(screen.queryByText(/setting…/i)).toBeInTheDocument());
  });
});
