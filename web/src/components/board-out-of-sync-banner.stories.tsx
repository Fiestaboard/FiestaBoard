import type { Meta, StoryObj } from "@storybook/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type ReactNode, useEffect, useState } from "react";
import { toast } from "sonner";
import { expect, userEvent, waitFor, within } from "storybook/test";

import { Toaster } from "@/components/ui/sonner";
import { useTranslations } from "@/i18n/translations";
import type { BoardCurrentMessageResponse, SilenceStatus } from "@/lib/api";

import { BoardOutOfSyncBanner } from "./board-out-of-sync-banner";

/**
 * Issue #1945: what another app put on the board, on Home and on a display's
 * own page. Every state the spec lists has a story here; the in-situ ones
 * live in Layout/ActivePageDisplay and Displays/DisplayPage.
 */

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const ROWS = 6;
const COLS = 22;

function grid(code: number): number[][] {
  return Array.from({ length: ROWS }, () => Array(COLS).fill(code));
}

/** "HI" and a red tile on row 0 — what the other app wrote. */
function external(): number[][] {
  const g = grid(0);
  g[0][0] = 8;
  g[0][1] = 9;
  g[0][2] = 63;
  return g;
}

/** FiestaBoard's own page: "GOOD MORNING". */
function expected(): number[][] {
  const g = grid(0);
  [7, 15, 15, 4, 0, 13, 15, 18, 14, 9, 14, 7].forEach((code, i) => (g[0][i] = code));
  return g;
}

/** Today at 23:42 in the viewer's zone. */
function todayAt2342(): Date {
  const d = new Date();
  d.setHours(23, 42, 0, 0);
  return d;
}

const OCT_16_2342 = new Date(2026, 9, 16, 23, 42);

/** The name the Save stub answers with, so the Saved story reads the same every run. */
const SAVED_NAME = "Saved from board Oct 17, 2026, 11:42 PM";

function state(overrides: Partial<BoardCurrentMessageResponse> = {}): BoardCurrentMessageResponse {
  return {
    characters: expected(),
    message: "",
    rows: ROWS,
    cols: COLS,
    expected_characters: expected(),
    cached_at: new Date().toISOString(),
    api_mode: "local",
    ...overrides,
  } as BoardCurrentMessageResponse;
}

const OUT_OF_SYNC = state({ characters: external() });
const KEPT = state({ external_characters: external(), external_detected_at: todayAt2342().toISOString() });

const SILENCE_OFF: SilenceStatus = {
  enabled: false,
  active: false,
  start_time_utc: "22:00+00:00",
  end_time_utc: "07:00+00:00",
  current_time_utc: "12:00+00:00",
  next_change_utc: "22:00+00:00",
};
const SILENCE_ON: SilenceStatus = { ...SILENCE_OFF, enabled: true, active: true, next_change_utc: "07:00+00:00" };

// ---------------------------------------------------------------------------
// Harness: seeded cache + a fetch stub for the three writes the banner makes
// ---------------------------------------------------------------------------

type StubResponse = { status: number; body?: unknown } | "hang";

interface Stubs {
  createPage?: StubResponse;
  forceRefresh?: StubResponse;
  dismiss?: StubResponse;
  /** What GET /board/current-message answers when the banner reads it ("hang": never). */
  refetch?: BoardCurrentMessageResponse | "hang";
}

const DEFAULT_STUBS: Required<Omit<Stubs, "refetch">> = {
  createPage: { status: 201, body: { id: "new-page", name: SAVED_NAME, type: "template" } },
  forceRefresh: { status: 200, body: { message: "Display force-refreshed", sent: true } },
  dismiss: { status: 204 },
};

function respond(r: StubResponse): Promise<Response> {
  if (r === "hang") return new Promise<Response>(() => {});
  return Promise.resolve(
    r.body === undefined
      ? new Response(null, { status: r.status })
      : new Response(JSON.stringify(r.body), { status: r.status, headers: { "Content-Type": "application/json" } }),
  );
}

/**
 * Swap `window.fetch` for the story's lifetime. Installed during the first
 * render (before any click a play function makes) and put back on unmount.
 */
