import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { createMemoryRouter, RouterProvider } from "react-router";
import { beforeEach, expect, it, vi } from "vitest";

import { CurrentBoardProvider } from "@/components/current-board-context";
import { PageEditorBridgeProvider, usePageEditorBridge } from "@/components/page-editor-bridge-context";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";
import { getScript } from "@/lib/ai-choreography/registry";
import type { ChoreographyContext } from "@/lib/ai-choreography/types";

import NewPage from "../../app/routes/pages.new";
import { server } from "./mocks/server";

vi.unmock("react-router");

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
});

function renderNewPage(onBridge?: (bridge: ReturnType<typeof usePageEditorBridge>) => void) {
  function BridgeProbe() {
    const bridge = usePageEditorBridge();
    onBridge?.(bridge);
    return null;
  }
  const router = createMemoryRouter(
    [
      { path: "/pages/new", element: <NewPage /> },
      { path: "/pages", element: <h1>Pages destination</h1> },
    ],
    { initialEntries: ["/pages", "/pages/new?board=desk&fresh=1"], initialIndex: 1 },
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <CurrentBoardProvider>
        <ConfigOverridesProvider>
          <ThemeProvider attribute="class" defaultTheme="light">
            <PageEditorBridgeProvider>
              <BridgeProbe />
              <RouterProvider router={router} />
            </PageEditorBridgeProvider>
          </ThemeProvider>
        </ConfigOverridesProvider>
      </CurrentBoardProvider>
    </QueryClientProvider>,
  );
  return router;
}

it("creates a page for the URL's display while the sidebar selects another display", async () => {
  localStorage.clear();
  localStorage.setItem("fiestaboard_current_board", "hall");
  let saved: Record<string, unknown> | undefined;
  server.use(
    http.get("/api/settings/board", () =>
      HttpResponse.json({
        board_type: "black",
        devices: ["flagship", "note"],
        boards: [
          { id: "hall", name: "Hall", device_type: "flagship", board_color: "black", enabled: true },
          { id: "desk", name: "Desk", device_type: "note", board_color: "black", enabled: true },
        ],
      }),
    ),
    http.get("/api/v1/pages/created-page", () =>
      HttpResponse.json({ ...saved, id: "created-page", created_at: "2026-01-01T00:00:00Z" }),
    ),
    http.post("/api/v1/pages", async ({ request }) => {
      saved = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ ...saved, id: "created-page", created_at: "2026-01-01T00:00:00Z" }, { status: 201 });
    }),
  );
  const router = renderNewPage();
  const user = userEvent.setup();
  await waitFor(() => expect(screen.getByLabelText("Change board size")).toHaveTextContent("Note"));
  expect(screen.getByRole("combobox", { name: "Select board for live output" })).toHaveTextContent("Desk");
  await user.type(screen.getByLabelText(/page name/i), "Desk page");
  await user.click(screen.getByRole("button", { name: "Save Page" }));
  await waitFor(() => expect(saved).toMatchObject({ name: "Desk page", device_type: "note" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Save Page" })).toBeEnabled());
  expect(router.state.location.pathname).toBe("/pages/new");
  expect(screen.getByLabelText(/page name/i)).toHaveValue("Desk page");
  expect(screen.queryByRole("heading", { name: "Pages destination" })).not.toBeInTheDocument();
  expect(saved).toMatchObject({ name: "Desk page", device_type: "note" });
  expect(localStorage.getItem("fiestaboard_current_board")).toBe("hall");
  await act(async () => {
    await router.navigate(-1);
  });
  expect(await screen.findByRole("heading", { name: "Pages destination" })).toBeInTheDocument();
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
});

it("leaves an untouched /pages/new on Back without a discard guard", async () => {
  const router = renderNewPage();
  await screen.findByLabelText(/page name/i);
  await act(async () => {
    await router.navigate(-1);
  });
  expect(await screen.findByRole("heading", { name: "Pages destination" })).toBeInTheDocument();
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
});

it("keeps the edited new page when Back is cancelled with Keep editing", async () => {
  const router = renderNewPage();
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText(/page name/i), "Unsaved kitchen draft");
  await act(async () => {
    await router.navigate(-1);
  });
  expect(await screen.findByRole("alertdialog", { name: /^Discard changes( to .*)?\?$/ })).toBeInTheDocument();
  expect(router.state.location.pathname).toBe("/pages/new");
  await user.click(screen.getByRole("button", { name: /^Keep editing$/ }));
  await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
  expect(screen.getByLabelText(/page name/i)).toHaveValue("Unsaved kitchen draft");
  expect(router.state.location.pathname).toBe("/pages/new");
});

