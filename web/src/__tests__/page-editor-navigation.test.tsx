import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { createMemoryRouter, Link, RouterProvider } from "react-router";
import { afterEach, beforeAll, beforeEach, expect, it, vi } from "vitest";

import { PageEditorBridgeProvider } from "@/components/page-editor-bridge-context";
import { EditPageClient } from "@/components/pages/edit-page-client";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

import LegacyEditPage from "../../app/routes/pages.edit._index";
import { server } from "./mocks/server";

vi.mock("@/components/preview-target-popover", () => import("./mocks/preview-target-popover-inline"));

vi.unmock("react-router");

beforeEach(() => {
  vi.spyOn(window, "scrollBy").mockImplementation(() => {});
});

beforeAll(async () => {
  await import("@/components/tiptap-template-editor/TipTapTemplateEditor");
});

afterEach(() => {
  window.history.replaceState({}, "", "/");
});

function setup(initialPath = "/pages/edit/page-1") {
  const router = createMemoryRouter(
    [
      { path: "/pages", element: <h1>Pages destination</h1> },
      { path: "/settings", element: <h1>Settings destination</h1> },
      {
        path: "/pages/edit",
        element: (
          <>
            <Link to="/pages">Pages breadcrumb</Link>
            <LegacyEditPage />
          </>
        ),
      },
      {
        path: "/pages/edit/:id",
        element: (
          <>
            <Link to="/pages">Pages breadcrumb</Link>
            <Link to="/settings">Settings sidebar</Link>
            <EditPageClient pageId="page-1" />
          </>
        ),
      },
    ],
    { initialEntries: ["/pages", initialPath], initialIndex: 1 },
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
  return { router, user: userEvent.setup() };
}

it.each(["Pages breadcrumb", "Settings sidebar"])(
  "keeps a dirty name when cancelling %s, then allows discard",
  async (link) => {
    const { user } = setup();
    const name = await screen.findByDisplayValue("Weather Page");
    await user.clear(name);
    await user.type(name, "Unsaved name");
    await user.click(screen.getByRole("link", { name: link }));
    const guard = await screen.findByRole("alertdialog", { name: /^Discard changes( to .*)?\?$/ });
    expect(guard).toHaveTextContent("Displays keep showing the saved version.");
    await user.click(screen.getByRole("button", { name: "Keep editing" }));
    expect(screen.getByDisplayValue("Unsaved name")).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: link }));
    await user.click(await screen.findByRole("button", { name: "Discard changes" }));
    expect(await screen.findByRole("heading", { name: /destination/ })).toBeInTheDocument();
  },
);

