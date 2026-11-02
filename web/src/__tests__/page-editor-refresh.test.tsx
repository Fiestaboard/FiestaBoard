import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { createMemoryRouter, Link, RouterProvider, useNavigate, useParams } from "react-router";
import { expect, it, vi } from "vitest";

import { PageEditorBridgeProvider } from "@/components/page-editor-bridge-context";
import { PageEditorShell } from "@/components/page-editor-shell";

import { server } from "./mocks/server";

vi.unmock("react-router");

const original = {
  id: "p",
  name: "Morning",
  type: "flexible",
  document_protocol: "page-document-v2",
  revision: "original-revision",
  duration_seconds: 30,
  blocks: [{ id: "title", kind: "text", text: "Hello" }],
};

function setup() {
  server.use(
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
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  function EditorRoute() {
    const { id } = useParams();
    const navigate = useNavigate();
    return (
      <>
        <Link to="/pages">Pages</Link>
        <Link to="/edit/q">Another page</Link>
        <PageEditorShell pageId={id} onClose={() => navigate("/pages")} onSave={() => navigate("/pages")} />
      </>
    );
  }
  const router = createMemoryRouter(
    [
      { path: "/edit/:id", element: <EditorRoute /> },
      { path: "/pages", element: <h1>Pages destination</h1> },
    ],
    { initialEntries: ["/edit/p"] },
  );
  render(
    <QueryClientProvider client={client}>
      <PageEditorBridgeProvider>
        <RouterProvider router={router} />
      </PageEditorBridgeProvider>
    </QueryClientProvider>,
  );
  return { client, user: userEvent.setup() };
}

it("keeps initial page read errors blocking", async () => {
  server.use(http.get("/api/v1/pages/p", () => HttpResponse.json({ detail: "Page unavailable" }, { status: 500 })));
  setup();
  expect(await screen.findByRole("alert")).toHaveTextContent("Page unavailable");
  expect(screen.queryByRole("button", { name: "Save page" })).not.toBeInTheDocument();
});

it.each([403, 404, 500])("retains dirty text and navigation protection after a background HTTP %s", async (status) => {
  server.use(http.get("/api/v1/pages/p", () => HttpResponse.json(original)));
  const { client, user } = setup();
  fireEvent.change(await screen.findByLabelText("Block 1 text"), { target: { value: "My unfinished draft" } });
  server.use(http.get("/api/v1/pages/p", () => HttpResponse.json({ detail: "Page unavailable" }, { status })));
  await act(() => client.refetchQueries({ queryKey: ["page", "p"] }));
  expect(screen.queryByLabelText("Block 1 text")).toHaveValue("My unfinished draft");
  await user.click(screen.getByRole("link", { name: "Pages" }));
  expect(await screen.findByRole("alertdialog", { name: "Discard unsaved changes?" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Keep editing" }));
  expect(screen.getByLabelText("Block 1 text")).toHaveValue("My unfinished draft");
});

it.each([
  { type: "template", template: ["Changed format"] },
  { type: "flexible", document_protocol: "page-document-v99" },
])("retains the draft but blocks saving after an incompatible successful refresh: %j", async (changed) => {
  server.use(http.get("/api/v1/pages/p", () => HttpResponse.json(original)));
  const { client } = setup();
  fireEvent.change(await screen.findByLabelText("Block 1 text"), { target: { value: "My draft" } });
  server.use(
    http.get("/api/v1/pages/p", () => HttpResponse.json({ ...original, ...changed, revision: "new-revision" })),
  );
  await act(() => client.refetchQueries({ queryKey: ["page", "p"] }));
  expect(screen.queryByLabelText("Block 1 text")).toHaveValue("My draft");
  expect(screen.getByRole("alert")).toHaveTextContent("format");
  expect(screen.getByRole("button", { name: "Save page" })).toBeDisabled();
});

it("does not reuse a previous page's draft after discarding and navigating to another ID", async () => {
  server.use(
    http.get("/api/v1/pages/p", () => HttpResponse.json(original)),
    http.get("/api/v1/pages/q", () => HttpResponse.json({ detail: "Other page unavailable" }, { status: 404 })),
  );
  const { user } = setup();
  fireEvent.change(await screen.findByLabelText("Block 1 text"), { target: { value: "First page draft" } });
  await user.click(screen.getByRole("link", { name: "Another page" }));
  await user.click(await screen.findByRole("button", { name: "Discard and leave" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Other page unavailable");
  expect(screen.queryByLabelText("Block 1 text")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Save page" })).not.toBeInTheDocument();
});

it("retains incomplete Canvas JSON after a failed read and a later successful refresh", async () => {
  const drawing = {
    ...original,
    blocks: [{ id: "drawing", kind: "canvas", canvas: { content: { size: [8, 8], shapes: [] } } }],
  };
  server.use(http.get("/api/v1/pages/p", () => HttpResponse.json(drawing)));
  const { client, user } = setup();
  await user.click(await screen.findByRole("tab", { name: "Shapes" }));
  await user.click(screen.getByRole("switch", { name: "Edit as JSON" }));
  fireEvent.change(screen.getByLabelText("Shapes JSON"), { target: { value: "[{" } });
  server.use(http.get("/api/v1/pages/p", () => HttpResponse.json({ detail: "Temporary failure" }, { status: 500 })));
  await act(() => client.refetchQueries({ queryKey: ["page", "p"] }));
  expect(screen.queryByLabelText("Shapes JSON")).toHaveValue("[{");
  expect(screen.getByRole("button", { name: "Save page" })).toBeDisabled();
  server.use(http.get("/api/v1/pages/p", () => HttpResponse.json({ ...drawing, revision: "newer-revision" })));
  await act(() => client.refetchQueries({ queryKey: ["page", "p"] }));
  expect(screen.getByLabelText("Shapes JSON")).toHaveValue("[{");
  expect(screen.getByRole("button", { name: "Save page" })).toBeDisabled();
});

it("retries only the read and retains the original save revision after refresh recovery", async () => {
  let writes = 0;
  let submitted: Record<string, unknown> | undefined;
  server.use(
    http.get("/api/v1/pages/p", () => HttpResponse.json(original)),
    http.put("/api/v1/pages/p", async ({ request }) => {
      writes += 1;
      submitted = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ detail: "Page changed in another editor" }, { status: 412 });
    }),
  );
  const { client, user } = setup();
  fireEvent.change(await screen.findByLabelText("Block 1 text"), { target: { value: "My draft" } });
  server.use(http.get("/api/v1/pages/p", () => HttpResponse.json({ detail: "Temporary failure" }, { status: 500 })));
  await act(() => client.refetchQueries({ queryKey: ["page", "p"] }));
  const retry = await screen.findByRole("button", { name: "Retry refresh" });
  await user.click(retry);
  await waitFor(() => expect(retry).toBeEnabled());
  expect(screen.getByRole("alert")).toHaveTextContent("draft");
  server.use(http.get("/api/v1/pages/p", () => HttpResponse.json({ ...original, revision: "newer-revision" })));
  await user.click(retry);
  await waitFor(() => expect(screen.queryByRole("button", { name: "Retry refresh" })).not.toBeInTheDocument());
  expect(writes).toBe(0);
  expect(screen.getByLabelText("Block 1 text")).toHaveValue("My draft");
  await user.click(screen.getByRole("button", { name: "Save page" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Page changed in another editor");
  expect(submitted).toMatchObject({ expected_revision: "original-revision", blocks: [{ text: "My draft" }] });
  expect(writes).toBe(1);
  expect(screen.getByLabelText("Block 1 text")).toHaveValue("My draft");
});
