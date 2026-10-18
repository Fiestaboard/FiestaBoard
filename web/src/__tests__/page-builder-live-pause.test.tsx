import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PageBuilder } from "@/components/page-builder";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";
import type { BoardInstance, Page } from "@/lib/api";
import { api } from "@/lib/api";

import { server } from "./mocks/server";

const API_BASE = "/api";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual("@/lib/api");
  return {
    ...actual,
    api: {
      ...(actual as { api: object }).api,
      renderTemplate: vi.fn(),
      getTemplateVariables: vi.fn(),
      getPage: vi.fn(),
      getBoardSettings: vi.fn(),
      forceRefresh: vi.fn(),
    },
  };
});

function TestWrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
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

const BOARD = {
  id: "board-1",
  name: "Hall",
  device_type: "flagship",
  board_color: "black",
  enabled: true,
  api_mode: "local",
  host: "",
  local_api_key: "",
  cloud_key: "",
} as BoardInstance;

const PAGE: Page = {
  id: "page-1",
  name: "Hello",
  type: "template",
  device_type: "flagship",
  template: ["HI THERE", "", "", "", "", ""],
  line_metadata: Array.from({ length: 6 }, () => ({ alignment: "left" as const, wrap: false })),
  duration_seconds: 30,
  created_at: "2026-01-01T00:00:00Z",
};

describe("PageBuilder paused Live Output target", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getTemplateVariables).mockResolvedValue({
      variables: {},
      max_lengths: {},
      colors: {},
      symbols: [],
      filters: [],
      formatting: {},
      syntax_examples: {},
    });
    vi.mocked(api.renderTemplate).mockResolvedValue({ rendered: "HI THERE", lines: ["HI THERE"], line_count: 1 });
    vi.mocked(api.getPage).mockResolvedValue(PAGE);
    vi.mocked(api.forceRefresh).mockResolvedValue({ message: "ok", sent: true });
  });

  afterEach(() => server.resetHandlers());

  function setup(boards: BoardInstance[]) {
    vi.mocked(api.getBoardSettings).mockResolvedValue({ board_type: "black", boards, devices: ["flagship"] });
    const liveRequests: unknown[] = [];
    server.use(
      http.post(`${API_BASE}/templates/render/live`, async ({ request }) => {
        liveRequests.push(await request.json());
        return HttpResponse.json({
          rendered: "HI THERE",
          lines: ["HI THERE"],
          line_count: 1,
          sent_to_board: false,
          paused: true,
        });
      }),
    );
    render(<PageBuilder pageId="page-1" skipDraft onClose={vi.fn()} onSave={vi.fn()} />, { wrapper: TestWrapper });
    return liveRequests;
  }

  it("explains a paused target before Live Output is activated, without sending", async () => {
    const requests = setup([{ ...BOARD, paused: true }]);
    expect(
      await screen.findByText(
        "This display is paused. Live Output updates the preview only until you resume the display.",
      ),
    ).toBeVisible();
    expect(screen.getByRole("switch", { name: /toggle live output to board/i })).not.toBeChecked();
    expect(screen.getByRole("switch", { name: /toggle live output to board/i })).toHaveAccessibleDescription(
      "This display is paused. Live Output updates the preview only until you resume the display.",
    );
    expect(requests).toEqual([]);
  });

  it("does not warn for a running target", async () => {
    setup([{ ...BOARD, paused: false }]);
    await screen.findByLabelText(/HI THERE/);
    expect(screen.queryByText(/This display is paused/)).not.toBeInTheDocument();
  });

  it("follows the selected live target rather than another paused board", async () => {
    setup([
      { ...BOARD, paused: false },
      { ...BOARD, id: "board-2", name: "Bedroom", paused: true },
    ]);
    const user = userEvent.setup();
    await screen.findByLabelText(/HI THERE/);
    expect(screen.queryByText(/This display is paused/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("combobox", { name: /select board/i }));
    await user.click(await screen.findByRole("option", { name: "Bedroom" }));
    expect(await screen.findByText(/This display is paused/)).toBeVisible();
    await user.click(screen.getByRole("combobox", { name: /select board/i }));
    await user.click(await screen.findByRole("option", { name: "Hall" }));
    await waitFor(() => expect(screen.queryByText(/This display is paused/)).not.toBeInTheDocument());
    expect(screen.getByRole("switch", { name: /toggle live output to board/i })).not.toHaveAttribute(
      "aria-describedby",
    );
  });
});
