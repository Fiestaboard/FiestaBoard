import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { FlexiblePageEditor } from "@/components/flexible-page-editor";
import type { BoardInstance } from "@/lib/api";

import { server } from "./mocks/server";

const initial = {
  id: "p",
  revision: "original",
  name: "Morning",
  type: "flexible" as const,
  duration_seconds: 30,
  blocks: [{ id: "heading", kind: "text", text: "Original" }],
};
let originalLocation: Location;
let navigate: ReturnType<typeof vi.fn>;
beforeEach(() => {
  originalLocation = window.location;
  navigate = vi.fn();
  Object.defineProperty(window, "location", {
    configurable: true,
    value: { ...originalLocation, pathname: "/pages/edit/p", search: "", assign: navigate },
  });
});
afterEach(() => {
  Object.defineProperty(window, "location", { configurable: true, value: originalLocation });
  delete (window as Window & { __reactRouterContext?: unknown }).__reactRouterContext;
});
function mount(fresh = false, boards: BoardInstance[] = [], providedClient?: QueryClient) {
  const onSave = vi.fn();
  const client = providedClient ?? new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <FlexiblePageEditor
        initialPage={fresh ? { ...initial, id: undefined, revision: undefined } : initial}
        boards={boards}
        onClose={vi.fn()}
        onSave={onSave}
      />
    </QueryClientProvider>,
  );
  return onSave;
}

it.each([false, true])(
  "keeps the draft on %s create/update authentication failure until an explicit retry",
  async (fresh) => {
    let writes = 0;
    const handler = async ({ request }: { request: Request }) => {
      writes++;
      const body = await request.json();
      if (writes === 1) return HttpResponse.json({ detail: "Not authenticated" }, { status: 401 });
      return HttpResponse.json(
        fresh
          ? { ...initial, ...body, id: "saved" }
          : { page: { ...initial, ...body, revision: "new" }, incompatible_references: [] },
        { status: fresh ? 201 : 200 },
      );
    };
    server.use(fresh ? http.post("/api/v1/pages", handler) : http.put("/api/v1/pages/p", handler));
    const onSave = mount(fresh);
    const user = userEvent.setup();
    await user.clear(screen.getByLabelText("Block 1 text"));
    await user.type(screen.getByLabelText("Block 1 text"), "Keep this draft");
    await user.click(screen.getByRole("button", { name: "Save page" }));
    const link = await screen.findByRole("link", { name: "Sign in in another tab" });
    expect(link).toHaveAttribute("href", "/login");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
    expect(screen.getByRole("alert")).toHaveTextContent(/Keep this editor open/);
    expect(screen.getByLabelText("Block 1 text")).toHaveValue("Keep this draft");
    expect(navigate).not.toHaveBeenCalled();
    expect(writes).toBe(1);
    expect(onSave).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Save page" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect(writes).toBe(2);
    expect(screen.queryByRole("link", { name: "Sign in in another tab" })).not.toBeInTheDocument();
  },
);

