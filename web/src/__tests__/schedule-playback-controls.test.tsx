import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { ScheduleBehavior } from "@/components/settings/schedule-behavior";
import type { BoardInstance } from "@/lib/api";

import { server } from "./mocks/server";
const board = {
  id: "secondary",
  name: "Desk",
  device_type: "note",
  schedule_enabled: true,
  schedule_defer_on_reenable: false,
} as BoardInstance;
const toastMock = vi.hoisted(() => ({ error: vi.fn() }));
vi.mock("sonner", () => ({ toast: toastMock }));
function setup() {
  server.use(
    http.get("/api/v1/schedules", () =>
      HttpResponse.json({ schedules: [], total: 0, enabled: true, default_page_id: "small" }),
    ),
    http.get("/api/v1/pages", () =>
      HttpResponse.json({
        pages: [
          { id: "small", name: "Note page", device_type: "note" },
          { id: "small2", name: "Second note page", device_type: "note" },
          { id: "big", name: "Flagship page", device_type: "flagship" },
        ],
        total: 3,
      }),
    ),
    http.get("/api/v1/collections", () => HttpResponse.json({ collections: [], total: 0 })),
  );
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}
    >
      <ScheduleBehavior board={board} />
    </QueryClientProvider>,
  );
}
describe("Display Playback schedule controls", () => {
  it("writes Schedule Mode only to the explicit non-primary display", async () => {
    let sent: unknown;
    server.use(
      http.patch("/api/v1/boards/secondary", async ({ request }) => {
        sent = await request.json();
        return HttpResponse.json({ schedule_enabled: false });
      }),
    );
    setup();
    const mode = await screen.findByRole("switch", { name: "Schedule Mode" });
    await userEvent.click(mode);
    await waitFor(() => expect(sent).toEqual({ schedule_enabled: false }));
  });
  it("rolls a rejected mode write back to the saved mode", async () => {
    server.use(
      http.patch("/api/v1/boards/secondary", () => HttpResponse.json({ detail: "Mode rejected" }, { status: 500 })),
    );
    setup();
    const mode = await screen.findByRole("switch", { name: "Schedule Mode" });
    await userEvent.click(mode);
    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith("Mode rejected"));
    expect(mode).toHaveAttribute("aria-checked", "true");
  });
  it("filters gap defaults to the explicit display geometry and persists its selected page", async () => {
    let sent: unknown;
    server.use(
      http.patch("/api/v1/boards/secondary", async ({ request }) => {
        sent = await request.json();
        return HttpResponse.json({ default_page_id: "small2" });
      }),
    );
    setup();
    await userEvent.click(await screen.findByRole("combobox", { name: /Default page for gaps/ }));
    expect(await screen.findByRole("option", { name: "Second note page" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Flagship page" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("option", { name: "Second note page" }));
    await waitFor(() => expect(sent).toEqual({ default_page_id: "small2" }));
  });
  it("restores the saved default page when the hub rejects a change", async () => {
    server.use(
      http.patch("/api/v1/boards/secondary", () => HttpResponse.json({ detail: "Default rejected" }, { status: 500 })),
    );
    setup();
    const select = await screen.findByRole("combobox", { name: /Default page for gaps/ });
    await userEvent.click(select);
    await userEvent.click(await screen.findByRole("option", { name: "Second note page" }));
    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith("Default rejected"));
    expect(select).toHaveTextContent("Note page");
  });
});
