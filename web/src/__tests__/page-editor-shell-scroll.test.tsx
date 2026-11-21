/**
 * PageEditorShell around the builder (BB-B-16, -27, -29): it never fetches the
 * page itself (the builder owns that request, so a deleted page is not asked
 * for again), mounts the Creator IDE only around a page that loaded, and only
 * the new-page editor (no IDE below it) reserves room for the touch toolbar.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, expect, it, vi } from "vitest";

import { PageEditorBridgeProvider } from "@/components/page-editor-bridge-context";
import { PageEditorShell } from "@/components/page-editor-shell";

import { server } from "./mocks/server";

vi.unmock("react-router");
vi.mock("@/components/page-builder", async () => {
  const { forwardRef } = await import("react");
  return {
    PageBuilder: forwardRef(function Builder() {
      return <p>builder</p>;
    }),
  };
});
vi.mock("@/components/ide/creator-ide", () => ({ default: () => <p>creator ide</p> }));

const requests: string[] = [];
const listener = ({ request }: { request: Request }) => {
  requests.push(new URL(request.url).pathname);
};
afterEach(() => {
  server.events.removeListener("request:start", listener);
  requests.length = 0;
});

function renderShell(pageId?: string, seed?: unknown) {
  server.events.on("request:start", listener);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  if (seed) client.setQueryData(["page", pageId], seed);
  const router = createMemoryRouter(
    [{ path: "*", element: <PageEditorShell pageId={pageId} onClose={() => {}} onSave={() => {}} /> }],
    { initialEntries: ["/pages/x"] },
  );
  return render(
    <QueryClientProvider client={client}>
      <PageEditorBridgeProvider>
        <RouterProvider router={router} />
      </PageEditorBridgeProvider>
    </QueryClientProvider>,
  );
}

it("never asks for the page itself, and mounts no IDE before the page loaded", async () => {
  renderShell("p1");
  await screen.findByText("builder");
  await new Promise((resolve) => setTimeout(resolve, 100));
  expect(requests.filter((path) => path.endsWith("/pages/p1"))).toEqual([]);
  expect(screen.queryByText("creator ide")).not.toBeInTheDocument();
});

it("mounts the IDE around a loaded page, with no extra toolbar room of its own", async () => {
  const { container } = renderShell("p1", { id: "p1", name: "Loaded" });
  expect(await screen.findByText("creator ide")).toBeInTheDocument();
  expect(container.querySelector(".overflow-y-auto")).not.toHaveClass("max-md:pb-20");
});

it("reserves toolbar room at the end of a new page's editor", async () => {
  const { container } = renderShell();
  await screen.findByText("builder");
  expect(container.querySelector(".overflow-y-auto")).toHaveClass("max-md:pb-20");
});