function FetchStub({ stubs, children }: { stubs: Stubs; children: ReactNode }) {
  const [original] = useState(() => {
    const real = window.fetch;
    const s = { ...DEFAULT_STUBS, ...stubs };
    window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      const method = (init?.method ?? "GET").toUpperCase();
      if (method === "POST" && /\/api\/v1\/pages(\?|$)/.test(url)) return respond(s.createPage);
      if (method === "POST" && /\/api\/force-refresh(\?|$)/.test(url)) return respond(s.forceRefresh);
      if (method === "DELETE" && /\/api\/board\/external-frame(\?|$)/.test(url)) return respond(s.dismiss);
      if (method === "GET" && /\/api\/board\/current-message/.test(url) && s.refetch)
        return respond(s.refetch === "hang" ? "hang" : { status: 200, body: s.refetch });
      return real(input, init);
    };
    return real;
  });
  useEffect(() => () => void (window.fetch = original), [original]);
  return <>{children}</>;
}

function seeded(boardState: BoardCurrentMessageResponse | undefined, silence: SilenceStatus, boardId?: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  const key = boardId ? ["board-current-message", boardId] : ["board-current-message"];
  if (boardState) client.setQueryData(key, boardState);
  client.setQueryData(boardId ? ["silenceStatus", boardId] : ["silenceStatus"], silence);
  client.setQueryData(["pages"], { pages: [] });
  return client;
}

function withBanner({
  boardState,
  silence = SILENCE_OFF,
  boardId,
  stubs = {},
  caption,
}: {
  boardState: BoardCurrentMessageResponse | undefined;
  silence?: SilenceStatus;
  boardId?: string;
  stubs?: Stubs;
  caption?: string;
}) {
  return function Decorator(Story: () => ReactNode) {
    return (
      <QueryClientProvider client={seeded(boardState, silence, boardId)}>
        <FetchStub stubs={stubs}>
          <Toaster />
          <div className="max-w-3xl" data-testid="story-frame">
            {caption && <p className="mb-2 text-xs text-muted-foreground">{caption}</p>}
            <div className="min-h-4 rounded-md border border-dashed border-border/60 p-2">
              <Story />
            </div>
          </div>
        </FetchStub>
      </QueryClientProvider>
    );
  };
}

const PHONE_VIEWPORTS = {
  phone390: { name: "Phone 390×844", styles: { width: "390px", height: "844px" }, type: "mobile" },
  phone320: { name: "Phone 320×568", styles: { width: "320px", height: "568px" }, type: "mobile" },
};

const meta = {
  title: "Layout/BoardOutOfSyncBanner",
  component: BoardOutOfSyncBanner,
  parameters: {
    layout: "padded",
    viewport: { options: PHONE_VIEWPORTS },
  },
  args: {
    geometry: { deviceType: "flagship", notesWide: 1, notesTall: 1 },
    paused: false,
    multiBoard: false,
    isPrimary: true,
  },
} satisfies Meta<typeof BoardOutOfSyncBanner>;

export default meta;
type Story = StoryObj<typeof meta>;

const banner = (canvasElement: HTMLElement) => within(canvasElement).findByTestId("board-out-of-sync");

/** Both action buttons sit inside the viewport and below the title (the phone layout). */
async function expectActionsBelowTitleInViewport(canvasElement: HTMLElement) {
  const alert = await banner(canvasElement);
  const title = alert.querySelector("h5") as HTMLElement;
  const titleBox = title.getBoundingClientRect();
  for (const button of within(alert).getAllByRole("button")) {
    const box = button.getBoundingClientRect();
    await expect(box.left).toBeGreaterThanOrEqual(0);
    await expect(box.right).toBeLessThanOrEqual(window.innerWidth);
    await expect(box.top).toBeGreaterThanOrEqual(titleBox.bottom);
  }
  await expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(window.innerWidth);
}

/** Every button's accessible name is its visible label. */
async function expectButtonsNamedByLabel(canvasElement: HTMLElement) {
  const alert = await banner(canvasElement);
  for (const button of within(alert).getAllByRole("button")) {
    await expect(button).toHaveAccessibleName(button.textContent?.trim() ?? "");
  }
}

// ---------------------------------------------------------------------------
// Out of sync (live face)
// ---------------------------------------------------------------------------

