/**
 * BoardOutOfSyncBanner (issue #1945): the one banner Home and each display's
 * own page show when another app wrote to the board.
 *
 * Two faces: "out-of-sync" while the board shows something FiestaBoard did not
 * send ([Restore] [Save as page]), and "kept" after FiestaBoard repainted but
 * the backend still holds the last confirmed external frame ([Save as page]
 * [Dismiss]). Restore calls POST /v1/boards/{board}/restore for this one
 * display (#2354) and tells the truth when silence or pause held the send.
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
  const seen = { count: 0 };
  server.use(
    http.get(`${API}/silence-status`, () => {
      seen.count += 1;
      return HttpResponse.json({
        enabled: true,
        active: false,
        start_time_utc: "22:00+00:00",
        end_time_utc: "07:00+00:00",
        current_time_utc: "23:00+00:00",
        next_change_utc: "07:00+00:00",
        ...status,
      });
    }),
  );
  return seen;
}

/** Answer Restore with `sent`, recording the board path segment of each call. */
function serveRestore(sent: boolean) {
  const boards: string[] = [];
  server.use(
    http.post(`${API}/v1/boards/:board/restore`, ({ params }) => {
      boards.push(String(params.board));
      return HttpResponse.json({
        board_id: String(params.board),
        page_id: null,
        sent,
        reason: sent ? null : "Nothing was written",
        device_observed: false,
      });
    }),
  );
  return boards;
}