it("exits the edited new page when Back is confirmed with Discard changes", async () => {
  const router = renderNewPage();
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText(/page name/i), "Discard this draft");
  await act(async () => {
    await router.navigate(-1);
  });
  expect(await screen.findByRole("alertdialog", { name: /^Discard changes( to .*)?\?$/ })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /^Discard changes$/ }));
  expect(await screen.findByRole("heading", { name: "Pages destination" })).toBeInTheDocument();
  expect(router.state.location.pathname).toBe("/pages");
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
});

it("identifies the saved new page through the live AI bridge and protects later edits", async () => {
  let saved: Record<string, unknown> | undefined;
  let bridge!: ReturnType<typeof usePageEditorBridge>;
  server.use(
    http.post("/api/v1/pages", async ({ request }) => {
      saved = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ ...saved, id: "created-page", created_at: "2026-01-01T00:00:00Z" }, { status: 201 });
    }),
    http.get("/api/v1/pages/created-page", () =>
      HttpResponse.json({ ...saved, id: "created-page", created_at: "2026-01-01T00:00:00Z" }),
    ),
  );
  const router = renderNewPage((current) => {
    bridge = current;
  });
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText(/page name/i), "Saved kitchen page");
  await user.click(screen.getByRole("button", { name: "Save Page" }));
  await waitFor(() => expect(bridge.getEditorSnapshot()?.id).toBe("created-page"));
  expect(bridge.staging.pageId()).toBe("created-page");
  await user.type(screen.getByLabelText(/page name/i), " with my draft");
  expect(bridge.staging.pageId()).toBe("created-page");
  expect(bridge.staging.hasUnsavedChanges()).toBe(true);
  const ctx: ChoreographyContext = {
    navigate: vi.fn(),
    pathname: () => router.state.location.pathname,
    pageEditor: bridge.staging,
    spotlight: { show: vi.fn(), pulse: vi.fn(), caption: vi.fn(), hide: vi.fn(), ghost: vi.fn(), clearGhosts: vi.fn() },
    schedule: {
      isMounted: () => false,
      openEmpty: vi.fn(),
      openEntry: vi.fn(),
      setField: vi.fn(),
      close: vi.fn(),
      waitFor: async () => false,
      waitForForm: async () => false,
    },
    t: (key) => key,
    label: (call) => call.title,
    reducedMotion: true,
  };
  const steps = getScript("update_page").narrate(
    {
      id: "update-created",
      name: "update_page",
      args: { page_id: "created-page", name: "AI replacement" },
      title: "Update page",
      read_only: false,
      destructive: false,
      requires_approval: false,
      source: "mcp",
    },
    ctx,
  );
  expect(steps).toEqual([
    { kind: "run", run: expect.any(Function) },
    { kind: "waitFor", anchor: "page-editor.template", timeoutMs: 1500 },
    { kind: "spotlight", anchor: "page-editor.template", caption: "updatingBehindEdits", controls: "stop" },
  ]);
  await act(async () => {
    for (const step of steps) if (step.kind === "run") await step.run(ctx);
  });
  expect(ctx.navigate).not.toHaveBeenCalled();
  expect(screen.getByLabelText(/page name/i)).toHaveValue("Saved kitchen page with my draft");
  expect(bridge.staging.hasUnsavedChanges()).toBe(true);
});