export const OutOfSyncDefault: Story = {
  name: "OutOfSync / Default",
  decorators: [withBanner({ boardState: OUT_OF_SYNC })],
  play: async ({ canvasElement }) => {
    const alert = await banner(canvasElement);
    await expect(alert).toHaveAttribute("data-face", "out-of-sync");
    await expectButtonsNamedByLabel(canvasElement);
  },
};

export const OutOfSyncPhone: Story = {
  name: "OutOfSync / Phone",
  globals: { viewport: { value: "phone390", isRotated: false } },
  parameters: { testViewport: { width: 390, height: 844 } },
  decorators: [withBanner({ boardState: OUT_OF_SYNC })],
  play: async ({ canvasElement }) => {
    if (window.innerWidth <= 400) await expectActionsBelowTitleInViewport(canvasElement);
  },
};

export const OutOfSyncPhoneNarrow: Story = {
  name: "OutOfSync / Phone narrow",
  globals: { viewport: { value: "phone320", isRotated: false } },
  parameters: { testViewport: { width: 320, height: 568 } },
  decorators: [withBanner({ boardState: OUT_OF_SYNC })],
  play: async ({ canvasElement }) => {
    if (window.innerWidth <= 330) await expectActionsBelowTitleInViewport(canvasElement);
  },
};

export const OutOfSyncSilenceHold: Story = {
  name: "OutOfSync / SilenceHold",
  decorators: [
    withBanner({
      boardState: OUT_OF_SYNC,
      silence: SILENCE_ON,
      stubs: { forceRefresh: { status: 200, body: { message: "Nothing sent", sent: false } } },
    }),
  ],
  play: async ({ canvasElement }) => {
    const alert = await banner(canvasElement);
    await expect(within(alert).getByTestId("board-out-of-sync-hold")).toHaveTextContent(/Silence mode is on until/);
    const restore = within(alert).getByRole("button", { name: "Restore" });
    await expect(restore).toBeEnabled();
    await userEvent.click(restore);
    // Nothing was sent: the banner stays and the toast says why.
    await waitFor(() =>
      expect(within(document.body).getByText(/Nothing was sent: silence mode is on until/)).toBeInTheDocument(),
    );
    await expect(await banner(canvasElement)).toBeInTheDocument();
  },
};

export const OutOfSyncPausedHold: Story = {
  name: "OutOfSync / PausedHold",
  args: { paused: true },
  decorators: [withBanner({ boardState: OUT_OF_SYNC })],
};

export const OutOfSyncSecondaryBoardMultiBoard: Story = {
  name: "OutOfSync / SecondaryBoardMultiBoard",
  args: { boardId: "kitchen", multiBoard: true, isPrimary: false },
  decorators: [withBanner({ boardState: OUT_OF_SYNC, boardId: "kitchen" })],
};

export const OutOfSyncRestoring: Story = {
  name: "OutOfSync / Restoring",
  decorators: [withBanner({ boardState: OUT_OF_SYNC, stubs: { forceRefresh: "hang" } })],
  play: async ({ canvasElement }) => {
    const alert = await banner(canvasElement);
    await userEvent.click(within(alert).getByRole("button", { name: "Restore" }));
    await waitFor(() => expect(within(alert).getByRole("button", { name: "Restore" })).toBeDisabled());
    await expect(within(alert).getByRole("button", { name: "Save as page" })).toBeEnabled();
  },
};

export const OutOfSyncSaving: Story = {
  name: "OutOfSync / Saving",
  decorators: [withBanner({ boardState: OUT_OF_SYNC, stubs: { createPage: "hang" } })],
  play: async ({ canvasElement }) => {
    const alert = await banner(canvasElement);
    await userEvent.click(within(alert).getByRole("button", { name: "Save as page" }));
    await waitFor(() => expect(within(alert).getByRole("button", { name: "Save as page" })).toBeDisabled());
    await expect(within(alert).getByRole("button", { name: "Restore" })).toBeEnabled();
  },
};

