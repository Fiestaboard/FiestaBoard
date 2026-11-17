import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { PageBuilder } from "@/components/page-builder";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

import { server } from "./mocks/server";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn(), dismiss: vi.fn() },
}));
const board = { id: "test-board", name: "Kitchen board", device_type: "flagship", enabled: true, board_color: "black" };
function Wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <ConfigOverridesProvider>
        <ThemeProvider attribute="class" defaultTheme="light">
          {children}
        </ThemeProvider>
      </ConfigOverridesProvider>
    </QueryClientProvider>
  );
}
let visibilityStyle: HTMLStyleElement;
afterEach(() => visibilityStyle?.remove());
beforeEach(() => {
  visibilityStyle = document.createElement("style");
  visibilityStyle.textContent = ".hidden { display: none; }";
  document.head.appendChild(visibilityStyle);
  localStorage.clear();
  sessionStorage.clear();
  server.use(
    http.get("/api/settings/board", () =>
      HttpResponse.json({ boards: [board], devices: ["flagship"], board_type: "black" }),
    ),
    http.get("/api/v1/boards/test-board", () =>
      HttpResponse.json({ ...board, drawing: { source: "profile", features: {} } }),
    ),
  );
});
it("keeps the preview docked without a hide control below 1024 and has one controlled mode toggle", async () => {
  vi.spyOn(window, "matchMedia").mockImplementation(
    (q) =>
      ({
        matches: q.includes("max-width"),
        media: q,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }) as unknown as MediaQueryList,
  );
  const { container } = render(<PageBuilder onClose={vi.fn()} />, { wrapper: Wrapper });
  await waitFor(() =>
    expect(container.querySelector('[data-slot="editor-preview"]')).toHaveAttribute("data-variant", "docked"),
  );
  expect(screen.queryByRole("button", { name: /hide preview/i })).not.toBeInTheDocument();
  expect(container.querySelectorAll('[data-slot="board-preview-mode-toggle"]')).toHaveLength(1);
});
it("honors H3 baseline by exposing plain text and no palette", async () => {
  server.use(
    http.get("/api/v1/boards/test-board", () =>
      HttpResponse.json({ ...board, drawing: { source: "baseline", features: {} } }),
    ),
  );
  render(<PageBuilder onClose={vi.fn()} />, { wrapper: Wrapper });
  expect(await screen.findByText("Can’t tell what this display draws")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Colors" })).not.toBeInTheDocument();
  expect(screen.queryByRole("group", { name: "Preview size" })).not.toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: /template/i })).toBeInTheDocument();
});
it("saves in place and updates rather than creates twice", async () => {
  let creates = 0,
    updates = 0;
  server.use(
    http.post("/api/v1/pages", async ({ request }) => {
      creates++;
      return HttpResponse.json({ ...((await request.json()) as object), id: "saved-25", revision: 1 });
    }),
    http.put("/api/v1/pages/saved-25", async ({ request }) => {
      updates++;
      return HttpResponse.json({
        page: { ...((await request.json()) as object), id: "saved-25", revision: 2 },
        incompatible_references: [],
      });
    }),
  );
  const onClose = vi.fn();
  const user = userEvent.setup();
  render(<PageBuilder onClose={onClose} />, { wrapper: Wrapper });
  fireEvent.change(await screen.findByLabelText(/page name/i), { target: { value: "Kitchen morning" } });
  await user.click(screen.getByRole("button", { name: "Save Page" }));
  await waitFor(() => expect(creates).toBe(1));
  await waitFor(() => expect(screen.getByRole("button", { name: "Save Page" })).toBeEnabled());
  expect(onClose).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Save Page" }));
  await waitFor(() => expect(updates).toBe(1));
  expect(creates).toBe(1);
});

it("does not open Show now or discard edits when its prerequisite save fails", async () => {
  server.use(http.post("/api/v1/pages", () => HttpResponse.json({ detail: "Save failed" }, { status: 500 })));
  const { createRef } = await import("react");
  const ref = createRef<import("@/components/page-builder").PageBuilderHandle>();
  const user = userEvent.setup();
  render(<PageBuilder ref={ref} onClose={vi.fn()} />, { wrapper: Wrapper });
  fireEvent.change(await screen.findByLabelText(/page name/i), { target: { value: "Unsaved morning" } });
  await user.click(screen.getByRole("button", { name: "Show now" }));
  const { toast } = await import("sonner");
  await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Save failed"));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(ref.current?.hasUnsavedChanges()).toBe(true);
});

