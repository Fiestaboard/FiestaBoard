import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, expect, it, vi } from "vitest";

import { PageEditorBridgeProvider } from "@/components/page-editor-bridge-context";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";
import type { Page, PageUpdate } from "@/lib/api";

import { PagesSection } from "../../app/routes/pages";
import EditPage from "../../app/routes/pages.edit._index";
import { server } from "./mocks/server";

vi.unmock("react-router");
afterEach(() => window.history.replaceState({}, "", "/"));

function setup() {
  const pages: Page[] = ["first", "second"].map((id) => ({
    id,
    name: id === "first" ? "First page" : "Second page",
    type: "flexible",
    document_protocol: "page-document-v2",
    revision: `${id}-revision`,
    blocks: [
      { id: "title", kind: "text", text: id === "first" ? "FIRST" : "SECOND" },
      { id: "drawing", kind: "canvas", canvas: { content: { size: [8, 8], shapes: [] } } },
    ],
    duration_seconds: 30,
    created_at: "2026-01-01T00:00:00Z",
  }));
  const writes: { id: string; body: PageUpdate }[] = [];
  server.use(
    http.get("/api/v1/pages", () => HttpResponse.json({ pages, total: pages.length })),
    http.get("/api/v1/pages/:id", ({ params }) => HttpResponse.json(pages.find((page) => page.id === params.id))),
    http.post("/api/pages/preview/flexible", () =>
      HttpResponse.json({
        page_id: "unsaved",
        message: "PREVIEW",
        lines: ["PREVIEW"],
        display_type: "page:flexible",
        raw: {},
        layout_issues: [],
      }),
    ),
    http.put("/api/v1/pages/:id", async ({ params, request }) => {
      const body = (await request.json()) as PageUpdate;
      writes.push({ id: String(params.id), body });
      return HttpResponse.json({
        page: { ...pages.find((page) => page.id === params.id), ...body, revision: "saved-revision" },
        incompatible_references: [],
      });
    }),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const router = createMemoryRouter(
    [
      { path: "/pages", element: <h1>Pages destination</h1> },
      {
        path: "/pages/edit",
        element: (
          <PagesSection>
            <EditPage />
          </PagesSection>
        ),
      },
    ],
    { initialEntries: ["/pages/edit?id=first"] },
  );
  render(
    <QueryClientProvider client={client}>
      <ConfigOverridesProvider>
        <ThemeProvider attribute="class" defaultTheme="light">
          <PageEditorBridgeProvider>
            <RouterProvider router={router} />
          </PageEditorBridgeProvider>
        </ThemeProvider>
      </ConfigOverridesProvider>
    </QueryClientProvider>,
  );
  return { client, router, writes, user: userEvent.setup() };
}

it("keeps flexible headers, documents, revisions and save targets aligned through query history", async () => {
  const { router, user, writes } = setup();
  expect(await screen.findByLabelText("Block 1 text")).toHaveValue("FIRST");
  await act(() => router.navigate("/pages/edit?id=second"));
  expect(await screen.findByRole("heading", { name: "Second page" })).toBeInTheDocument();
  expect(await screen.findByLabelText("Block 1 text")).toHaveValue("SECOND");
  await act(() => router.navigate(-1));
  expect(await screen.findByLabelText("Block 1 text")).toHaveValue("FIRST");
  await act(() => router.navigate(1));
  expect(await screen.findByLabelText("Block 1 text")).toHaveValue("SECOND");
  fireEvent.change(screen.getByLabelText("Block 1 text"), { target: { value: "SECOND EDIT" } });
  await user.click(screen.getByRole("button", { name: "Save page" }));
  expect(await screen.findByRole("heading", { name: "Pages destination" })).toBeInTheDocument();
  expect(writes).toHaveLength(1);
  expect(writes[0]).toMatchObject({
    id: "second",
    body: {
      name: "Second page",
      expected_revision: "second-revision",
      blocks: [{ id: "title", text: "SECOND EDIT" }, { id: "drawing" }],
    },
  });
});

it("preserves incomplete JSON across a failed refresh and same-ID query changes before cancel or discard", async () => {
  const { client, router, user, writes } = setup();
  await user.click(await screen.findByRole("tab", { name: "Shapes" }));
  await user.click(screen.getByRole("switch", { name: "Edit as JSON" }));
  fireEvent.change(screen.getByLabelText("Shapes JSON"), { target: { value: "[{" } });
  server.use(
    http.get("/api/v1/pages/first", () => HttpResponse.json({ detail: "Temporary failure" }, { status: 500 })),
  );
  await act(() => client.refetchQueries({ queryKey: ["page", "first"] }));
  await act(() => router.navigate("/pages/edit?id=first&view=preview#canvas"));
  expect(router.state.location.hash).toBe("#canvas");
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  expect(screen.getByLabelText("Shapes JSON")).toHaveValue("[{");
  expect(screen.getByRole("button", { name: "Save page" })).toBeDisabled();
  await act(() => router.navigate("/pages/edit?id=second"));
  await user.click(await screen.findByRole("button", { name: "Keep editing" }));
  expect(screen.getByLabelText("Shapes JSON")).toHaveValue("[{");
  expect(router.state.location.search).toBe("?id=first&view=preview");
  await act(() => router.navigate("/pages/edit?id=second"));
  await user.click(await screen.findByRole("button", { name: "Discard and leave" }));
  expect(await screen.findByRole("heading", { name: "Second page" })).toBeInTheDocument();
  expect(await screen.findByLabelText("Block 1 text")).toHaveValue("SECOND");
  expect(screen.getByRole("button", { name: "Save page" })).toBeEnabled();
  expect(screen.queryByDisplayValue("[{")).not.toBeInTheDocument();
  expect(writes).toEqual([]);
});

it("cannot save the previous flexible draft after discarding to a page that fails to load", async () => {
  const { router, user, writes } = setup();
  fireEvent.change(await screen.findByLabelText("Block 1 text"), { target: { value: "FIRST DRAFT" } });
  server.use(
    http.get("/api/v1/pages/second", () => HttpResponse.json({ detail: "Second page unavailable" }, { status: 500 })),
  );
  await act(() => router.navigate("/pages/edit?id=second"));
  await user.click(await screen.findByRole("button", { name: "Discard and leave" }));
  expect(await screen.findByRole("heading", { name: "Second page" })).toBeInTheDocument();
  expect(await screen.findByRole("alert")).toHaveTextContent("Second page unavailable");
  expect(screen.queryByLabelText("Block 1 text")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Save page" })).not.toBeInTheDocument();
  expect(writes).toEqual([]);
});

it("confirms discarding the flexible draft before leaving a route with no page ID", async () => {
  const { router, user, writes } = setup();
  fireEvent.change(await screen.findByLabelText("Block 1 text"), { target: { value: "FIRST DRAFT" } });
  await act(() => router.navigate("/pages/edit"));
  await user.click(await screen.findByRole("button", { name: "Keep editing" }));
  expect(screen.getByLabelText("Block 1 text")).toHaveValue("FIRST DRAFT");
  await act(() => router.navigate("/pages/edit"));
  await user.click(await screen.findByRole("button", { name: "Discard and leave" }));
  expect(await screen.findByRole("heading", { name: "Pages destination" })).toBeInTheDocument();
  expect(writes).toEqual([]);
});