export const OutOfSyncSaved: Story = {
  name: "OutOfSync / Saved",
  decorators: [withBanner({ boardState: OUT_OF_SYNC })],
  play: async ({ canvasElement }) => {
    const alert = await banner(canvasElement);
    await userEvent.click(within(alert).getByRole("button", { name: "Save as page" }));
    await waitFor(() => expect(alert).toHaveAttribute("data-saved", "true"));
    await expect(within(alert).getByText(`Saved as “${SAVED_NAME}”`)).toBeInTheDocument();
    await expect(within(alert).getByRole("link", { name: "Open page" })).toHaveAttribute(
      "href",
      "/pages/edit/new-page",
    );
    await expect(within(alert).queryByRole("button", { name: "Save as page" })).toBeNull();
    await expect(within(alert).getByRole("button", { name: "Restore" })).toBeInTheDocument();
  },
};

// ---------------------------------------------------------------------------
// Kept (after FiestaBoard repainted)
// ---------------------------------------------------------------------------

export const KeptDefault: Story = {
  name: "Kept / Default",
  decorators: [withBanner({ boardState: KEPT })],
  play: async ({ canvasElement }) => {
    const alert = await banner(canvasElement);
    await expect(alert).toHaveAttribute("data-face", "kept");
    await expectButtonsNamedByLabel(canvasElement);
  },
};

export const KeptOlderThanToday: Story = {
  name: "Kept / OlderThanToday",
  decorators: [
    withBanner({
      boardState: state({ external_characters: external(), external_detected_at: OCT_16_2342.toISOString() }),
    }),
  ],
};

export const KeptPhone: Story = {
  name: "Kept / Phone",
  globals: { viewport: { value: "phone390", isRotated: false } },
  parameters: { testViewport: { width: 390, height: 844 } },
  decorators: [withBanner({ boardState: KEPT })],
  play: async ({ canvasElement }) => {
    if (window.innerWidth <= 400) await expectActionsBelowTitleInViewport(canvasElement);
  },
};

export const KeptSaving: Story = {
  name: "Kept / Saving",
  decorators: [withBanner({ boardState: KEPT, stubs: { createPage: "hang" } })],
  play: async ({ canvasElement }) => {
    const alert = await banner(canvasElement);
    await userEvent.click(within(alert).getByRole("button", { name: "Save as page" }));
    await waitFor(() => expect(within(alert).getByRole("button", { name: "Save as page" })).toBeDisabled());
  },
};

export const KeptSaved: Story = {
  name: "Kept / Saved",
  decorators: [withBanner({ boardState: KEPT })],
  play: async ({ canvasElement }) => {
    const alert = await banner(canvasElement);
    await userEvent.click(within(alert).getByRole("button", { name: "Save as page" }));
    await waitFor(() => expect(alert).toHaveAttribute("data-saved", "true"));
    await expect(within(alert).getByRole("link", { name: "Open page" })).toBeInTheDocument();
    await expect(within(alert).getByRole("button", { name: "Dismiss" })).toBeInTheDocument();
  },
};

export const KeptDismissed: Story = {
  name: "Kept / Dismissed",
  decorators: [
    withBanner({
      boardState: KEPT,
      stubs: { refetch: state() },
      caption: "Dismiss was clicked: the notice is gone (the frame below stays empty).",
    }),
  ],
  play: async ({ canvasElement }) => {
    const alert = await banner(canvasElement);
    await userEvent.click(within(alert).getByRole("button", { name: "Dismiss" }));
    await waitFor(() => expect(within(canvasElement).queryByTestId("board-out-of-sync")).toBeNull());
  },
};

// ---------------------------------------------------------------------------
// Renders nothing
// ---------------------------------------------------------------------------

async function expectNothing(canvasElement: HTMLElement) {
  await new Promise((r) => setTimeout(r, 100));
  await expect(within(canvasElement).queryByTestId("board-out-of-sync")).toBeNull();
}

export const HiddenInSync: Story = {
  name: "Hidden / InSync",
  decorators: [withBanner({ boardState: state(), caption: "In sync, no held frame: the banner renders nothing." })],
  play: async ({ canvasElement }) => expectNothing(canvasElement),
};

export const HiddenKeptEqualsExpected: Story = {
  name: "Hidden / KeptEqualsExpected",
  decorators: [
    withBanner({
      boardState: state({ external_characters: expected(), external_detected_at: todayAt2342().toISOString() }),
      caption: "The held frame is FiestaBoard's own page: nothing to keep.",
    }),
  ],
  play: async ({ canvasElement }) => expectNothing(canvasElement),
};

