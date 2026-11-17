import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { beforeEach, expect, it, vi } from "vitest";

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
beforeEach(() => {
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