it("blocks history back for unsaved edits", async () => {
  const { router, user } = setup();
  await user.type(await screen.findByDisplayValue("Weather Page"), " changed");
  await act(async () => {
    await router.navigate(-1);
  });
  expect(await screen.findByRole("alertdialog")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Discard changes" }));
  expect(await screen.findByRole("heading", { name: "Pages destination" })).toBeInTheDocument();
});

it("leaves an unchanged page without prompting", async () => {
  const { user } = setup();
  await screen.findByDisplayValue("Weather Page");
  await user.click(screen.getByRole("link", { name: "Pages breadcrumb" }));
  expect(await screen.findByRole("heading", { name: "Pages destination" })).toBeInTheDocument();
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
});

it("stays after Save, then leaves without prompting", async () => {
  const { user } = setup();
  await user.type(await screen.findByDisplayValue("Weather Page"), " changed");
  await user.click(screen.getByRole("button", { name: "Save Page" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Save Page" })).toBeEnabled());
  expect(screen.getByDisplayValue("Weather Page changed")).toBeInTheDocument();
  await user.click(screen.getByRole("link", { name: "Pages breadcrumb" }));
  expect(await screen.findByRole("heading", { name: "Pages destination" })).toBeInTheDocument();
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
});

it("keeps content edits after cancelling navigation", async () => {
  const { user } = setup();
  await screen.findByDisplayValue("Weather Page");
  const editor = await waitFor(() => {
    const element = document.querySelector('[contenteditable="true"]');
    expect(element).toBeTruthy();
    return element as HTMLElement;
  });
  await user.click(editor);
  await user.keyboard("NEW TEXT");
  expect(editor).toHaveTextContent("NEW TEXT");
  await user.click(screen.getByRole("link", { name: "Pages breadcrumb" }));
  await user.click(await screen.findByRole("button", { name: "Keep editing" }));
  expect(editor).toHaveTextContent("NEW TEXT");
});

it("allows query and hash updates in the same editor without losing edits", async () => {
  const { router, user } = setup();
  await user.type(await screen.findByDisplayValue("Weather Page"), " changed");
  await act(async () => {
    await router.navigate("/pages/edit/page-1?view=preview#canvas");
  });
  expect(router.state.location.search).toBe("?view=preview");
  expect(screen.getByDisplayValue("Weather Page changed")).toBeInTheDocument();
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
});

it("still warns after a failed save", async () => {
  server.use(http.put("/api/v1/pages/page-1", () => HttpResponse.json({ detail: "Save failed" }, { status: 500 })));
  const { user } = setup();
  await user.type(await screen.findByDisplayValue("Weather Page"), " changed");
  await user.click(screen.getByRole("button", { name: "Save Page" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Save Page" })).not.toBeDisabled());
  await user.click(screen.getByRole("link", { name: "Pages breadcrumb" }));
  expect(await screen.findByRole("alertdialog")).toBeInTheDocument();
});

it("warns when only the device target changes", async () => {
  const { user } = setup();
  await screen.findByDisplayValue("Weather Page");
  await user.click(screen.getByLabelText("Change board size"));
  await user.click(await screen.findByRole("option", { name: "Note" }));
  await user.click(screen.getByRole("link", { name: "Pages breadcrumb" }));
  expect(await screen.findByRole("alertdialog")).toBeInTheDocument();
});

it("leaves while the existing page is still loading without prompting", async () => {
  server.use(
    http.get("/api/v1/pages/page-1", async () => {
      await delay(300);
      return HttpResponse.json({
        id: "page-1",
        name: "Weather Page",
        type: "template",
        device_type: "flagship",
        template: ["HELLO"],
      });
    }),
  );
  const { user } = setup();
  await user.click(screen.getByRole("link", { name: "Pages breadcrumb" }));
  expect(await screen.findByRole("heading", { name: "Pages destination" })).toBeInTheDocument();
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
});

it("does not warn after reverting an edit", async () => {
  const { user } = setup();
  const name = await screen.findByDisplayValue("Weather Page");
  await user.type(name, " changed");
  await user.clear(name);
  await user.type(name, "Weather Page");
  await user.click(screen.getByRole("link", { name: "Pages breadcrumb" }));
  expect(await screen.findByRole("heading", { name: "Pages destination" })).toBeInTheDocument();
});

it("leaves after confirming deletion without another discard prompt", async () => {
  const { user } = setup();
  await user.type(await screen.findByDisplayValue("Weather Page"), " changed");
  await user.click(await screen.findByRole("button", { name: /^Delete page…/ }));
  await user.click(await screen.findByRole("button", { name: "Delete" }));
  expect(await screen.findByRole("heading", { name: "Pages destination" })).toBeInTheDocument();
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
});

it("guards the legacy query-string editor route too", async () => {
  window.history.replaceState({}, "", "/pages/edit?id=page-1");
  const { user } = setup("/pages/edit?id=page-1");
  await user.type(await screen.findByDisplayValue("Weather Page"), " changed");
  await user.click(screen.getByRole("link", { name: "Pages breadcrumb" }));
  expect(await screen.findByRole("alertdialog")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Keep editing" }));
  expect(screen.getByDisplayValue("Weather Page changed")).toBeInTheDocument();
});

// BB-B-27: deleting a page drops its cached query instead of refetching a
// page that no longer exists (a 404 in the console after every delete).
it("does not ask for the deleted page again", async () => {
  const { user } = setup();
  await screen.findByDisplayValue("Weather Page");
  let deleted = false;
  const afterDelete: string[] = [];
  const listener = ({ request }: { request: Request }) => {
    const path = new URL(request.url).pathname;
    if (request.method === "DELETE" && path.endsWith("/pages/page-1")) deleted = true;
    else if (deleted && request.method === "GET" && /\/pages\/page-1(\/|$)/.test(path)) afterDelete.push(path);
  };
  server.events.on("request:start", listener);
  try {
    await user.click(await screen.findByRole("button", { name: /^Delete page…/ }));
    await user.click(await screen.findByRole("button", { name: "Delete" }));
    expect(await screen.findByRole("heading", { name: "Pages destination" })).toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 200));
    expect(deleted).toBe(true);
    expect(afterDelete).toEqual([]);
  } finally {
    server.events.removeListener("request:start", listener);
  }
});

// BB-B-16: an unknown page id is a "doesn't exist" state with a way back,
// not a blank, saveable editor titled with the raw id.
it("says an unknown page doesn't exist and offers the way back", async () => {
  server.use(http.get("/api/v1/pages/page-1", () => HttpResponse.json({ detail: "Page not found" }, { status: 404 })));
  const { user } = setup();
  expect(await screen.findByRole("heading", { name: "This page doesn’t exist" })).toBeInTheDocument();
  expect(screen.queryByText("page-1")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /save page/i })).not.toBeInTheDocument();
  expect(screen.queryByDisplayValue("My Custom Page")).not.toBeInTheDocument();
  // No Creator IDE (status row, Inspector) around a page that isn't there.
  await new Promise((resolve) => setTimeout(resolve, 200));
  expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
  await user.click(screen.getAllByRole("button", { name: "Back to Pages" }).at(-1)!);
  expect(await screen.findByRole("heading", { name: "Pages destination" })).toBeInTheDocument();
});

// BB-B-16: the missing state shows at once; a 404 is not retried like a
// network blip (the app retries failed queries twice).
it("does not retry a page that isn't there", async () => {
  let gets = 0;
  server.use(
    http.get("/api/v1/pages/page-1", () => {
      gets += 1;
      return HttpResponse.json({ detail: "Page not found" }, { status: 404 });
    }),
  );
  const router = createMemoryRouter([{ path: "/pages/edit/:id", element: <EditPageClient pageId="page-1" /> }], {
    initialEntries: ["/pages/edit/page-1"],
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: 2, retryDelay: 1 } } });
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
  expect(await screen.findByRole("heading", { name: "This page doesn’t exist" })).toBeInTheDocument();
  await new Promise((resolve) => setTimeout(resolve, 100));
  expect(gets).toBe(1);
});
