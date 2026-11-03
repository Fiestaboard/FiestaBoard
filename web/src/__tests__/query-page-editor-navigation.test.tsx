import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeAll, expect, it, vi } from "vitest";

import { PageEditorBridgeProvider } from "@/components/page-editor-bridge-context";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";
import type { Page } from "@/lib/api";

import { PagesSection } from "../../app/routes/pages";
import EditPage from "../../app/routes/pages.edit._index";
import { server } from "./mocks/server";

vi.unmock("react-router");

beforeAll(async () => {
  await import("@/components/tiptap-template-editor/TipTapTemplateEditor");
});

afterEach(() => window.history.replaceState({}, "", "/"));

function setup(initialPath = "/pages/edit?id=first") {
  const pages: Page[] = [
    {
      id: "first",
      name: "First page",
      type: "template",
      device_type: "flagship",
      template: ["FIRST"],
      duration_seconds: 30,
      created_at: "2026-01-01T00:00:00Z",
    },
    {
      id: "second",
      name: "Second page",
      type: "template",
      device_type: "flagship",
      template: ["SECOND"],
      duration_seconds: 60,
      created_at: "2026-01-01T00:00:00Z",
    },
  ];
  const writes: { id: string; body: Partial<Page> }[] = [];
  server.use(
    http.get("/api/v1/pages", () => HttpResponse.json({ pages, total: pages.length })),
    http.get("/api/v1/pages/:id", ({ params }) => HttpResponse.json(pages.find((page) => page.id === params.id))),
    http.put("/api/v1/pages/:id", async ({ params, request }) => {
      const body = (await request.json()) as Partial<Page>;
      writes.push({ id: String(params.id), body });
      return HttpResponse.json({
        page: { ...pages.find((page) => page.id === params.id), ...body },
        incompatible_references: [],
      });
    }),
  );
  window.history.replaceState({}, "", initialPath);
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
    { initialEntries: [initialPath] },
  );
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}
    >
      <ConfigOverridesProvider>
        <ThemeProvider attribute="class" defaultTheme="light">
          <PageEditorBridgeProvider>
            <RouterProvider router={router} />
          </PageEditorBridgeProvider>
        </ThemeProvider>
      </ConfigOverridesProvider>
    </QueryClientProvider>,
  );
  return { router, writes, user: userEvent.setup() };
}

it("keeps the header, opened document and save target together across query navigation and history", async () => {
  const { router, user, writes } = setup();
  expect(await screen.findByDisplayValue("First page")).toBeInTheDocument();
  await act(async () => {
    await router.navigate("/pages/edit?id=second");
  });
  expect(await screen.findByRole("heading", { name: "Second page" })).toBeInTheDocument();
  expect(await screen.findByDisplayValue("Second page")).toBeInTheDocument();
  await act(async () => {
    await router.navigate(-1);
  });
  expect(await screen.findByDisplayValue("First page")).toBeInTheDocument();
  await act(async () => {
    await router.navigate(1);
  });
  expect(await screen.findByDisplayValue("Second page")).toBeInTheDocument();
  await user.type(screen.getByDisplayValue("Second page"), " saved");
  await user.click(screen.getByRole("button", { name: "Save Page" }));
  expect(await screen.findByRole("heading", { name: "Pages destination" })).toBeInTheDocument();
  expect(writes).toHaveLength(1);
  expect(writes[0]).toMatchObject({ id: "second", body: { name: "Second page saved", template: ["SECOND"] } });
});

it("keeps dirty edits on cancellation and opens the requested page after confirmed discard", async () => {
  const { router, user, writes } = setup();
  await user.type(await screen.findByDisplayValue("First page"), " unsaved");
  await act(async () => {
    await router.navigate("/pages/edit?id=second");
  });
  await user.click(await screen.findByRole("button", { name: "Keep editing" }));
  expect(router.state.location.search).toBe("?id=first");
  expect(screen.getByDisplayValue("First page unsaved")).toBeInTheDocument();
  await act(async () => {
    await router.navigate("/pages/edit?id=second");
  });
  await user.click(await screen.findByRole("button", { name: "Discard and leave" }));
  expect(await screen.findByDisplayValue("Second page")).toBeInTheDocument();
  expect(screen.queryByDisplayValue("First page unsaved")).not.toBeInTheDocument();
  expect(writes).toEqual([]);
  expect(router.state.location.search).toBe("?id=second");
});

it("preserves a dirty draft when only unrelated query parameters or hash change", async () => {
  const { router, user } = setup();
  await user.type(await screen.findByDisplayValue("First page"), " unsaved");
  await act(async () => {
    await router.navigate("/pages/edit?id=first&view=preview#canvas");
  });
  expect(router.state.location.hash).toBe("#canvas");
  expect(screen.getByDisplayValue("First page unsaved")).toBeInTheDocument();
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
});

it("does not offer the previous document for saving when the next page fails to load", async () => {
  const { router, writes } = setup();
  await screen.findByDisplayValue("First page");
  server.use(http.get("/api/v1/pages/second", () => HttpResponse.json({ detail: "Unavailable" }, { status: 500 })));
  await act(async () => {
    await router.navigate("/pages/edit?id=second");
  });
  expect(await screen.findByRole("heading", { name: "Second page" })).toBeInTheDocument();
  expect(await screen.findByRole("alert")).toHaveTextContent("Unavailable");
  expect(screen.queryByDisplayValue("First page")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Save Page" })).not.toBeInTheDocument();
  expect(writes).toEqual([]);
});

it.each([false, true])(
  "returns to the page list when the query ID is absent (after opening: %s)",
  async (afterOpening) => {
    const { router, writes } = setup(afterOpening ? "/pages/edit?id=first" : "/pages/edit");
    if (afterOpening) {
      await screen.findByDisplayValue("First page");
      await act(async () => {
        await router.navigate("/pages/edit");
      });
    }
    expect(await screen.findByRole("heading", { name: "Pages destination" })).toBeInTheDocument();
    await waitFor(() => expect(router.state.location.pathname).toBe("/pages"));
    expect(writes).toEqual([]);
  },
);
