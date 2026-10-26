import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { createMemoryRouter, RouterProvider } from "react-router";
import { expect, it, vi } from "vitest";

import { CurrentBoardProvider } from "@/components/current-board-context";
import { PageEditorBridgeProvider } from "@/components/page-editor-bridge-context";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

import NewPage from "../../app/routes/pages.new";
import { server } from "./mocks/server";

vi.unmock("react-router");

it("creates a page for the URL's display while the sidebar selects another display", async () => {
  localStorage.clear();
  localStorage.setItem("fiestaboard_current_board", "hall");
  let saved: Record<string, unknown> | undefined;
  server.use(
    http.get("/api/settings/board", () =>
      HttpResponse.json({
        board_type: "black",
        devices: ["flagship", "note"],
        boards: [
          { id: "hall", name: "Hall", device_type: "flagship", board_color: "black", enabled: true },
          { id: "desk", name: "Desk", device_type: "note", board_color: "black", enabled: true },
        ],
      }),
    ),
    http.post("/api/v1/pages", async ({ request }) => {
      saved = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ ...saved, id: "created-page", created_at: "2026-01-01T00:00:00Z" }, { status: 201 });
    }),
  );
  const router = createMemoryRouter(
    [
      { path: "/pages/new", element: <NewPage /> },
      { path: "/pages", element: <h1>Pages destination</h1> },
    ],
    { initialEntries: ["/pages/new?board=desk&fresh=1"] },
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <CurrentBoardProvider>
        <ConfigOverridesProvider>
          <ThemeProvider attribute="class" defaultTheme="light">
            <PageEditorBridgeProvider>
              <RouterProvider router={router} />
            </PageEditorBridgeProvider>
          </ThemeProvider>
        </ConfigOverridesProvider>
      </CurrentBoardProvider>
    </QueryClientProvider>,
  );
  const user = userEvent.setup();
  await waitFor(() => expect(screen.getByLabelText("Change board size")).toHaveTextContent("Note"));
  expect(screen.getByRole("combobox", { name: "Select board for live output" })).toHaveTextContent("Desk");
  await user.type(screen.getByLabelText(/page name/i), "Desk page");
  await user.click(screen.getByRole("button", { name: "Save Page" }));
  expect(await screen.findByRole("heading", { name: "Pages destination" })).toBeInTheDocument();
  expect(saved).toMatchObject({ name: "Desk page", device_type: "note" });
  expect(localStorage.getItem("fiestaboard_current_board")).toBe("hall");
});