it("starts untouched new pages clean and guards their first edit", async () => {
  const { createRef } = await import("react");
  const ref = createRef<import("@/components/page-builder").PageBuilderHandle>();
  render(<PageBuilder ref={ref} onClose={vi.fn()} />, { wrapper: Wrapper });
  await screen.findByLabelText(/page name/i);
  expect(ref.current?.hasUnsavedChanges()).toBe(false);
  fireEvent.change(screen.getByLabelText(/page name/i), { target: { value: "First change" } });
  await waitFor(() => expect(ref.current?.hasUnsavedChanges()).toBe(true));
  const event = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(event);
  expect(event.defaultPrevented).toBe(true);
});

it("keeps the More-sheet mirror control available in the plain-text dock", async () => {
  vi.spyOn(window, "matchMedia").mockImplementation(
    (q) =>
      ({
        matches: q.includes("max-width"),
        media: q,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }) as unknown as MediaQueryList,
  );
  const user = userEvent.setup();
  render(<PageBuilder onClose={vi.fn()} />, { wrapper: Wrapper });
  await user.click(await screen.findByRole("button", { name: "Plain Text" }));
  await user.click(screen.getByRole("button", { name: "More" }));
  expect(await screen.findByRole("switch", { name: "Mirror to board while editing" })).toBeInTheDocument();
});