/** Restore refused with 409: the board is paused or silenced. */
function refuseRestore() {
  server.use(
    http.post(`${API}/v1/boards/:board/restore`, () =>
      HttpResponse.json({ detail: "Board is paused — sends are blocked until it is resumed." }, { status: 409 }),
    ),
  );
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
      <BoardOutOfSyncBanner geometry={FLAGSHIP} paused={false} {...props} />
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
        within(alert).getByText(
          "FiestaBoard will replace it the next time your page updates. Save it as a page to keep it.",
        ),
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

    it("hides itself while the board is silenced, since Restore cannot send", async () => {
      serveBoard(boardState({ characters: hiRed() }));
      const silence = serveSilence({ active: true });
      renderBanner();

      await waitFor(() => expect(silence.count).toBeGreaterThan(0));
      await act(() => new Promise((r) => setTimeout(r, 50)));
      expect(screen.queryByTestId("board-out-of-sync")).toBeNull();
    });

    it("shows no hold line on a running, unsilenced secondary board", async () => {
      // Restore touches only this display (#2354), so there is nothing to warn about.
      serveBoard(boardState({ characters: hiRed() }));
      renderBanner({ boardId: "b2" });

      await screen.findByTestId("board-out-of-sync");
      expect(screen.queryByTestId("board-out-of-sync-hold")).toBeNull();
    });
  });

  describe("Restore", () => {
    it("marks the board in sync, forgets the held frame and says so when the send reached the board", async () => {
      const success = vi.spyOn(toast, "success");
      serveBoard(boardState({ characters: hiRed() }));
      const restored = serveRestore(true);
      const dismissed = recordDismiss();
      const user = userEvent.setup();
      const { queryClient } = renderBanner();

      await user.click(await screen.findByRole("button", { name: "Restore" }));

      await waitFor(() => expect(success).toHaveBeenCalledWith("Board restored"));
      expect(restored).toEqual(["primary"]);
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
      serveRestore(true);
      const user = userEvent.setup();
      renderBanner();

      await user.click(await screen.findByRole("button", { name: "Restore" }));

      await waitFor(() => expect(banner()).toBeNull());
    });

    it("restores only the board it is scoped to", async () => {
      serveBoard(boardState({ characters: hiRed() }));
      const restored = serveRestore(true);
      const user = userEvent.setup();
      renderBanner({ boardId: "b2" });

      await user.click(await screen.findByRole("button", { name: "Restore" }));

      await waitFor(() => expect(restored).toEqual(["b2"]));
    });

    it("forgets the held frame of the board it is scoped to", async () => {
      serveBoard(boardState({ characters: hiRed() }));
      serveRestore(true);
      const dismissed = recordDismiss();
      const user = userEvent.setup();
      renderBanner({ boardId: "b2" });

      await user.click(await screen.findByRole("button", { name: "Restore" }));

      await waitFor(() => expect(dismissed).toHaveLength(1));
      expect(new URL(dismissed[0]).searchParams.get("board_id")).toBe("b2");
    });

    it("says the board was restored on a secondary board", async () => {
      const success = vi.spyOn(toast, "success");
      serveBoard(boardState({ characters: hiRed() }));
      serveRestore(true);
      const user = userEvent.setup();
      renderBanner({ boardId: "b2" });

      await user.click(await screen.findByRole("button", { name: "Restore" }));

      await waitFor(() => expect(success).toHaveBeenCalledWith("Board restored"));
    });

    it("leaves the banner up and says nothing was sent when the send did not happen", async () => {
      const warning = vi.spyOn(toast, "warning");
      const success = vi.spyOn(toast, "success");
      serveBoard(boardState({ characters: hiRed() }));
      serveRestore(false);
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

    it("names pause as the reason nothing was sent", async () => {
      const warning = vi.spyOn(toast, "warning");
      serveBoard(boardState({ characters: hiRed() }));
      refuseRestore();
      const user = userEvent.setup();
      renderBanner({ paused: true });

      await user.click(await screen.findByRole("button", { name: "Restore" }));

      await waitFor(() =>
        expect(warning).toHaveBeenCalledWith("Nothing was sent: this display is paused", {
          description: "Board is paused — sends are blocked until it is resumed.",
        }),
      );
    });

    it("says nothing was sent, not that Restore failed, when the board refuses it", async () => {
      // A 409 is policy (pause, or silence that began after the banner showed), not breakage.
      const warning = vi.spyOn(toast, "warning");
      const error = vi.spyOn(toast, "error");
      serveBoard(boardState({ characters: hiRed() }));
      refuseRestore();
      const user = userEvent.setup();
      renderBanner();

      await user.click(await screen.findByRole("button", { name: "Restore" }));

      await waitFor(() =>
        expect(warning).toHaveBeenCalledWith("Nothing was sent to the display", {
          description: "Board is paused — sends are blocked until it is resumed.",
        }),
      );
      expect(error).not.toHaveBeenCalled();
      expect(banner()).toBeInTheDocument();
    });

    it("passes the server's reason for refusing Restore as the toast description", async () => {
      const warning = vi.spyOn(toast, "warning");
      serveBoard(boardState({ characters: hiRed() }));
      server.use(
        http.post(`${API}/v1/boards/:board/restore`, () =>
          HttpResponse.json({ detail: "Silence mode is active until 07:00." }, { status: 409 }),
        ),
      );
      const user = userEvent.setup();
      renderBanner();

      await user.click(await screen.findByRole("button", { name: "Restore" }));

      await waitFor(() =>
        expect(warning).toHaveBeenCalledWith("Nothing was sent to the display", {
          description: "Silence mode is active until 07:00.",
        }),
      );
    });

    it("says Restore failed when the request fails", async () => {
      const error = vi.spyOn(toast, "error");
      serveBoard(boardState({ characters: hiRed() }));
      server.use(
        http.post(`${API}/v1/boards/:board/restore`, () => HttpResponse.json({ detail: "x" }, { status: 503 })),
      );
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
      renderBanner({ boardId: "b2" });

      await user.click(await screen.findByRole("button", { name: "Dismiss" }));

      expect(banner()).toBeNull();
      release();
      await waitFor(() => expect(dismissed).toHaveLength(1));
      expect(new URL(dismissed[0]).searchParams.get("board_id")).toBe("b2");
      await act(() => new Promise((r) => setTimeout(r, 100)));
      expect(banner()).toBeNull();
    });
  });

  describe("overwritten face (a display that cannot read back, #2354)", () => {
    /** A Pixoo-like board: nothing to compare, only that another app wrote it. */
    function overwritten(at: Date = new Date(), overrides: Partial<BoardCurrentMessageResponse> = {}) {
      return boardState({
        characters: null,
        expected_characters: null,
        overwritten_at: at.toISOString(),
        ...overrides,
      });
    }

    it("says another app changed the display, when, and offers Restore but not Save", async () => {
      const detected = new Date();
      serveBoard(overwritten(detected));
      renderBanner();

      const alert = await screen.findByTestId("board-out-of-sync");
      expect(alert).toHaveAttribute("data-face", "overwritten");
      expect(within(alert).getByText("Another app changed this board")).toBeInTheDocument();
      const time = new Intl.DateTimeFormat("en", { timeStyle: "short" }).format(detected);
      expect(
        within(alert).getByText(
          `Detected: ${time}. FiestaBoard can't see what this display shows now, so there's nothing to save. Restore puts your page back.`,
        ),
      ).toBeInTheDocument();
      expect(within(alert).getByRole("button", { name: "Restore" })).toBeEnabled();
      expect(within(alert).queryByRole("button", { name: "Save as page" })).toBeNull();
      expect(within(alert).queryByRole("button", { name: "Dismiss" })).toBeNull();
    });

    it("renders nothing for a display that cannot read back and was not overwritten", async () => {
      const seen = serveBoard(boardState({ characters: null, expected_characters: null }));
      renderBanner();

      await waitFor(() => expect(seen.length).toBeGreaterThan(0));
      await act(() => new Promise((r) => setTimeout(r, 50)));
      expect(banner()).toBeNull();
    });

    it("shows the overwritten face for the shape a no-read-back display actually serves", async () => {
      // After its first send a Pixoo's GET /board/current-message echoes the
      // last frame FiestaBoard sent as `characters`, equal to
      // `expected_characters`; only `overwritten_at` says another app wrote it.
      serveBoard(overwritten(new Date(), { characters: EXPECTED, expected_characters: EXPECTED }));
      renderBanner();

      const alert = await screen.findByTestId("board-out-of-sync");
      expect(alert).toHaveAttribute("data-face", "overwritten");
      expect(within(alert).getByRole("button", { name: "Restore" })).toBeEnabled();
      expect(within(alert).queryByRole("button", { name: "Save as page" })).toBeNull();
    });

    it("wins over the kept face when a held frame is also there", async () => {
      serveBoard(
        overwritten(new Date(), {
          characters: EXPECTED,
          expected_characters: EXPECTED,
          external_characters: hiRed(),
          external_detected_at: new Date().toISOString(),
        }),
      );
      renderBanner();

      const alert = await screen.findByTestId("board-out-of-sync");
      expect(alert).toHaveAttribute("data-face", "overwritten");
      expect(within(alert).queryByRole("button", { name: "Save as page" })).toBeNull();
    });

    it("Restore sends this display's page back and the notice goes", async () => {
      const success = vi.spyOn(toast, "success");
      serveBoard(overwritten());
      const restored = serveRestore(true);
      const user = userEvent.setup();
      renderBanner({ boardId: "b2" });

      await user.click(await screen.findByRole("button", { name: "Restore" }));

      await waitFor(() => expect(restored).toEqual(["b2"]));
      await waitFor(() => expect(success).toHaveBeenCalledWith("Board restored"));
      await waitFor(() => expect(banner()).toBeNull());
    });

    it("hides itself while the board is silenced", async () => {
      serveBoard(overwritten());
      const silence = serveSilence({ active: true });
      renderBanner();

      await waitFor(() => expect(silence.count).toBeGreaterThan(0));
      await act(() => new Promise((r) => setTimeout(r, 50)));
      expect(banner()).toBeNull();
    });

    it("hides itself while Live Mode drives the board (suppressed)", async () => {
      const seen = serveBoard(overwritten());
      renderBanner({ suppressed: true });

      await waitFor(() => expect(seen.length).toBeGreaterThan(0));
      await act(() => new Promise((r) => setTimeout(r, 50)));
      expect(banner()).toBeNull();
    });

    it("says a paused display holds Restore", async () => {
      serveBoard(overwritten());
      renderBanner({ paused: true });

      const alert = await screen.findByTestId("board-out-of-sync");
      expect(within(alert).getByTestId("board-out-of-sync-hold")).toHaveTextContent(
        "This display is paused, so Restore won't send anything until you resume it.",
      );
    });

    it("gives way to the out-of-sync face when the board also differs from what was sent", async () => {
      serveBoard(overwritten(new Date(), { characters: hiRed(), expected_characters: EXPECTED }));
      renderBanner();

      const alert = await screen.findByTestId("board-out-of-sync");
      expect(alert).toHaveAttribute("data-face", "out-of-sync");
      expect(within(alert).getByRole("button", { name: "Save as page" })).toBeInTheDocument();
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
