import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { beforeEach, expect, it, vi } from "vitest";

import { PageEditorBridgeProvider, usePageEditorBridge } from "@/components/page-editor-bridge-context";
import { PageEditorShell } from "@/components/page-editor-shell";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

vi.unmock("react-router");

beforeEach(() => localStorage.clear());

async function setup() {
  let bridge!: ReturnType<typeof usePageEditorBridge>;
  function Editor() {
    bridge = usePageEditorBridge();
    return <PageEditorShell skipDraft onClose={vi.fn()} onSave={vi.fn()} />;
  }
  const router = createMemoryRouter(
    [
      { path: "/pages/new", element: <Editor /> },
      { path: "/saved", element: <h1>Saved page destination</h1> },
    ],
    { initialEntries: ["/pages/new"] },
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
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
  await screen.findByLabelText("Page Name");
  await waitFor(() => expect(bridge.staging.isMounted()).toBe(true));
  return { router, bridge: () => bridge, user: userEvent.setup() };
}

it("allows create-page settle to discard clean staging and navigate in the same tick", async () => {
  const { bridge, router } = await setup();
  await waitFor(() => expect(bridge().staging.hasUnsavedChanges()).toBe(false));
  act(() => {
    bridge().staging.begin();
    bridge().staging.setName("AI created page");
    bridge().staging.setLine(0, "AI CONTENT");
  });
  await waitFor(() => expect(bridge().staging.hasUnsavedChanges()).toBe(true));
  act(() => {
    bridge().staging.discard();
    void router.navigate("/saved");
  });
  expect(await screen.findByRole("heading", { name: "Saved page destination" })).toBeInTheDocument();
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
});

it("restores an original dirty draft and keeps same-tick navigation guarded", async () => {
  const { bridge, router, user } = await setup();
  fireEvent.change(screen.getByLabelText("Page Name"), { target: { value: "My original draft" } });
  await waitFor(() => expect(bridge().staging.hasUnsavedChanges()).toBe(true));
  const original = bridge().getEditorSnapshot();
  act(() => {
    bridge().staging.begin();
    bridge().staging.setName("AI staged replacement");
    bridge().staging.setLine(0, "AI CONTENT");
  });
  await screen.findByDisplayValue("AI staged replacement");
  act(() => {
    bridge().staging.discard();
    // A duplicate completion must not clear the user's original dirty flag.
    bridge().staging.discard();
    void router.navigate("/saved");
  });
  expect(await screen.findByRole("alertdialog", { name: /^Discard changes( to .*)?\?$/ })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Keep editing" }));
  expect(screen.getByDisplayValue("My original draft")).toBeInTheDocument();
  expect(bridge().getEditorSnapshot()).toEqual(original);
  expect(bridge().staging.hasUnsavedChanges()).toBe(true);
  expect(router.state.location.pathname).toBe("/pages/new");
});
