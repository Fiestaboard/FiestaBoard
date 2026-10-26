import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ScheduleBehavior } from "@/components/settings/schedule-behavior";
import type { BoardInstance } from "@/lib/api";

import { server } from "./mocks/server";

const toastMock = vi.hoisted(() => ({ success: vi.fn(), info: vi.fn(), error: vi.fn(), warning: vi.fn() }));
vi.mock("sonner", () => ({ toast: toastMock, Toaster: () => null }));
const boardA = { id: "a", name: "Kitchen", schedule_defer_on_reenable: false } as BoardInstance;
const boardB = { ...boardA, id: "b", name: "Office", schedule_defer_on_reenable: true };
function TestWrapper({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { retry: false },
          mutations: { retry: false },
        },
      }),
  );
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("ScheduleBehavior per board", () => {
  beforeEach(() => vi.clearAllMocks());

  it("reflects the explicitly targeted board and switches targets", () => {
    const view = render(<ScheduleBehavior board={boardA} />, { wrapper: TestWrapper });
    expect(screen.getByRole("switch")).toHaveAttribute("aria-checked", "false");
    view.rerender(<ScheduleBehavior board={boardB} />);
    expect(screen.getByRole("switch")).toHaveAttribute("aria-checked", "true");
  });

  it("persists behavior only for the selected board", async () => {
    let sent: unknown;
    server.use(
      http.put("/api/schedules/settings", async ({ request }) => {
        sent = await request.json();
        return HttpResponse.json({ defer_on_reenable: true });
      }),
    );
    render(<ScheduleBehavior board={boardA} />, { wrapper: TestWrapper });
    await userEvent.click(screen.getByRole("switch"));
    await waitFor(() => expect(sent).toEqual({ board_id: "a", defer_on_reenable: true }));
  });

  it("rolls the switch back after a rejected save", async () => {
    server.use(http.put("/api/schedules/settings", () => HttpResponse.json({ detail: "nope" }, { status: 500 })));
    render(<ScheduleBehavior board={boardA} />, { wrapper: TestWrapper });
    await userEvent.click(screen.getByRole("switch"));
    await waitFor(() => expect(toastMock.error).toHaveBeenCalledTimes(1));
    expect(screen.getByRole("switch")).toHaveAttribute("aria-checked", "false");
  });

  it("does not let a failed save for A change B after navigation", async () => {
    let finish: (() => void) | undefined;
    server.use(
      http.put("/api/schedules/settings", async () => {
        await new Promise<void>((resolve) => {
          finish = resolve;
        });
        return HttpResponse.json({ detail: "nope" }, { status: 500 });
      }),
    );
    const view = render(<ScheduleBehavior board={boardA} />, { wrapper: TestWrapper });
    await userEvent.click(screen.getByRole("switch"));
    await waitFor(() => expect(finish).toBeDefined());
    view.rerender(<ScheduleBehavior board={boardB} />);
    finish!();
    await waitFor(() => expect(toastMock.error).toHaveBeenCalled());
    expect(screen.getByRole("switch")).toHaveAttribute("aria-checked", "true");
  });
});
