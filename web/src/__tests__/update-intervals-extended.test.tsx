import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { UpdateIntervals } from "@/components/settings/update-intervals";
import type { BoardInstance } from "@/lib/api";

import { server } from "./mocks/server";

const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast: toastMock, Toaster: () => null }));

const boardA = {
  id: "a",
  name: "Kitchen",
  device_type: "flagship",
  api_mode: "local",
  polling_interval_seconds: 45,
  board_read_interval_local: 60,
  board_read_interval_cloud: 240,
} as BoardInstance;
const boardB = {
  ...boardA,
  id: "b",
  name: "Office",
  polling_interval_seconds: 90,
  board_read_interval_local: 120,
  board_read_interval_cloud: 300,
};

function TestWrapper({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
      }),
  );
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const input = () => screen.getByLabelText("Board Update Interval") as HTMLInputElement;

describe("UpdateIntervals per board", () => {
  beforeEach(() => vi.clearAllMocks());

  it("reads the explicitly supplied board instead of global polling defaults", () => {
    render(<UpdateIntervals board={boardA} />, { wrapper: TestWrapper });
    expect(input()).toHaveValue(45);
    expect(screen.getByLabelText("Board State Refresh (Local)")).toHaveValue(60);
    expect(screen.queryByText("Requires service restart")).not.toBeInTheDocument();
  });

  it.each([
    { label: "FiestaPanel", target: { output: "fiestapanel", api_mode: "virtual" }, local: false, cloud: false },
    { label: "legacy virtual board", target: { api_mode: "virtual" }, local: false, cloud: false },
    { label: "local Vestaboard", target: { output: "vestaboard", api_mode: "local" }, local: true, cloud: false },
    { label: "cloud Vestaboard", target: { output: "vestaboard", api_mode: "cloud" }, local: false, cloud: true },
    {
      label: "cloud output config overriding legacy local mode",
      target: {
        output: "vestaboard",
        api_mode: "local",
        output_config: { api_mode: "cloud" },
      },
      local: false,
      cloud: true,
    },
    {
      label: "unknown plugin output",
      target: { output: "custom-display", api_mode: "local" },
      local: true,
      cloud: true,
    },
  ])("shows only applicable read intervals for $label", ({ target, local, cloud }) => {
    render(<UpdateIntervals board={{ ...boardA, ...target } as BoardInstance} />, { wrapper: TestWrapper });
    expect(input()).toHaveValue(45);
    expect(!!screen.queryByLabelText("Board State Refresh (Local)")).toBe(local);
    expect(!!screen.queryByLabelText("Board State Refresh (Cloud)")).toBe(cloud);
  });

  it("sends only the changed interval and explicit board target", async () => {
    let body: unknown;
    server.use(
      http.put("/api/settings/polling", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({
          interval_seconds: 75,
          board_read_interval_local: 60,
          board_read_interval_cloud: 240,
          requires_restart: false,
        });
      }),
    );
    render(<UpdateIntervals board={boardA} />, { wrapper: TestWrapper });
    fireEvent.change(input(), { target: { value: "75" } });
    fireEvent.blur(input());
    await waitFor(() => expect(body).toEqual({ board_id: "a", interval_seconds: 75 }));
    await waitFor(() => expect(toastMock.success).toHaveBeenCalledTimes(1));
  });

  it("reseeds drafts and writes the new target when the selected board changes", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.put("/api/settings/polling", async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({ interval_seconds: 105, requires_restart: false });
      }),
    );
    const view = render(<UpdateIntervals board={boardA} />, { wrapper: TestWrapper });
    fireEvent.change(input(), { target: { value: "55" } });
    view.rerender(<UpdateIntervals board={boardB} />);
    expect(input()).toHaveValue(90);
    fireEvent.change(input(), { target: { value: "105" } });
    fireEvent.blur(input());
    await waitFor(() => expect(bodies).toEqual([{ board_id: "b", interval_seconds: 105 }]));
  });

  it.each(["", "5", "3601", "12.5"])("does not persist invalid polling draft %s", (value) => {
    const requests = vi.fn();
    server.use(http.put("/api/settings/polling", requests));
    render(<UpdateIntervals board={boardA} />, { wrapper: TestWrapper });
    fireEvent.change(input(), { target: { value } });
    fireEvent.blur(input());
    expect(requests).not.toHaveBeenCalled();
    expect(input()).toBeInvalid();
  });

  it("restores the saved interval after a rejected mutation", async () => {
    server.use(http.put("/api/settings/polling", () => HttpResponse.json({ detail: "refused" }, { status: 500 })));
    render(<UpdateIntervals board={boardA} />, { wrapper: TestWrapper });
    fireEvent.change(input(), { target: { value: "75" } });
    fireEvent.blur(input());
    await waitFor(() => expect(toastMock.error).toHaveBeenCalledTimes(1));
    expect(input()).toHaveValue(45);
    expect(toastMock.success).not.toHaveBeenCalled();
  });

  it("saves a local read interval only for this board", async () => {
    let body: unknown;
    server.use(
      http.put("/api/settings/polling", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ board_read_interval_local: 80, requires_restart: false });
      }),
    );
    render(<UpdateIntervals board={boardA} />, { wrapper: TestWrapper });
    const local = screen.getByLabelText("Board State Refresh (Local)");
    fireEvent.change(local, { target: { value: "80" } });
    fireEvent.blur(local);
    await waitFor(() => expect(body).toEqual({ board_id: "a", board_read_interval_local: 80 }));
  });
});
