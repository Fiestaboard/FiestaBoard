import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

import { server } from "./mocks/server";

const API_BASE = "/api";
import { ActivePageDisplay } from "@/components/active-page-display";

vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
  }),
}));

vi.mock("@/components/smart-link", () => ({
  default: ({ children, href, ...rest }: { children: React.ReactNode; href: string }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
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

describe("ActivePageDisplay", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading state when preview is loading", async () => {
    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByTestId("now-showing")).toBeInTheDocument();
    });
  });

  it("displays active page info in manual mode", async () => {
    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Weather Page")).toBeInTheDocument();
      expect(screen.getByText("Manual Mode")).toBeInTheDocument();
    });
  });

  it("offers Edit page for the saved page on the display", async () => {
    // Issue #1473: when a Page generates the current display, Home links
    // straight to that page's editor (07a: "Edit page" in the action row).
    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    expect(await screen.findByRole("heading", { level: 2, name: "Weather Page" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Edit page" })).toHaveAttribute("href", "/pages/edit/page-1");
  });

  it("does not render a page edit link when a collection is active", async () => {
    // Collections aren't a single editable page, so no editor link.
    server.use(
      http.get(`${API_BASE}/settings/active-page`, () =>
        HttpResponse.json({ page_id: "collection:test-collection-id" }),
      ),
      http.get(`${API_BASE}/v1/collections`, () =>
        HttpResponse.json({
          collections: [
            {
              id: "collection:test-collection-id",
              name: "Test Collection",
              page_ids: ["page-1"],
              selection_mode: "time",
              time: { interval_seconds: 30 },
              variable: null,
              random: null,
              created_at: "2025-01-01T00:00:00Z",
            },
          ],
          total: 1,
        }),
      ),
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    expect(await screen.findByRole("heading", { level: 2, name: "Test Collection" })).toBeInTheDocument();

    // No member page is named, so there is no page to edit.
    expect(screen.queryByRole("link", { name: /^Edit page/i })).not.toBeInTheDocument();
  });

  it("links the collection name and the page it is currently rendering when a collection is active", async () => {
    // Issue #1513: a Collection decides which member page shows on the board.
    // The Dashboard must link the collection (to edit its logic) AND the member
    // page the collection is currently rendering (to edit that design).
    server.use(
      http.get(`${API_BASE}/settings/active-page`, () =>
        HttpResponse.json({ page_id: "collection:test-collection-id", resolved_page_id: "page-1" }),
      ),
      http.get(`${API_BASE}/v1/collections`, () =>
        HttpResponse.json({
          collections: [
            {
              id: "collection:test-collection-id",
              name: "Test Collection",
              page_ids: ["page-1"],
              selection_mode: "time",
              time: { interval_seconds: 30 },
              variable: null,
              random: null,
              created_at: "2025-01-01T00:00:00Z",
            },
          ],
          total: 1,
        }),
      ),
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    expect(await screen.findByRole("heading", { level: 2, name: "Test Collection" })).toBeInTheDocument();

    // The collection links to the collections editor.
    const collectionLink = screen.getByRole("link", { name: /Edit collection "Test Collection"/i });
    expect(collectionLink).toHaveAttribute("href", "/collections/collection%3Atest-collection-id");

    // The member page the collection is currently rendering links to its editor.
    const pageLink = screen.getByRole("link", { name: /Edit page "Weather Page"/i });
    expect(pageLink).toHaveAttribute("href", "/pages/edit/page-1");
  });

  it("links to the scheduled page's editor when a schedule drives the display", async () => {
    // Issue #1473 calls out complex schedules as the case where it's hardest to
    // tell which saved page is on the board, so the link must follow the
    // schedule's page — not whatever the manual active-page setting still says.
    server.use(
      http.get(`${API_BASE}/schedules/active/page`, () =>
        HttpResponse.json({
          page_id: "page-2",
          source: "schedule",
          schedule_enabled: true,
          current_time: "09:00",
          current_day: "monday",
        }),
      ),
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    expect(await screen.findByRole("heading", { level: 2, name: "Custom Template" })).toBeInTheDocument();
    // The manual active page (page-1) is stale in schedule mode; it must not leak through.
    expect(screen.queryByRole("heading", { level: 2, name: "Weather Page" })).not.toBeInTheDocument();

    // 07a's Schedule Mode row offers View Schedule; Edit page is in the board menu.
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^Actions for / }));
    expect(await screen.findByRole("menuitem", { name: /Edit page/ })).toHaveAttribute("href", "/pages/edit/page-2");
  });

  it("does not render a page edit link during a schedule gap", async () => {
    // No page is scheduled for the current time, so there is nothing to edit.
    server.use(
      http.get(`${API_BASE}/schedules/active/page`, () =>
        HttpResponse.json({
          page_id: null,
          source: "schedule",
          schedule_enabled: true,
        }),
      ),
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Schedule gap (no default page set)")).toBeInTheDocument();
    });

    expect(screen.queryByRole("link", { name: /Edit page/i })).not.toBeInTheDocument();
  });

  it("shows Change Page button in manual mode", async () => {
    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      const changeBtn = screen.getByRole("button", { name: /^Change Page$/ });
      expect(changeBtn).toBeInTheDocument();
    });
  });

  it("opens the Change Page dialog when Change Page is clicked in manual mode", async () => {
    const user = userEvent.setup();
    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /^Change Page$/ })).toBeInTheDocument();
    });

    const changeBtn = screen.getByRole("button", { name: /^Change Page$/ });
    await user.click(changeBtn);

    expect(await screen.findByRole("dialog", { name: "Change Page" })).toBeInTheDocument();
  });

  it("shows schedule gap warning when schedule enabled and no active page", async () => {
    server.use(
      http.get(`${API_BASE}/schedules/active/page`, () =>
        HttpResponse.json({
          page_id: null,
          source: "schedule",
          schedule_enabled: true,
        }),
      ),
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Schedule gap (no default page set)")).toBeInTheDocument();
      expect(screen.getByText(/No page scheduled for current time/i)).toBeInTheDocument();
    });
  });

  it("renders View Schedule as a link (not a button) when schedule is enabled", async () => {
    // Regression: navigation actions must be <a href> so screen reader users
    // hear "link" (navigation) rather than "button" (in-page action).
    // See issue #1197 / WCAG 2.4.4.
    server.use(
      http.get(`${API_BASE}/schedules/active/page`, () =>
        HttpResponse.json({
          page_id: null,
          source: "none",
          schedule_enabled: true,
        }),
      ),
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("link", { name: /View Schedule/i })).toBeInTheDocument();
    });

    const viewScheduleLink = screen.getByRole("link", { name: /View Schedule/i });
    expect(viewScheduleLink).toHaveAttribute("href", "/schedule");
    // It must NOT be exposed to assistive tech as a button.
    expect(screen.queryByRole("button", { name: /View Schedule/i })).not.toBeInTheDocument();
  });

  it("renders schedule gap link as a link (not a button)", async () => {
    // Regression: the "Schedule settings" affordance inside the schedule-gap
    // warning navigates to /schedule, so it must be an anchor too. See #1197.
    server.use(
      http.get(`${API_BASE}/schedules/active/page`, () =>
        HttpResponse.json({
          page_id: null,
          source: "schedule",
          schedule_enabled: true,
        }),
      ),
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("link", { name: /Schedule settings/i })).toBeInTheDocument();
    });

    expect(screen.getByRole("link", { name: /Schedule settings/i })).toHaveAttribute("href", "/schedule");
    expect(screen.queryByRole("button", { name: /Schedule settings/i })).not.toBeInTheDocument();
  });

  it("derives schedule mode from active schedule endpoint without fetching full schedule list", async () => {
    // This test verifies the fix: schedule_enabled is derived from the
    // /schedules/active/page endpoint (lightweight) instead of /schedules
    // (heavyweight, returns all schedule entries).
    server.use(
      http.get(`${API_BASE}/schedules/active/page`, () =>
        HttpResponse.json({
          page_id: "page-1",
          source: "schedule",
          schedule_enabled: true,
          current_time: "09:00",
          current_day: "monday",
        }),
      ),
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("link", { name: /View Schedule/i })).toBeInTheDocument();
    });
  });

  it("shows silence mode indicator when silence is active", async () => {
    server.use(
      http.get(`${API_BASE}/silence-status`, () =>
        HttpResponse.json({
          enabled: true,
          active: true,
          start_time_utc: "04:00+00:00",
          end_time_utc: "15:00+00:00",
          current_time_utc: "2025-12-26T18:30:00+00:00",
          next_change_utc: "2025-12-27T04:00:00+00:00",
        }),
      ),
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Silence mode active")).toBeInTheDocument();
    });
  });

  it("shows Collection badge when active page is a collection", async () => {
    server.use(
      http.get(`${API_BASE}/settings/active-page`, () =>
        HttpResponse.json({ page_id: "collection:test-collection-id" }),
      ),
      http.get(`${API_BASE}/v1/collections`, () =>
        HttpResponse.json({
          collections: [
            {
              id: "collection:test-collection-id",
              name: "Test Collection",
              page_ids: ["page-1"],
              selection_mode: "time",

              time: { interval_seconds: 30 },

              variable: null,
              random: null,
              created_at: "2025-01-01T00:00:00Z",
            },
          ],
          total: 1,
        }),
      ),
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    expect(await screen.findByRole("heading", { level: 2, name: "Test Collection" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: 'Edit collection "Test Collection"' })).toHaveTextContent("Collection");
  });

  it("shows out-of-sync alert when board was changed externally", async () => {
    const differentChars = Array.from({ length: 6 }, () => Array(22).fill(1));
    const expectedChars = Array.from({ length: 6 }, () => Array(22).fill(2));
    server.use(
      http.get(`${API_BASE}/board/current-message`, () =>
        HttpResponse.json({
          characters: differentChars,
          message: "",
          rows: 6,
          cols: 22,
          expected_characters: expectedChars,
          cached_at: null,
          api_mode: "local",
        }),
      ),
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Another app changed this board")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /Restore/i })).toBeInTheDocument();
    });
  });

  it("restores the primary board and shows a success toast when Restore is clicked", async () => {
    const toastSpy = vi.spyOn((await import("sonner")).toast, "success");
    const differentChars = Array.from({ length: 6 }, () => Array(22).fill(1));
    const expectedChars = Array.from({ length: 6 }, () => Array(22).fill(2));
    server.use(
      http.get(`${API_BASE}/board/current-message`, () =>
        HttpResponse.json({
          characters: differentChars,
          message: "",
          rows: 6,
          cols: 22,
          expected_characters: expectedChars,
          cached_at: null,
          api_mode: "local",
        }),
      ),
      http.post(`${API_BASE}/v1/boards/primary/restore`, () =>
        HttpResponse.json({ board_id: "b1", page_id: null, sent: true, reason: null, device_observed: false }),
      ),
    );

    const user = userEvent.setup();
    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Restore/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /Restore/i }));

    await waitFor(() => {
      expect(toastSpy).toHaveBeenCalledWith("Board restored");
    });

    toastSpy.mockRestore();
  });

  it("does not hide the banner or claim success when restore reports sent=false", async () => {
    const successSpy = vi.spyOn((await import("sonner")).toast, "success");
    const warningSpy = vi.spyOn((await import("sonner")).toast, "warning");
    server.use(
      http.get(`${API_BASE}/board/current-message`, () =>
        HttpResponse.json({
          characters: Array.from({ length: 6 }, () => Array(22).fill(1)),
          message: "",
          rows: 6,
          cols: 22,
          expected_characters: Array.from({ length: 6 }, () => Array(22).fill(2)),
          cached_at: null,
          api_mode: "local",
        }),
      ),
      http.post(`${API_BASE}/v1/boards/primary/restore`, () =>
        HttpResponse.json({ board_id: "b1", page_id: null, sent: false, reason: "x", device_observed: false }),
      ),
    );

    const user = userEvent.setup();
    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await user.click(await screen.findByRole("button", { name: /Restore/i }));

    await waitFor(() => {
      expect(warningSpy).toHaveBeenCalledWith("Nothing was sent to the display");
    });
    expect(successSpy).not.toHaveBeenCalledWith("Board restored");
    expect(screen.getByText("Another app changed this board")).toBeInTheDocument();

    successSpy.mockRestore();
    warningSpy.mockRestore();
  });

  it("saves the externally set board content as a new template page", async () => {
    const toastSpy = vi.spyOn((await import("sonner")).toast, "success");
    // Row 0 reads "HI" followed by a red tile; the rest is blank.
    const externalChars = Array.from({ length: 6 }, () => Array(22).fill(0));
    externalChars[0][0] = 8;
    externalChars[0][1] = 9;
    externalChars[0][2] = 63;
    const expectedChars = Array.from({ length: 6 }, () => Array(22).fill(2));
    let createdBody: Record<string, unknown> | null = null;
    server.use(
      http.get(`${API_BASE}/board/current-message`, () =>
        HttpResponse.json({
          characters: externalChars,
          message: "",
          rows: 6,
          cols: 22,
          expected_characters: expectedChars,
          cached_at: null,
          api_mode: "local",
        }),
      ),
      http.post(`${API_BASE}/v1/pages`, async ({ request }) => {
        createdBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: "new-page", ...createdBody }, { status: 201 });
      }),
    );

    const user = userEvent.setup();
    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    const saveButton = await screen.findByRole("button", { name: /Save as page/i });
    await user.click(saveButton);

    await waitFor(() => {
      expect(createdBody).not.toBeNull();
    });
    expect(createdBody).toMatchObject({
      type: "template",
      template: ["HI{{red}}", "", "", "", "", ""],
    });
    expect(String(createdBody!.name)).toMatch(/^From board /);
    await waitFor(() => {
      expect(toastSpy).toHaveBeenCalledWith(expect.stringMatching(/^Saved “From board .*” as a page$/), {
        action: expect.objectContaining({ label: "Open" }),
      });
    });

    toastSpy.mockRestore();
  });

  it("shows an error toast when saving the external board content fails", async () => {
    const toastSpy = vi.spyOn((await import("sonner")).toast, "error");
    server.use(
      http.get(`${API_BASE}/board/current-message`, () =>
        HttpResponse.json({
          characters: Array.from({ length: 6 }, () => Array(22).fill(1)),
          message: "",
          rows: 6,
          cols: 22,
          expected_characters: Array.from({ length: 6 }, () => Array(22).fill(2)),
          cached_at: null,
          api_mode: "local",
        }),
      ),
      http.post(`${API_BASE}/v1/pages`, () => HttpResponse.json({ detail: "nope" }, { status: 500 })),
    );

    const user = userEvent.setup();
    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await user.click(await screen.findByRole("button", { name: /Save as page/i }));

    await waitFor(() => {
      expect(toastSpy).toHaveBeenCalledWith("Failed to save board as a page");
    });

    toastSpy.mockRestore();
  });

  it("handles set active page error", async () => {
    const toastSpy = vi.spyOn((await import("sonner")).toast, "error");
    server.use(
      http.put(`${API_BASE}/settings/active-page`, () => HttpResponse.json({ error: "Failed" }, { status: 500 })),
    );

    const user = userEvent.setup();
    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /^Change Page$/ })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /^Change Page$/ }));
    await user.click(await screen.findByRole("button", { name: /Custom Template/ }));
    await user.click(screen.getByRole("button", { name: "Show now" }));

    await waitFor(() => expect(toastSpy).toHaveBeenCalledWith("Couldn’t change the page"));

    toastSpy.mockRestore();
  });

  it("shows an error toast when the page switches but the board send fails", async () => {
    // Issue #1791: the backend persists the page but reports the render/send
    // failure via error + sent_to_board=false on a 200 response. That must
    // NOT be toasted as a success.
    const errorToastSpy = vi.spyOn((await import("sonner")).toast, "error");
    const successToastSpy = vi.spyOn((await import("sonner")).toast, "success");
    server.use(
      http.put(`${API_BASE}/settings/active-page`, () =>
        HttpResponse.json({
          status: "success",
          page_id: "page-2",
          sent_to_board: false,
          paused: false,
          board_id: null,
          error: "Weather API unreachable",
        }),
      ),
    );

    const user = userEvent.setup();
    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /^Change Page$/ })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /^Change Page$/ }));
    await user.click(await screen.findByRole("button", { name: /Custom Template/ }));
    await user.click(screen.getByRole("button", { name: "Show now" }));

    await waitFor(() => expect(errorToastSpy).toHaveBeenCalledWith("Saved, but sending to Flagship failed."));
    expect(successToastSpy).not.toHaveBeenCalled();

    errorToastSpy.mockRestore();
    successToastSpy.mockRestore();
  });
});
