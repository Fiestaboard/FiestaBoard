/**
 * UX-7-1 (FP-2): Page-tab settings are staged edits, so the leave guard's
 * "Changed" list names a changed Page duration or Transition beside the lines.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { expect, it, vi } from "vitest";

import { PageEditorBridgeProvider } from "@/components/page-editor-bridge-context";
import { PageEditorShell } from "@/components/page-editor-shell";

const current = vi.hoisted(() => ({
  page: { name: "Loaded", template: ["HELLO"], duration_seconds: 60, transition_strategy: null as string | null },
}));

vi.unmock("react-router");
vi.mock("@/components/page-builder", async () => {
  const { forwardRef, useImperativeHandle } = await import("react");
  return {
    PageBuilder: forwardRef(function Builder(_props, ref) {
      useImperativeHandle(ref, () => ({ hasUnsavedChanges: () => true, getCurrentPage: () => current.page }));
      return <p>builder</p>;
    }),
  };
});
vi.mock("@/components/ide/creator-ide", () => ({ default: () => null }));

function renderShell() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(["page", "p1"], {
    id: "p1",
    name: "Loaded",
    template: ["HELLO"],
    duration_seconds: 300,
    transition_strategy: null,
    updated_at: "2026-11-17T15:12:00Z",
  });
  const router = createMemoryRouter(
    [
      { path: "/pages/x", element: <PageEditorShell pageId="p1" onClose={() => {}} onSave={() => {}} /> },
      { path: "*", element: <p>elsewhere</p> },
    ],
    { initialEntries: ["/pages/x"] },
  );
  render(
    <QueryClientProvider client={client}>
      <PageEditorBridgeProvider>
        <RouterProvider router={router} />
      </PageEditorBridgeProvider>
    </QueryClientProvider>,
  );
  return router;
}

it("names a changed Page duration in the discard list", async () => {
  current.page = { ...current.page, duration_seconds: 60, transition_strategy: null };
  const router = renderShell();
  await screen.findByText("builder");
  await act(async () => {
    void router.navigate("/elsewhere");
  });
  const list = await screen.findByTestId("discard-changed-lines");
  expect(list).toHaveTextContent("Page duration");
  expect(list).not.toHaveTextContent("Transition");
});

it("names a changed Transition and no lines when only the settings changed", async () => {
  current.page = { ...current.page, duration_seconds: 300, transition_strategy: "row" };
  const router = renderShell();
  await screen.findByText("builder");
  await act(async () => {
    void router.navigate("/elsewhere");
  });
  const list = await screen.findByTestId("discard-changed-lines");
  expect(list).toHaveTextContent("Transition");
  expect(list).not.toHaveTextContent("Page duration");
});
