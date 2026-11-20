import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { createMemoryRouter, RouterProvider } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CollectionsLayout from "../../app/routes/collections";
import CollectionsIndex from "../../app/routes/collections._index";
import EditCollection from "../../app/routes/collections.$collectionId";
import NewCollection from "../../app/routes/collections.new";
import { server } from "./mocks/server";
vi.unmock("react-router");
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
const collection = {
  id: "collection:rotation",
  name: "Rotation",
  page_ids: ["p1"],
  selection_mode: "time",
  time: { interval_seconds: 5400 },
  variable: null,
  random: null,
  created_at: "2026-01-01",
};
function renderRoute(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const router = createMemoryRouter(
    [
      {
        path: "/collections",
        Component: CollectionsLayout,
        children: [
          { index: true, Component: CollectionsIndex },
          { path: "new", Component: NewCollection },
          { path: ":collectionId", Component: EditCollection },
        ],
      },
    ],
    { initialEntries: ["/collections", path], initialIndex: 1 },
  );
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return Object.assign(router, { queryClient: client });
}
describe("Collection routes", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    server.use(
      http.post("/api/collections/:id/dry-run", () =>
        HttpResponse.json({ page_id: null, rules: [], at: "2026-01-01T00:00:00Z" }),
      ),
      http.get("/api/v1/collections", () => HttpResponse.json({ collections: [collection] })),
      http.get("/api/v1/pages", () =>
        HttpResponse.json({ pages: [{ id: "p1", name: "First", device_type: "flagship" }] }),
      ),
      http.post("/api/pages/preview/batch", () => HttpResponse.json({ previews: {} })),
    );
  });
  it("saves an existing custom duration from its deep link and returns to the library", async () => {
    const user = userEvent.setup();
    let body: unknown;
    server.use(
      http.put("/api/v1/collections/collection:rotation", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(collection);
      }),
    );
    const router = renderRoute("/collections/collection%3Arotation");
    expect(await screen.findByLabelText("Custom duration")).toHaveValue(90);
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/collections"));
    expect(body).toEqual(expect.objectContaining({ time: { interval_seconds: 5400 }, page_ids: ["p1"] }));
  });
  it("creates from a full-page route", async () => {
    const user = userEvent.setup();
    let body: unknown;
    server.use(
      http.post("/api/v1/collections", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(collection, { status: 201 });
      }),
    );
    const router = renderRoute("/collections/new");
    await user.type(await screen.findByLabelText("Collection name"), "New rotation");
    await user.click(screen.getByRole("button", { name: "Add page" }));
    await user.click(await screen.findByRole("menuitem", { name: /^First/ }));
    await user.click(screen.getByRole("button", { name: "Create Collection" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/collections"));
    expect(body).toEqual(expect.objectContaining({ name: "New rotation", page_ids: ["p1"] }));
  });
  it("keeps typed edits on a failed save", async () => {
    const user = userEvent.setup();
    server.use(
      http.put("/api/v1/collections/collection:rotation", () =>
        HttpResponse.json({ detail: "Save failed" }, { status: 500 }),
      ),
    );
    const router = renderRoute("/collections/collection%3Arotation");
    const name = await screen.findByLabelText("Collection name");
    await user.clear(name);
    await user.type(name, "Keep this draft");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Save failed");
    expect(name).toHaveValue("Keep this draft");
    expect(router.state.location.pathname).toBe("/collections/collection%3Arotation");
  });
  it("keeps the original revision and dirty draft when a background refresh precedes a conflict", async () => {
    const user = userEvent.setup();
    let body: unknown;
    server.use(
      http.get("/api/v1/collections", () =>
        HttpResponse.json({
          collections: [
            {
              ...collection,
              revision: "original",
              edit_protocol: "collection-revision-v1",
            },
          ],
        }),
      ),
      http.put("/api/v1/collections/collection:rotation", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ detail: "Collection changed. Reload before saving." }, { status: 412 });
      }),
    );
    const router = renderRoute("/collections/collection%3Arotation");
    const name = await screen.findByLabelText("Collection name");
    await user.clear(name);
    await user.type(name, "My draft");
    await act(async () => {
      router.queryClient.setQueryData(["collections"], {
        collections: [
          {
            ...collection,
            name: "Other writer",
            revision: "newer",
            edit_protocol: "collection-revision-v1",
          },
        ],
      });
    });
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Collection changed");
    expect(body).toEqual(expect.objectContaining({ name: "My draft", expected_revision: "original" }));
    expect(name).toHaveValue("My draft");
  });
  it("guards history back and preserves edits when Keep editing is chosen", async () => {
    const user = userEvent.setup();
    const router = renderRoute("/collections/collection%3Arotation");
    await user.type(await screen.findByLabelText("Collection name"), " changed");
    await act(async () => {
      await router.navigate(-1);
    });
    expect(await screen.findByRole("alertdialog", { name: "Discard unsaved changes?" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Keep editing" }));
    expect(screen.getByLabelText("Collection name")).toHaveValue("Rotation changed");
    await act(async () => {
      await router.navigate(-1);
    });
    await user.click(await screen.findByRole("button", { name: "Discard and leave" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/collections"));
  });
  it("cancels deletion without deleting, then confirms the collection's own ID", async () => {
    const user = userEvent.setup();
    const deleted: string[] = [];
    server.use(
      http.delete("/api/v1/collections/:id", ({ params }) => {
        deleted.push(String(params.id));
        return HttpResponse.json({ id: params.id });
      }),
    );
    const router = renderRoute("/collections/collection%3Arotation");
    await user.click(await screen.findByRole("button", { name: "Delete…" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
    expect(deleted).toEqual([]);
    expect(screen.getByLabelText("Collection name")).toHaveValue("Rotation");
    await user.click(screen.getByRole("button", { name: "Delete…" }));
    const dialog = screen.getByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/collections"));
    expect(deleted).toEqual(["collection:rotation"]);
  });
  it("tests the saved Collection at a chosen instant without writing it", async () => {
    const user = userEvent.setup();
    const requests: unknown[] = [];
    server.use(
      http.get("/api/v1/collections", () =>
        HttpResponse.json({
          collections: [
            {
              ...collection,
              selection_mode: "variable",
              variable: { rules: [], default_page_id: "p1", poll_seconds: 10 },
            },
          ],
        }),
      ),
      http.post("/api/collections/:id/dry-run", async ({ request }) => {
        requests.push(await request.json());
        return HttpResponse.json({ page_id: null, rules: [], at: "2026-01-01T00:00:00Z" });
      }),
    );
    renderRoute("/collections/collection%3Arotation");
    await user.click(await screen.findByRole("button", { name: "Test at a time…" }));
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Test at a time…"), { target: { value: "2026-01-01T09:30" } });
    await user.click(within(dialog).getByRole("button", { name: "Preview" }));
    await waitFor(() => expect(requests).toContainEqual({ at: new Date("2026-01-01T09:30").toISOString() }));
  });
});
