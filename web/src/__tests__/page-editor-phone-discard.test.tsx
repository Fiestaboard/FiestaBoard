import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { beforeEach, expect, it, vi } from "vitest";

import { PageEditorBridgeProvider } from "@/components/page-editor-bridge-context";
import { PageEditorShell } from "@/components/page-editor-shell";

vi.unmock("react-router");
vi.mock("@/components/page-builder", async () => {
  const { forwardRef, useImperativeHandle, useState } = await import("react");
  return {
    PageBuilder: forwardRef(function DraftEditor(_props, ref) {
      const [name, setName] = useState("Kitchen draft");
      useImperativeHandle(ref, () => ({ hasUnsavedChanges: () => true, getCurrentPage: () => ({ name }) }));
      return <input aria-label="Page name" value={name} onChange={(event) => setName(event.target.value)} />;
    }),
  };
});

function media(phone: boolean) {
  vi.spyOn(window, "matchMedia").mockImplementation((query) => ({
    matches: phone && query === "(max-width: 639px)",
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}
function setup() {
  const router = createMemoryRouter(
    [
      { path: "/pages", element: <h1>Pages destination</h1> },
      { path: "/pages/new", element: <PageEditorShell onClose={() => {}} onSave={() => {}} /> },
    ],
    { initialEntries: ["/pages", "/pages/new"], initialIndex: 1 },
  );
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <PageEditorBridgeProvider>
        <RouterProvider router={router} />
      </PageEditorBridgeProvider>
    </QueryClientProvider>,
  );
  return router;
}
beforeEach(() => media(true));

// BB-B-22 (Figma 316:91801): "Discard changes to <page>?", the saved version
// stays on the board, Keep editing / Discard changes, and the title clear of X.
it("uses a modal bottom sheet with Keep editing before full-width Discard on phones", async () => {
  const router = setup();
  await act(async () => {
    await router.navigate(-1);
  });
  const dialog = await screen.findByRole("alertdialog", { name: "Discard changes to Kitchen draft?" });
  expect(within(dialog).getByText(/keep showing the saved version/)).toBeInTheDocument();
  expect(dialog.querySelector('[data-slot="sheet-header"]')).toHaveClass("pr-12");
  expect(dialog).toHaveAttribute("data-slot", "sheet-content");
  expect(dialog).toHaveAttribute("data-side", "bottom");
  expect(document.querySelector('[data-slot="sheet-overlay"]')).toBeInTheDocument();
  const buttons = within(dialog)
    .getAllByRole("button")
    .filter((button) => /Keep editing|Discard changes/.test(button.textContent ?? ""));
  expect(buttons.map((button) => button.textContent)).toEqual(["Keep editing", "Discard changes"]);
  const footer = dialog.querySelector('[data-slot="sheet-footer"]');
  expect(footer).toHaveClass("flex-col");
  expect(footer).not.toHaveClass("flex-col-reverse");
  for (const button of buttons) expect(button).toHaveClass("w-full");
  await waitFor(() => expect(buttons[0]).toHaveFocus());
  expect(buttons[1]).toHaveAttribute("data-variant", "destructive");
});

it("preserves the draft and route when Keep editing or Escape cancels phone Back", async () => {
  const user = userEvent.setup();
  const router = setup();
  await user.type(screen.getByLabelText("Page name"), " edited");
  await act(async () => {
    await router.navigate(-1);
  });
  await user.click(await screen.findByRole("button", { name: /^Keep editing$/ }));
  await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
  expect(router.state.location.pathname).toBe("/pages/new");
  expect(screen.getByLabelText("Page name")).toHaveValue("Kitchen draft edited");
  await act(async () => {
    await router.navigate(-1);
  });
  await screen.findByRole("alertdialog");
  await user.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
  expect(router.state.location.pathname).toBe("/pages/new");
  expect(screen.getByLabelText("Page name")).toHaveValue("Kitchen draft edited");
});

it("proceeds with history Back when the phone Discard action is accepted", async () => {
  const user = userEvent.setup();
  const router = setup();
  await act(async () => {
    await router.navigate(-1);
  });
  await user.click(await screen.findByRole("button", { name: /^Discard changes$/ }));
  expect(await screen.findByRole("heading", { name: "Pages destination" })).toBeInTheDocument();
  expect(router.state.location.pathname).toBe("/pages");
});

it("keeps the desktop alert dialog and initially focuses Keep editing", async () => {
  media(false);
  const router = setup();
  await act(async () => {
    await router.navigate(-1);
  });
  const dialog = await screen.findByRole("alertdialog", { name: "Discard unsaved changes?" });
  expect(dialog).not.toHaveAttribute("data-slot", "sheet-content");
  await waitFor(() => expect(within(dialog).getByRole("button", { name: /^Keep editing$/ })).toHaveFocus());
});
