/**
 * Live Output never wakes a silenced board by itself (#1943).
 *
 * `POST /templates/render/live` answers `silenced: true, sent_to_board: false`
 * during silence. The editor keeps previewing, says so in a strip, never
 * claims the frame on Home (the live-output channel), raises no toast, and
 * does not re-send the same preview. "Send to board anyway" is the explicit
 * override; "Stop sending" and turning Live Output off end it.
 */
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
import { readLiveOutputMessage, writeLiveOutputMessage } from "@/lib/live-output-channel";

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

const SILENCED_STATUS = {
  enabled: true,
  active: true,
  start_time_utc: "00:00+00:00",
  end_time_utc: "23:59+00:00",
  current_time_utc: "12:00+00:00",
  next_change_utc: "23:59+00:00",
  seconds_until_next_change: 3600,
  ends_at_utc: "2026-05-04T15:00:00+00:00",
  mode: "freeze",
  holds_blocked_sends: false,
  held: null,
};

/** Every live-render body, answered as a silenced board would. */
function serveSilencedBoard() {
  const bodies: Record<string, unknown>[] = [];
  server.use(
    http.get(`${API_BASE}/silence-status`, () => HttpResponse.json(SILENCED_STATUS)),
    http.post(`${API_BASE}/templates/render/live`, async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      bodies.push(body);
      const overriding = body.override_silence === true;
      // Deliberately not the editor's own preview text: the live render
      // replaces the preview, which is what re-arms the mutation-path effect.
      return HttpResponse.json({
        rendered: "HI THERE LIVE",
        lines: ["HI THERE LIVE", "", "", "", "", ""],
        line_count: 6,
        sent_to_board: overriding,
        paused: false,
        silenced: !overriding,
        board_id: "board-1",
      });
    }),
  );
  return bodies;
}

async function turnLiveOn(user: ReturnType<typeof userEvent.setup>) {
  const toggle = await screen.findByRole("switch", { name: /toggle live output to board/i });
  await user.click(toggle);
  return toggle;
}

describe("PageBuilder Live Output during silence", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    writeLiveOutputMessage(null);
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
    vi.mocked(api.getBoardSettings).mockResolvedValue({ board_type: "black", boards: [BOARD], devices: ["flagship"] });
    vi.mocked(api.forceRefresh).mockResolvedValue({ message: "ok", sent: true });
  });

  afterEach(() => {
    server.resetHandlers();
    writeLiveOutputMessage(null);
  });

  it("previews only: no override in the body, no Home claim, no toast, one request", async () => {
    const bodies = serveSilencedBoard();
    const { toast } = await import("sonner");
    const user = userEvent.setup();
    render(<PageBuilder pageId="page-1" skipDraft onClose={vi.fn()} onSave={vi.fn()} />, { wrapper: TestWrapper });
    await turnLiveOn(user);

    await waitFor(() => expect(bodies.length).toBeGreaterThanOrEqual(1));
    expect(bodies[0]).not.toHaveProperty("override_silence");
    expect(await screen.findByTestId("live-silence")).toHaveTextContent(
      "Live Output is previewing only. The board stays quiet.",
    );
    expect(readLiveOutputMessage()).toBeNull();
    expect(toast.info).not.toHaveBeenCalledWith(expect.stringContaining("silenc"));
    expect(toast.error).not.toHaveBeenCalled();

    // The "last attempted" marker stays unconditional: once the live render
    // has replaced the preview, the mutation path must not re-send that same,
    // silenced preview. One live render, and nothing after it.
    await new Promise((resolve) => setTimeout(resolve, 1200));
    expect(bodies).toHaveLength(1);
  });

  it("Send to board anyway re-sends with override_silence and shows the warning strip", async () => {
    const bodies = serveSilencedBoard();
    const user = userEvent.setup();
    render(<PageBuilder pageId="page-1" skipDraft onClose={vi.fn()} onSave={vi.fn()} />, { wrapper: TestWrapper });
    await turnLiveOn(user);
    await user.click(await screen.findByTestId("live-send-anyway"));

    await waitFor(() => expect(bodies.some((b) => b.override_silence === true)).toBe(true));
    expect(await screen.findByTestId("live-silence-overriding")).toHaveTextContent(
      "Live Output is waking the board during silence.",
    );
    // A frame the board really shows is claimed on Home.
    await waitFor(() => expect(readLiveOutputMessage()).toBe("HI THERE LIVE"));
  });

  it("Stop sending goes back to previewing only", async () => {
    const bodies = serveSilencedBoard();
    const user = userEvent.setup();
    render(<PageBuilder pageId="page-1" skipDraft onClose={vi.fn()} onSave={vi.fn()} />, { wrapper: TestWrapper });
    await turnLiveOn(user);
    await user.click(await screen.findByTestId("live-send-anyway"));
    await user.click(await screen.findByTestId("live-stop-override"));

    await waitFor(() => expect(bodies[bodies.length - 1]).not.toHaveProperty("override_silence"));
    expect(await screen.findByTestId("live-silence")).toBeInTheDocument();
    expect(screen.queryByTestId("live-silence-overriding")).not.toBeInTheDocument();
  });

  it("turning Live Output off resets the override", async () => {
    const bodies = serveSilencedBoard();
    const user = userEvent.setup();
    render(<PageBuilder pageId="page-1" skipDraft onClose={vi.fn()} onSave={vi.fn()} />, { wrapper: TestWrapper });
    const toggle = await turnLiveOn(user);
    await user.click(await screen.findByTestId("live-send-anyway"));
    await waitFor(() => expect(bodies.some((b) => b.override_silence === true)).toBe(true));

    await user.click(toggle); // off
    expect(screen.queryByTestId("live-silence-overriding")).not.toBeInTheDocument();
    const before = bodies.length;
    await user.click(toggle); // on again
    await waitFor(() => expect(bodies.length).toBeGreaterThan(before));
    expect(bodies[bodies.length - 1]).not.toHaveProperty("override_silence");
  });
});