it.each(["create", "update"] as const)("keeps newer edits dirty during a pending %s for Show now", async (kind) => {
  let release!: () => void;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  let submitted: Record<string, unknown> | undefined;
  const handler = kind === "create" ? http.post : http.put;
  const id = kind === "create" ? "pending-page" : "page-1";
  server.use(
    handler(kind === "create" ? "/api/v1/pages" : "/api/v1/pages/page-1", async ({ request }) => {
      submitted = (await request.json()) as Record<string, unknown>;
      await pending;
      const page = { ...submitted, id, revision: 1 };
      return HttpResponse.json(kind === "create" ? page : { page, incompatible_references: [] });
    }),
  );
  const { createRef } = await import("react");
  const ref = createRef<import("@/components/page-builder").PageBuilderHandle>();
  const user = userEvent.setup();
  render(<PageBuilder ref={ref} pageId={kind === "update" ? "page-1" : undefined} onClose={vi.fn()} />, {
    wrapper: Wrapper,
  });
  if (kind === "update") await screen.findByDisplayValue("Weather Page");
  fireEvent.change(await screen.findByLabelText(/page name/i), { target: { value: "Submitted morning" } });
  await user.click(screen.getByRole("button", { name: "Show now" }));
  await waitFor(() => expect(submitted?.name).toBe("Submitted morning"));
  fireEvent.change(screen.getByLabelText(/page name/i), { target: { value: "Newer morning" } });
  release();
  await waitFor(() => expect(screen.getByRole("button", { name: "Save Page" })).toBeEnabled());
  expect(screen.getByDisplayValue("Newer morning")).toBeInTheDocument();
  expect(ref.current?.hasUnsavedChanges()).toBe(true);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it("offers mirroring from More in the dock with the fine-pointer desktop toolbar at 900px", async () => {
  vi.spyOn(window, "matchMedia").mockImplementation(
    (q) =>
      ({
        matches: q === "(max-width: 1023px)",
        media: q,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }) as unknown as MediaQueryList,
  );
  const user = userEvent.setup();
  render(<PageBuilder onClose={vi.fn()} />, { wrapper: Wrapper });
  await user.click(await screen.findByRole("button", { name: "More" }));
  expect(await screen.findByRole("switch", { name: "Mirror to board while editing" })).toBeInTheDocument();
});

it("shows the saved page on the explicitly selected compatible board", async () => {
  const a = { ...board, id: "board-a", name: "Display A" };
  const b = { ...board, id: "board-b", name: "Display B" };
  let activation: Record<string, unknown> | undefined;
  server.use(
    http.get("/api/settings/board", () =>
      HttpResponse.json({ boards: [a, b], devices: ["flagship"], board_type: "black" }),
    ),
    http.get("/api/v1/boards/:id", ({ params }) =>
      HttpResponse.json({
        ...a,
        id: params.id,
        paused: false,
        schedule_enabled: false,
        drawing: { source: "profile", features: {} },
      }),
    ),
    http.post("/api/v1/pages", async ({ request }) =>
      HttpResponse.json({ ...((await request.json()) as object), id: "page-1", revision: 1 }),
    ),
    http.put("/api/settings/active-page", async ({ request }) => {
      activation = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({
        page_id: "page-1",
        sent_to_board: true,
        paused: false,
        board_id: activation.board_id,
      });
    }),
  );
  const user = userEvent.setup();
  render(<PageBuilder targetBoardId="board-a" onClose={vi.fn()} />, { wrapper: Wrapper });
  fireEvent.change(await screen.findByLabelText(/page name/i), { target: { value: "New morning" } });
  await user.click(screen.getByRole("combobox", { name: "Select board for live output" }));
  await user.click(await screen.findByRole("option", { name: "Display B" }));
  await user.click(screen.getByRole("button", { name: "Show now" }));
  const { within } = await import("@testing-library/react");
  const dialog = await screen.findByRole("dialog", { name: "Change Page" });
  await user.click(within(dialog).getByRole("button", { name: "Show now" }));
  await waitFor(() => expect(activation?.board_id).toBe("board-b"));
});

it.each([390, 768])("keeps page geometry controls reachable at %ipx", async (width) => {
  vi.spyOn(window, "matchMedia").mockImplementation(
    (q) =>
      ({
        matches:
          q === "(max-width: 1023px)" || (width < 768 && q.includes("767px")) || (width < 640 && q.includes("639px")),
        media: q,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }) as unknown as MediaQueryList,
  );
  const user = userEvent.setup();
  render(<PageBuilder onClose={vi.fn()} />, { wrapper: Wrapper });
  const size = await screen.findByRole("combobox", { name: "Change board size" });
  expect(size).toBeVisible();
  await user.click(size);
  await user.click(await screen.findByRole("option", { name: /note array/i }));
  const wide = screen.getByRole("combobox", { name: /notes wide/i });
  expect(wide).toBeVisible();
  await user.click(wide);
  await user.click(await screen.findByRole("option", { name: /2.*wide/i }));
  expect(wide).toHaveTextContent("2");
});

it("renders the kit first-save toast actions in Show now then Add to Schedule order", async () => {
  server.use(
    http.post("/api/v1/pages", async ({ request }) =>
      HttpResponse.json({ ...((await request.json()) as object), id: "toast-page", revision: 1 }),
    ),
  );
  const { Toaster, toast: kitToast } = await import("@fiestaboard/ui");
  kitToast.dismiss();
  const user = userEvent.setup();
  const { container } = render(
    <>
      <Toaster />
      <PageBuilder onClose={vi.fn()} />
    </>,
    { wrapper: Wrapper },
  );
  fireEvent.change(await screen.findByLabelText(/page name/i), { target: { value: "Toast morning" } });
  await user.click(screen.getByRole("button", { name: "Save Page" }));
  await waitFor(() => expect(container.querySelector("[data-sonner-toast]")).toHaveTextContent("Saved to Pages"));
  const toastElement = container.querySelector("[data-sonner-toast]")!;
  expect(Array.from(toastElement.querySelectorAll("button")).map((button) => button.textContent)).toEqual([
    "Show now",
    "Add to Schedule",
  ]);
  kitToast.dismiss();
});

it("opens Add to Schedule in the editor's display context after a first save", async () => {
  const hall = { ...board, id: "hall", name: "Hall" };
  localStorage.setItem("fiestaboard_current_board", "hall");
  let saved: Record<string, unknown> | undefined;
  server.use(
    http.get("/api/settings/board", () =>
      HttpResponse.json({ boards: [hall, board], devices: ["flagship"], board_type: "black" }),
    ),
    http.post("/api/v1/pages", async ({ request }) => {
      saved = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ ...saved, id: "schedule-page", revision: 1 });
    }),
    http.get("/api/v1/pages/schedule-page", () => HttpResponse.json({ ...saved, id: "schedule-page", revision: 1 })),
  );
  const { CurrentBoardProvider } = await import("@/components/current-board-context");
  const { Toaster, toast: kitToast } = await import("@fiestaboard/ui");
  kitToast.dismiss();
  const user = userEvent.setup();
  const { container } = render(
    <CurrentBoardProvider>
      <Toaster />
      <PageBuilder targetBoardId={board.id} onClose={vi.fn()} />
    </CurrentBoardProvider>,
    { wrapper: Wrapper },
  );
  fireEvent.change(await screen.findByLabelText(/page name/i), { target: { value: "Scheduled morning" } });
  await user.click(screen.getByRole("button", { name: "Save Page" }));
  await waitFor(() => expect(container.querySelector("[data-sonner-toast]")).toHaveTextContent("Saved to Pages"));
  expect(localStorage.getItem("fiestaboard_current_board")).toBe("hall");
  await user.click(screen.getByRole("button", { name: "Add to Schedule" }));
  expect(localStorage.getItem("fiestaboard_current_board")).toBe(board.id);
  kitToast.dismiss();
});