it("keeps a permission rejection distinct from a sign-in failure", async () => {
  server.use(
    http.put("/api/v1/pages/p", () =>
      HttpResponse.json({ detail: "This TV sign-in does not permit that operation." }, { status: 403 }),
    ),
  );
  mount();
  fireEvent.change(screen.getByLabelText("Block 1 text"), { target: { value: "Keep the denied draft" } });
  fireEvent.click(screen.getByRole("button", { name: "Save page" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("does not permit");
  expect(screen.queryByRole("link", { name: "Sign in in another tab" })).not.toBeInTheDocument();
  expect(screen.getByLabelText("Block 1 text")).toHaveValue("Keep the denied draft");
  expect(navigate).not.toHaveBeenCalled();
});

it("shows preview-only authentication recovery in page actions and clears it after explicit preview retry", async () => {
  let previews = 0;
  server.use(
    http.post("/api/pages/preview/flexible", () => {
      previews++;
      return previews === 1
        ? HttpResponse.json({ detail: "Not authenticated" }, { status: 401 })
        : HttpResponse.json({
            page_id: "unsaved",
            available: true,
            message: "Original",
            lines: ["Original"],
            display_type: "page:flexible",
            raw: {},
          });
    }),
  );
  const onSave = mount(false, [{ id: "board", name: "Desk", device_type: "flagship" } as BoardInstance]);
  const link = await screen.findByRole("link", { name: "Sign in in another tab" });
  expect(screen.getByRole("group", { name: "Page actions" })).toContainElement(link);
  expect(navigate).not.toHaveBeenCalled();
  expect(screen.getByLabelText("Block 1 text")).toHaveValue("Original");
  expect(onSave).not.toHaveBeenCalled();
  await userEvent.setup().click(screen.getByRole("button", { name: "Retry preview" }));
  await waitFor(() => expect(screen.queryByRole("link", { name: "Sign in in another tab" })).not.toBeInTheDocument());
  expect(previews).toBe(2);
  expect(onSave).not.toHaveBeenCalled();
});

it("opens recovery at the same ingress prefix without leaving the editor", async () => {
  (window as Window & { __reactRouterContext?: { basename: string } }).__reactRouterContext = {
    basename: "/ingress/test/",
  };
  server.use(
    http.put("/ingress/test/api/v1/pages/p", () => HttpResponse.json({ detail: "Not authenticated" }, { status: 401 })),
  );
  mount();
  fireEvent.click(screen.getByRole("button", { name: "Save page" }));
  expect(await screen.findByRole("link", { name: "Sign in in another tab" })).toHaveAttribute(
    "href",
    "/ingress/test/login",
  );
  expect(navigate).not.toHaveBeenCalled();
});

it("clears obsolete sign-in guidance after a successful preview without saving the draft", async () => {
  let writes = 0;
  server.use(
    http.put("/api/v1/pages/p", () => {
      writes++;
      return HttpResponse.json({ detail: "Not authenticated" }, { status: 401 });
    }),
    http.post("/api/pages/preview/flexible", () =>
      HttpResponse.json({
        page_id: "unsaved",
        available: true,
        message: "Original",
        lines: ["Original"],
        display_type: "page:flexible",
        raw: {},
      }),
    ),
  );
  const onSave = mount(false, [{ id: "board", name: "Desk", device_type: "flagship" } as BoardInstance]);
  await screen.findByLabelText("Desk character preview");
  fireEvent.change(screen.getByLabelText("Block 1 text"), { target: { value: "Unsaved before expiry" } });
  await waitFor(() => expect(screen.queryByText("Rendering…")).not.toBeInTheDocument());
  fireEvent.click(screen.getByRole("button", { name: "Save page" }));
  await screen.findByRole("link", { name: "Sign in in another tab" });
  fireEvent.change(screen.getByLabelText("Block 1 text"), { target: { value: "Unsaved after sign-in" } });
  await waitFor(() => expect(screen.queryByRole("link", { name: "Sign in in another tab" })).not.toBeInTheDocument());
  expect(screen.getByLabelText("Block 1 text")).toHaveValue("Unsaved after sign-in");
  expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
  expect(writes).toBe(1);
  expect(onSave).not.toHaveBeenCalled();
});

it("keeps newer Save authentication guidance when an earlier successful preview arrives late", async () => {
  let release!: () => void;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  server.use(
    http.post("/api/pages/preview/flexible", async () => {
      await pending;
      return HttpResponse.json({
        page_id: "unsaved",
        available: true,
        message: "Earlier",
        lines: ["Earlier"],
        display_type: "page:flexible",
        raw: {},
      });
    }),
    http.put("/api/v1/pages/p", () => HttpResponse.json({ detail: "Not authenticated" }, { status: 401 })),
  );
  mount(false, [{ id: "board", name: "Desk", device_type: "flagship" } as BoardInstance]);
  fireEvent.click(screen.getByRole("button", { name: "Save page" }));
  await screen.findByRole("link", { name: "Sign in in another tab" });
  release();
  await screen.findByLabelText("Desk character preview");
  expect(screen.getByRole("link", { name: "Sign in in another tab" })).toBeInTheDocument();
});

it("ignores an older preview 401 after a newer preview has authenticated", async () => {
  let release!: () => void;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  let requests = 0;
  server.use(
    http.post("/api/pages/preview/flexible", async () => {
      if (++requests === 1) {
        await pending;
        return HttpResponse.json({ detail: "Not authenticated" }, { status: 401 });
      }
      return HttpResponse.json({
        page_id: "unsaved",
        available: true,
        message: "Newer",
        lines: ["Newer"],
        display_type: "page:flexible",
        raw: {},
      });
    }),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  mount(false, [{ id: "board", name: "Desk", device_type: "flagship" } as BoardInstance], client);
  await waitFor(() => expect(requests).toBe(1));
  fireEvent.change(screen.getByLabelText("Block 1 text"), { target: { value: "Newer draft" } });
  await screen.findByLabelText("Desk character preview");
  release();
  await waitFor(() =>
    expect(
      client
        .getQueryCache()
        .getAll()
        .some((query) => query.state.status === "error"),
    ).toBe(true),
  );
  expect(screen.queryByRole("link", { name: "Sign in in another tab" })).not.toBeInTheDocument();
  expect(screen.getByLabelText("Block 1 text")).toHaveValue("Newer draft");
});

it.each([400, 412])("replaces sign-in guidance with an authenticated Save error %s", async (status) => {
  let writes = 0;
  server.use(
    http.put("/api/v1/pages/p", () =>
      ++writes === 1
        ? HttpResponse.json({ detail: "Not authenticated" }, { status: 401 })
        : HttpResponse.json({ detail: "Save requires a correction" }, { status }),
    ),
  );
  mount();
  fireEvent.change(screen.getByLabelText("Block 1 text"), { target: { value: "Keep this stale draft" } });
  fireEvent.click(screen.getByRole("button", { name: "Save page" }));
  await screen.findByRole("link", { name: "Sign in in another tab" });
  fireEvent.click(screen.getByRole("button", { name: "Save page" }));
  await screen.findByText("Save requires a correction");
  expect(screen.queryByRole("link", { name: "Sign in in another tab" })).not.toBeInTheDocument();
  expect(screen.getByLabelText("Block 1 text")).toHaveValue("Keep this stale draft");
});

it.each([404, 422])("replaces preview sign-in guidance with authenticated target/layout error %s", async (status) => {
  let previews = 0;
  server.use(
    http.post("/api/pages/preview/flexible", () =>
      ++previews === 1
        ? HttpResponse.json({ detail: "Not authenticated" }, { status: 401 })
        : HttpResponse.json({ detail: "Preview target unavailable" }, { status }),
    ),
  );
  mount(false, [{ id: "board", name: "Desk", device_type: "flagship" } as BoardInstance]);
  await screen.findByRole("link", { name: "Sign in in another tab" });
  fireEvent.click(screen.getByRole("button", { name: "Retry preview" }));
  await screen.findByText("Preview target unavailable");
  expect(screen.queryByRole("link", { name: "Sign in in another tab" })).not.toBeInTheDocument();
});
