/**
 * BoardOutOfSyncBanner (issue #1945): the one banner Home and each display's
 * own page show when another app wrote to the board.
 *
 * Two faces: "out-of-sync" while the board shows something FiestaBoard did not
 * send ([Restore] [Save as page]), and "kept" after FiestaBoard repainted but
 * the backend still holds the last confirmed external frame ([Save as page]
 * [Dismiss]). Restore reads `sent` from POST /force-refresh and tells the
 * truth when silence or pause held the send.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { toast } from "sonner";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BoardOutOfSyncBanner, type BoardOutOfSyncBannerProps } from "@/components/board-out-of-sync-banner";
import type { BoardCurrentMessageResponse, SilenceStatus } from "@/lib/api";

import { server } from "./mocks/server";

const API = "/api";

const push = vi.fn();
vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({ push, replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
}));

vi.mock("@/components/smart-link", () => ({
  default: ({ children, href, ...rest }: { children: ReactNode; href: string }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

function grid(code: number): number[][] {
  return Array.from({ length: 6 }, () => Array(22).fill(code));
}

/** Row 0 reads "HI" and a red tile; the rest is blank. */
function hiRed(): number[][] {
  const g = grid(0);
  g[0][0] = 8;
  g[0][1] = 9;
  g[0][2] = 63;
  return g;
}

const EXPECTED = grid(2);

function boardState(overrides: Partial<BoardCurrentMessageResponse> = {}): BoardCurrentMessageResponse {
  return {
    characters: EXPECTED,
    message: "",
    rows: 6,
    cols: 22,
    expected_characters: EXPECTED,
    cached_at: null,
    api_mode: "local",
    ...overrides,
  } as BoardCurrentMessageResponse;
}

/** Serve *body* for GET /board/current-message; returns a request counter. */
function serveBoard(body: BoardCurrentMessageResponse | (() => BoardCurrentMessageResponse)) {
  const seen: string[] = [];
  server.use(
    http.get(`${API}/board/current-message`, ({ request }) => {
      seen.push(request.url);
      return HttpResponse.json(typeof body === "function" ? body() : body);
    }),
  );
  return seen;
}

function serveSilence(status: Partial<SilenceStatus>) {
  server.use(
    http.get(`${API}/silence-status`, () =>
      HttpResponse.json({
        enabled: true,
        active: false,
        start_time_utc: "22:00+00:00",
        end_time_utc: "07:00+00:00",
        current_time_utc: "23:00+00:00",
        next_change_utc: "07:00+00:00",
        ...status,
      }),
    ),
  );
}

function serveForceRefresh(sent: boolean) {
  const calls: number[] = [];
  server.use(
    http.post(`${API}/force-refresh`, () => {
      calls.push(1);
      return HttpResponse.json({ message: sent ? "Display force-refreshed" : "Nothing sent", sent });
    }),
  );
  return calls;
}

function recordDismiss() {
  const urls: string[] = [];
  server.use(
    http.delete(`${API}/board/external-frame`, ({ request }) => {
      urls.push(request.url);
      return new HttpResponse(null, { status: 204 });
    }),
  );
  return urls;
}

function recordCreatePage(status = 201) {
  const bodies: Record<string, unknown>[] = [];
  server.use(
    http.post(`${API}/v1/pages`, async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      bodies.push(body);
      if (status >= 400) return HttpResponse.json({ detail: "nope" }, { status });
      return HttpResponse.json({ id: "new-page", ...body }, { status: 201 });
    }),
  );
  return bodies;
}

const FLAGSHIP = { deviceType: "flagship", notesWide: 1, notesTall: 1 } as const;

function renderBanner(props: Partial<BoardOutOfSyncBannerProps> = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const utils = render(
    <QueryClientProvider client={queryClient}>
      <BoardOutOfSyncBanner geometry={FLAGSHIP} paused={false} multiBoard={false} isPrimary={true} {...props} />
    </QueryClientProvider>,
  );
  return { ...utils, queryClient };
}

const banner = () => screen.queryByTestId("board-out-of-sync");

/** Today at 07:00 UTC as the viewer's zone writes a short time. */
function shortTimeOfUtc(hours: number, minutes: number, locale = "en") {
  const now = new Date();
  const at = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), hours, minutes));
  return new Intl.DateTimeFormat(locale, { timeStyle: "short" }).format(at);
}

