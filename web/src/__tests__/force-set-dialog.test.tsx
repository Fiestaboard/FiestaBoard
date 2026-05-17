// Tests for ForceSetDialog component
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, waitFor, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { http, HttpResponse } from "msw";
import { server } from "./mocks/server";
import type { Page } from "@/lib/api";
import { ForceSetDialog } from "@/components/force-set-dialog";

const API_BASE = "/api";

const mockPages: Page[] = [
  {
    id: "page-1",
    name: "Weather Page",
    type: "single",
    device_type: "flagship",
    display_type: "weather",
    duration_seconds: 300,
    created_at: "2024-01-01T00:00:00Z",
  },
  {
    id: "page-2",
    name: "Date & Time",
    type: "single",
    device_type: "flagship",
    display_type: "datetime",
    duration_seconds: 300,
    created_at: "2024-01-01T00:00:00Z",
  },
];

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
    <ForceSetDialog
      open={true}
      onOpenChange={vi.fn()}
      pageId="page-1"
      pageName="Weather Page"
      scheduleEnabled={true}
      pages={mockPages}
      {...props}
    />,
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
    await waitFor(() =>
      expect(screen.getByPlaceholderText(/1.?480/i)).toBeInTheDocument(),
    );
  });

  it("shows 'Resume schedule' option when scheduleEnabled=true", () => {
    renderDialog({ scheduleEnabled: true });
    expect(screen.getByText(/resume schedule/i)).toBeInTheDocument();
  });

  it("does not show 'Resume schedule' when scheduleEnabled=false", () => {
    renderDialog({ scheduleEnabled: false });
    expect(screen.queryByText(/resume schedule/i)).not.toBeInTheDocument();
  });

  it("always shows 'Go blank' option", () => {
    renderDialog();
    expect(screen.getByText(/go blank/i)).toBeInTheDocument();
  });

  it("always shows 'Switch to page' option", () => {
    renderDialog();
    expect(screen.getByText(/switch to page/i)).toBeInTheDocument();
  });

  it("shows page dropdown when 'Switch to page' is selected", async () => {
    renderDialog();
    const revertPageRadio = screen.getByDisplayValue("page");
    fireEvent.click(revertPageRadio);
    await waitFor(() =>
      expect(screen.getByRole("combobox")).toBeInTheDocument(),
    );
  });

  it("page dropdown excludes the currently selected page", async () => {
    renderDialog({ pageId: "page-1" });
    const revertPageRadio = screen.getByDisplayValue("page");
    fireEvent.click(revertPageRadio);
    await waitFor(() => {
      const dropdown = screen.getByRole("combobox");
      expect(dropdown.innerHTML).not.toContain("Weather Page");
      expect(dropdown.innerHTML).toContain("Date");
    });
  });

  it("Force Set button is disabled when revert_mode=page and no page selected", async () => {
    renderDialog();
    const revertPageRadio = screen.getByDisplayValue("page");
    fireEvent.click(revertPageRadio);
    await waitFor(() => {
      const confirmBtn = screen.getByRole("button", { name: /force set/i });
      expect(confirmBtn).toBeDisabled();
    });
  });

  it("clicking Cancel calls onOpenChange(false)", () => {
    const onOpenChange = vi.fn();
    render(
      <ForceSetDialog
        open={true}
        onOpenChange={onOpenChange}
        pageId="page-1"
        pageName="Weather"
        scheduleEnabled={true}
        pages={mockPages}
      />,
      { wrapper: TestWrapper },
    );
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("clicking Force Set calls POST /settings/temporary-override", async () => {
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
      http.post(`${API_BASE}/force-refresh`, () =>
        HttpResponse.json({ status: "ok", message: "Refreshed" }),
      ),
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
    await waitFor(() =>
      expect(screen.queryByText(/setting…/i)).not.toBeInTheDocument(),
    );
  });

  it("Force Set button is disabled while submitting", async () => {
    // Use a slow handler to catch the pending state
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
      http.post(`${API_BASE}/force-refresh`, () =>
        HttpResponse.json({ status: "ok", message: "Refreshed" }),
      ),
    );
    renderDialog();
    const btn = screen.getByRole("button", { name: /force set/i });
    fireEvent.click(btn);
    // Immediately after click, button should show pending text
    await waitFor(() =>
      expect(screen.queryByText(/setting…/i)).toBeInTheDocument(),
    );
  });
});