export const HiddenLiveMode: Story = {
  name: "Hidden / LiveMode",
  args: { suppressed: true },
  decorators: [withBanner({ boardState: OUT_OF_SYNC, caption: "Live Mode drives the board: suppressed." })],
  play: async ({ canvasElement }) => expectNothing(canvasElement),
};

export const HiddenNoBoardStateYet: Story = {
  name: "Hidden / NoBoardStateYet",
  decorators: [
    withBanner({
      boardState: undefined,
      stubs: { refetch: "hang" },
      caption: "Board state still loading: nothing, so nothing jumps.",
    }),
  ],
  play: async ({ canvasElement }) => expectNothing(canvasElement),
};

export const LiveWinsOverKept: Story = {
  name: "LiveWinsOverKept",
  decorators: [
    withBanner({
      boardState: state({
        characters: external(),
        external_characters: grid(5),
        external_detected_at: todayAt2342().toISOString(),
      }),
    }),
  ],
  play: async ({ canvasElement }) => {
    await expect(await banner(canvasElement)).toHaveAttribute("data-face", "out-of-sync");
  },
};

export const GermanOutOfSync: Story = {
  name: "German / OutOfSync",
  globals: { locale: "de" },
  decorators: [withBanner({ boardState: OUT_OF_SYNC })],
  play: async ({ canvasElement }) => {
    const alert = await banner(canvasElement);
    await waitFor(() =>
      expect(within(alert).getByText("Eine andere App hat dieses Board geändert")).toBeInTheDocument(),
    );
    await expect(within(alert).getByRole("button", { name: "Wiederherstellen" })).toBeInTheDocument();
    await expect(within(alert).getByRole("button", { name: "Als Seite speichern" })).toBeInTheDocument();
  },
};

// ---------------------------------------------------------------------------
// Toasts the banner raises
// ---------------------------------------------------------------------------

type ToastKind = "success" | "warning" | "error";

function ToastOnMount({ kind, message, withOpen }: { kind: ToastKind; message: string; withOpen?: boolean }) {
  const t = useTranslations("boardOutOfSync");
  useEffect(() => {
    const id = toast[kind](message, {
      duration: Infinity,
      ...(withOpen ? { action: { label: t("toastOpen"), onClick: () => {} } } : {}),
    });
    return () => void toast.dismiss(id);
  }, [kind, message, withOpen, t]);
  return <Toaster />;
}

function ToastStory({
  kind,
  msgKey,
  params,
  withOpen,
}: {
  kind: ToastKind;
  msgKey: string;
  params?: Record<string, string>;
  withOpen?: boolean;
}) {
  const t = useTranslations("boardOutOfSync");
  return <ToastOnMount kind={kind} message={t(msgKey, params)} withOpen={withOpen} />;
}

const toastStory = (kind: ToastKind, msgKey: string, params?: Record<string, string>, withOpen?: boolean): Story => ({
  render: () => <ToastStory kind={kind} msgKey={msgKey} params={params} withOpen={withOpen} />,
});

export const ToastRestored: Story = { name: "Toasts / Restored", ...toastStory("success", "toastRestored") };
export const ToastRestoredAll: Story = { name: "Toasts / RestoredAll", ...toastStory("success", "toastRestoredAll") };
export const ToastNotSentSilence: Story = {
  name: "Toasts / NotSentSilence",
  ...toastStory("warning", "toastNotSentSilence", { time: "7:00 AM" }),
};
export const ToastNotSentPaused: Story = {
  name: "Toasts / NotSentPaused",
  ...toastStory("warning", "toastNotSentPaused"),
};
export const ToastNotSent: Story = { name: "Toasts / NotSent", ...toastStory("warning", "toastNotSent") };
export const ToastSaved: Story = {
  name: "Toasts / Saved",
  ...toastStory("success", "toastSaved", { pageName: SAVED_NAME }, true),
};
export const ToastSaveFailed: Story = { name: "Toasts / SaveFailed", ...toastStory("error", "toastSaveFailed") };
export const ToastRestoreFailed: Story = {
  name: "Toasts / RestoreFailed",
  ...toastStory("error", "toastRestoreFailed"),
};