describe("BoardOutOfSyncBanner", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  describe("when it renders", () => {
    it("renders nothing when the board shows what FiestaBoard sent", async () => {
      const seen = serveBoard(boardState());
      renderBanner();

      await waitFor(() => expect(seen.length).toBeGreaterThan(0));
      await act(() => new Promise((r) => setTimeout(r, 50)));
      expect(banner()).toBeNull();
    });

    it("renders nothing while the board state is still loading", async () => {
      server.use(http.get(`${API}/board/current-message`, () => new Promise(() => {})));
      const { container } = renderBanner();

      await act(() => new Promise((r) => setTimeout(r, 50)));
      expect(container).toBeEmptyDOMElement();
    });

    it("shows the warning face when the board differs from what FiestaBoard sent", async () => {
      serveBoard(boardState({ characters: hiRed() }));
      renderBanner();

      const alert = await screen.findByTestId("board-out-of-sync");
      expect(alert).toHaveAttribute("data-face", "out-of-sync");
      expect(within(alert).getByText("Another app changed this board")).toBeInTheDocument();
      expect(
        within(alert).getByText("FiestaBoard will replace it the next time your page updates. Save it as a page to keep it."),
      ).toBeInTheDocument();
      expect(within(alert).getByRole("button", { name: "Restore" })).toBeEnabled();
      expect(within(alert).getByRole("button", { name: "Save as page" })).toBeEnabled();
    });

    it("hides everything while Live Mode drives the board (suppressed)", async () => {
      const seen = serveBoard(boardState({ characters: hiRed() }));
      renderBanner({ suppressed: true });

      await waitFor(() => expect(seen.length).toBeGreaterThan(0));
      await act(() => new Promise((r) => setTimeout(r, 50)));
      expect(banner()).toBeNull();
    });

    it("shows only the out-of-sync face when the board differs and a frame is also held", async () => {
      serveBoard(
        boardState({
          characters: hiRed(),
          external_characters: grid(5),
          external_detected_at: new Date().toISOString(),
        }),
      );
      renderBanner();

      const alert = await screen.findByTestId("board-out-of-sync");
      expect(alert).toHaveAttribute("data-face", "out-of-sync");
      expect(screen.queryByText(/Another app wrote to this board/)).toBeNull();
      expect(screen.queryByRole("button", { name: "Dismiss" })).toBeNull();
    });

    it("scopes its board read to the board it is given", async () => {
      const seen = serveBoard(boardState({ characters: hiRed() }));
      renderBanner({ boardId: "b2" });

      await screen.findByTestId("board-out-of-sync");
      expect(seen.every((url) => new URL(url).searchParams.get("board_id") === "b2")).toBe(true);
    });
  });

  describe("hold line", () => {
    it("says a paused display holds Restore", async () => {
      serveBoard(boardState({ characters: hiRed() }));
      renderBanner({ paused: true });

      expect(
        await screen.findByText("This display is paused, so Restore won't send anything until you resume it."),
      ).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Restore" })).toBeEnabled();
    });

    it("says silence holds Restore until the window ends", async () => {
      serveBoard(boardState({ characters: hiRed() }));
      serveSilence({ active: true, end_time_utc: "07:00+00:00" });
      renderBanner();

      const time = shortTimeOfUtc(7, 0);
      expect(
        await screen.findByText(`Silence mode is on until ${time}, so Restore won't send anything until then.`),
      ).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Restore" })).toBeEnabled();
    });

    it("says Restore resends every display on a secondary board", async () => {
      serveBoard(boardState({ characters: hiRed() }));
      renderBanner({ boardId: "b2", multiBoard: true, isPrimary: false });

      expect(await screen.findByText("Restore resends pages to every display.")).toBeInTheDocument();
    });

    it("shows no hold line on the primary board of a running, unsilenced install", async () => {
      serveBoard(boardState({ characters: hiRed() }));
      renderBanner({ multiBoard: true, isPrimary: true });

      await screen.findByTestId("board-out-of-sync");
      expect(screen.queryByTestId("board-out-of-sync-hold")).toBeNull();
    });

    it("shows one hold line at a time, pause first", async () => {
      serveBoard(boardState({ characters: hiRed() }));
      serveSilence({ active: true });
      renderBanner({ paused: true, boardId: "b2", multiBoard: true, isPrimary: false });

      await screen.findByText(/This display is paused/);
      await act(() => new Promise((r) => setTimeout(r, 50)));
      expect(screen.getAllByTestId("board-out-of-sync-hold")).toHaveLength(1);
      expect(screen.queryByText(/Silence mode is on until/)).toBeNull();
      expect(screen.queryByText("Restore resends pages to every display.")).toBeNull();
    });
  });

  describe("Restore", () => {
    it("marks the board in sync, forgets the held frame and says so when the send reached the board", async () => {
      const success = vi.spyOn(toast, "success");
      serveBoard(boardState({ characters: hiRed() }));
      const refreshes = serveForceRefresh(true);
      const dismissed = recordDismiss();
      const user = userEvent.setup();
      const { queryClient } = renderBanner();

      await user.click(await screen.findByRole("button", { name: "Restore" }));

      await waitFor(() => expect(success).toHaveBeenCalledWith("Board restored"));
      expect(refreshes).toHaveLength(1);
      const cached = queryClient.getQueryData<BoardCurrentMessageResponse>(["board-current-message"]);
      expect(cached?.characters).toEqual(EXPECTED);
      await waitFor(() => expect(dismissed).toHaveLength(1));
      expect(new URL(dismissed[0]).searchParams.get("board_id")).toBeNull();
      await waitFor(() => expect(banner()).toBeNull());
    });

    it("does not fall back to the kept notice after a successful Restore", async () => {
      serveBoard(
        boardState({
          characters: hiRed(),
          external_characters: hiRed(),
          external_detected_at: new Date().toISOString(),
        }),
      );
      serveForceRefresh(true);
      const user = userEvent.setup();
      renderBanner();

      await user.click(await screen.findByRole("button", { name: "Restore" }));

      await waitFor(() => expect(banner()).toBeNull());
    });

    it("forgets the held frame of the board it is scoped to", async () => {
      serveBoard(boardState({ characters: hiRed() }));
      serveForceRefresh(true);
      const dismissed = recordDismiss();
      const user = userEvent.setup();
      renderBanner({ boardId: "b2", multiBoard: true, isPrimary: true });

      await user.click(await screen.findByRole("button", { name: "Restore" }));

      await waitFor(() => expect(dismissed).toHaveLength(1));
      expect(new URL(dismissed[0]).searchParams.get("board_id")).toBe("b2");
    });

    it("says pages were resent to every display on a secondary board", async () => {
      const success = vi.spyOn(toast, "success");
      serveBoard(boardState({ characters: hiRed() }));
      serveForceRefresh(true);
      const user = userEvent.setup();
      renderBanner({ boardId: "b2", multiBoard: true, isPrimary: false });

      await user.click(await screen.findByRole("button", { name: "Restore" }));

      await waitFor(() => expect(success).toHaveBeenCalledWith("Pages resent to every display"));
    });

    it("leaves the banner up and says nothing was sent when the send did not happen", async () => {
      const warning = vi.spyOn(toast, "warning");
      const success = vi.spyOn(toast, "success");
      serveBoard(boardState({ characters: hiRed() }));
      serveForceRefresh(false);
      const dismissed = recordDismiss();
      const user = userEvent.setup();
      const { queryClient } = renderBanner();

      await user.click(await screen.findByRole("button", { name: "Restore" }));

      await waitFor(() => expect(warning).toHaveBeenCalledWith("Nothing was sent to the display"));
      expect(success).not.toHaveBeenCalled();
      const cached = queryClient.getQueryData<BoardCurrentMessageResponse>(["board-current-message"]);
      expect(cached?.characters).toEqual(hiRed());
      expect(banner()).toBeInTheDocument();
      expect(dismissed).toHaveLength(0);
    });

    it("names silence as the reason nothing was sent", async () => {
      const warning = vi.spyOn(toast, "warning");
      serveBoard(boardState({ characters: hiRed() }));
      serveSilence({ active: true, end_time_utc: "07:00+00:00" });
      serveForceRefresh(false);
      const user = userEvent.setup();
      renderBanner();

      await screen.findByText(/Silence mode is on until/);
      await user.click(screen.getByRole("button", { name: "Restore" }));

      await waitFor(() =>
        expect(warning).toHaveBeenCalledWith(`Nothing was sent: silence mode is on until ${shortTimeOfUtc(7, 0)}`),
      );
      expect(banner()).toBeInTheDocument();
    });

    it("names pause as the reason nothing was sent", async () => {
      const warning = vi.spyOn(toast, "warning");
      serveBoard(boardState({ characters: hiRed() }));
      serveForceRefresh(false);
      const user = userEvent.setup();
      renderBanner({ paused: true });

      await user.click(await screen.findByRole("button", { name: "Restore" }));

      await waitFor(() => expect(warning).toHaveBeenCalledWith("Nothing was sent: this display is paused"));
    });

    it("says Restore failed when the request fails", async () => {
      const error = vi.spyOn(toast, "error");
      serveBoard(boardState({ characters: hiRed() }));
      server.use(http.post(`${API}/force-refresh`, () => HttpResponse.json({ detail: "x" }, { status: 503 })));
      const user = userEvent.setup();
      renderBanner();

      await user.click(await screen.findByRole("button", { name: "Restore" }));

      await waitFor(() => expect(error).toHaveBeenCalledWith("Failed to restore board"));
      expect(banner()).toBeInTheDocument();
    });
  });

  describe("Save as page", () => {
    it("saves what the board shows as a template page in the board's geometry", async () => {
      serveBoard(boardState({ characters: hiRed() }));
      const created = recordCreatePage();
      const user = userEvent.setup();
      renderBanner({ geometry: { deviceType: "note_array", notesWide: 2, notesTall: 2 } });

      await user.click(await screen.findByRole("button", { name: "Save as page" }));

      await waitFor(() => expect(created).toHaveLength(1));
      expect(created[0]).toMatchObject({
        type: "template",
        device_type: "note_array",
        notes_wide: 2,
        notes_tall: 2,
        template: ["HI{{red}}", "", "", "", "", ""],
      });
      expect(String(created[0].name)).toMatch(/^From board /);
    });

    it("turns the button into a Saved as note with an Open page link", async () => {
      serveBoard(boardState({ characters: hiRed() }));
      const created = recordCreatePage();
      const user = userEvent.setup();
      renderBanner();

      await user.click(await screen.findByRole("button", { name: "Save as page" }));

      const alert = await screen.findByTestId("board-out-of-sync");
      await waitFor(() => expect(alert).toHaveAttribute("data-saved", "true"));
      expect(within(alert).queryByRole("button", { name: "Save as page" })).toBeNull();
      const name = String(created[0].name);
      expect(within(alert).getByText(`Saved as “${name}”`)).toBeInTheDocument();
      expect(within(alert).getByRole("link", { name: "Open page" })).toHaveAttribute("href", "/pages/edit/new-page");
      // Restore stays.
      expect(within(alert).getByRole("button", { name: "Restore" })).toBeInTheDocument();
      expect(created).toHaveLength(1);
    });

    it("brings the button back when the board shows something new", async () => {
      let current = hiRed();
      serveBoard(() => boardState({ characters: current }));
      recordCreatePage();
      const user = userEvent.setup();
      const { queryClient } = renderBanner();

      await user.click(await screen.findByRole("button", { name: "Save as page" }));
      await screen.findByRole("link", { name: "Open page" });

      current = grid(9);
      await act(() => queryClient.invalidateQueries({ queryKey: ["board-current-message"] }));

      expect(await screen.findByRole("button", { name: "Save as page" })).toBeInTheDocument();
      expect(screen.queryByRole("link", { name: "Open page" })).toBeNull();
    });

    it("keeps the button and says so when saving fails", async () => {
      const error = vi.spyOn(toast, "error");
      serveBoard(boardState({ characters: hiRed() }));
      recordCreatePage(500);
      const user = userEvent.setup();
      renderBanner();

      await user.click(await screen.findByRole("button", { name: "Save as page" }));

      await waitFor(() => expect(error).toHaveBeenCalledWith("Failed to save board as a page"));
      expect(screen.getByRole("button", { name: "Save as page" })).toBeEnabled();
      expect(banner()).not.toHaveAttribute("data-saved");
    });
  });

  describe("kept face", () => {
    it("offers to save the held frame after FiestaBoard put the page back", async () => {
      const detected = new Date();
      serveBoard(boardState({ external_characters: hiRed(), external_detected_at: detected.toISOString() }));
      renderBanner();

      const alert = await screen.findByTestId("board-out-of-sync");
      expect(alert).toHaveAttribute("data-face", "kept");
      const time = new Intl.DateTimeFormat("en", { timeStyle: "short" }).format(detected);
      expect(within(alert).getByText(`Another app wrote to this board at ${time}`)).toBeInTheDocument();
      expect(
        within(alert).getByText(
          "FiestaBoard has since put your page back. You can still save what the other app wrote.",
        ),
      ).toBeInTheDocument();
      expect(within(alert).getByRole("button", { name: "Save as page" })).toBeInTheDocument();
      expect(within(alert).getByRole("button", { name: "Dismiss" })).toBeInTheDocument();
      expect(within(alert).queryByRole("button", { name: "Restore" })).toBeNull();
    });

    it("writes the date as well when the write was not today", async () => {
      const detected = new Date(Date.now() - 2 * 24 * 60 * 60 * 1000);
      serveBoard(boardState({ external_characters: hiRed(), external_detected_at: detected.toISOString() }));
      renderBanner();

      const when = new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short" }).format(detected);
      expect(await screen.findByText(`Another app wrote to this board at ${when}`)).toBeInTheDocument();
    });

    it("renders nothing when the held frame is what FiestaBoard shows", async () => {
      const seen = serveBoard(
        boardState({ external_characters: EXPECTED, external_detected_at: new Date().toISOString() }),
      );
      renderBanner();

      await waitFor(() => expect(seen.length).toBeGreaterThan(0));
      await act(() => new Promise((r) => setTimeout(r, 50)));
      expect(banner()).toBeNull();
    });

    it("saves the held frame, not what the board shows now", async () => {
      serveBoard(boardState({ external_characters: hiRed(), external_detected_at: new Date().toISOString() }));
      const created = recordCreatePage();
      const user = userEvent.setup();
      renderBanner();

      await user.click(await screen.findByRole("button", { name: "Save as page" }));

      await waitFor(() => expect(created).toHaveLength(1));
      expect(created[0].template).toEqual(["HI{{red}}", "", "", "", "", ""]);
      expect(await screen.findByRole("link", { name: "Open page" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Dismiss" })).toBeInTheDocument();
    });

    it("Dismiss forgets the frame, hides the notice at once and keeps it hidden after the refetch", async () => {
      let held = true;
      serveBoard(() =>
        held
          ? boardState({ external_characters: hiRed(), external_detected_at: new Date().toISOString() })
          : boardState(),
      );
      const dismissed: string[] = [];
      // Hold the DELETE open so "at once" means before the server answered.
      let release: () => void = () => {};
      const gate = new Promise<void>((resolve) => (release = resolve));
      server.use(
        http.delete(`${API}/board/external-frame`, async ({ request }) => {
          dismissed.push(request.url);
          await gate;
          held = false;
          return new HttpResponse(null, { status: 204 });
        }),
      );
      const user = userEvent.setup();
      renderBanner({ boardId: "b2", multiBoard: true, isPrimary: false });

      await user.click(await screen.findByRole("button", { name: "Dismiss" }));

      expect(banner()).toBeNull();
      release();
      await waitFor(() => expect(dismissed).toHaveLength(1));
      expect(new URL(dismissed[0]).searchParams.get("board_id")).toBe("b2");
      await act(() => new Promise((r) => setTimeout(r, 100)));
      expect(banner()).toBeNull();
    });
  });

  describe("accessibility", () => {
    it("names every out-of-sync button by its visible label", async () => {
      serveBoard(boardState({ characters: hiRed() }));
      renderBanner();

      const alert = await screen.findByTestId("board-out-of-sync");
      for (const button of within(alert).getAllByRole("button")) {
        expect(button).toHaveAccessibleName(button.textContent?.trim() ?? "");
      }
    });

    it("names every kept-face button by its visible label", async () => {
      serveBoard(boardState({ external_characters: hiRed(), external_detected_at: new Date().toISOString() }));
      renderBanner();

      const alert = await screen.findByTestId("board-out-of-sync");
      const buttons = within(alert).getAllByRole("button");
      expect(buttons.length).toBe(2);
      for (const button of buttons) {
        expect(button).toHaveAccessibleName(button.textContent?.trim() ?? "");
      }
    });
  });
});
