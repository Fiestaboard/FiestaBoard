import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, it, vi } from "vitest";

import { PageEditorShell } from "@/components/page-editor-shell";

import { server } from "./mocks/server";

vi.mock("react-router", async () => ({
  ...(await vi.importActual("react-router")),
  useBlocker: () => ({ state: "unblocked" }),
}));
vi.mock("@/components/page-editor-bridge-context", () => ({
  usePageEditorBridge: () => ({ register: vi.fn(), unregister: vi.fn() }),
}));
vi.mock("@/components/page-builder", () => ({ PageBuilder: () => <p>Legacy grid editor</p> }));

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <PageEditorShell pageId="p" onClose={vi.fn()} onSave={vi.fn()} />
    </QueryClientProvider>,
  );
}

it("routes a geometry-free flexible document to block editing", async () => {
  server.use(
    http.get("/api/v1/pages/p", () =>
      HttpResponse.json({
        id: "p",
        name: "Flexible",
        type: "flexible",
        blocks: [{ id: "text", kind: "text", text: "Hi" }],
        revision: "one",
      }),
    ),
  );
  mount();
  expect(await screen.findByLabelText("Block 1 text")).toHaveValue("Hi");
  expect(screen.queryByText("Legacy grid editor")).not.toBeInTheDocument();
});

it("retains the legacy grid editor for exact-grid documents", async () => {
  server.use(
    http.get("/api/v1/pages/p", () =>
      HttpResponse.json({ id: "p", name: "Grid", type: "template", device_type: "flagship", template: ["Hi"] }),
    ),
  );
  mount();
  expect(await screen.findByText("Legacy grid editor")).toBeInTheDocument();
});

it("does not let an older editor rewrite a future flexible document protocol", async () => {
  server.use(
    http.get("/api/v1/pages/p", () =>
      HttpResponse.json({
        id: "p",
        name: "Future",
        type: "flexible",
        document_protocol: "page-document-v99",
        blocks: [],
      }),
    ),
  );
  mount();
  expect(await screen.findByRole("alert")).toHaveTextContent("not editable");
  expect(screen.queryByRole("button", { name: "Save page" })).not.toBeInTheDocument();
});
