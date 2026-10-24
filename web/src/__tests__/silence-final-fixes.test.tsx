import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ActivePageDisplay } from "@/components/active-page-display";
import { CurrentBoardProvider, useCurrentBoard } from "@/components/current-board-context";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

import { server } from "./mocks/server";

vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
}));
vi.mock("@/components/smart-link", () => ({
  default: ({ children, href, ...rest }: { children: React.ReactNode; href: string }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

function Wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <ConfigOverridesProvider>
        <ThemeProvider attribute="class" defaultTheme="light">
          <CurrentBoardProvider>{children}</CurrentBoardProvider>
        </ThemeProvider>
      </ConfigOverridesProvider>
    </QueryClientProvider>
  );
}

function SwitchBoard() {
  const { setCurrentBoardId } = useCurrentBoard();
  return <button onClick={() => setCurrentBoardId("b")}>Select second board</button>;
}

function fixture({ enabled = true, paused = false, unresolved = false } = {}) {
  const held: Record<string, boolean> = { a: true, b: true };
  server.use(
    http.get("/api/settings/board", () =>
      HttpResponse.json({
        board_type: "black",
        devices: ["flagship"],
        boards: [
          { id: "a", name: "First", device_type: "flagship", paused },
          { id: "b", name: "Second", device_type: "flagship", paused },
        ],
      }),
    ),
    http.get("/api/silence-status", ({ request }) => {
      const board = new URL(request.url).searchParams.get("board_id") ?? "a";
      return HttpResponse.json({
        enabled,
        active: false,
        start_time_utc: "22:00+00:00",
        end_time_utc: "07:00+00:00",
        mode: "freeze",
        held: held[board]
          ? {
              kind: "text",
              preview: `MESSAGE ${board.toUpperCase()}`,
              queued_at: "2026-10-24T23:00:00Z",
              delivery_state: unresolved ? "unresolved" : "pending",
            }
          : null,
      });
    }),
  );
  return held;
}

describe("Home keeps pending delivery visible outside quiet hours", () => {
  beforeEach(() => localStorage.clear());

  it.each(["paused", "offline", "ui", "disabled"])(
    "shows preview and discard for %s pending delivery",
    async (state) => {
      fixture({ paused: state === "paused", enabled: state !== "disabled" });
      if (state === "offline")
        server.use(
          http.get("/api/board/current-message", () => HttpResponse.json({ detail: "offline" }, { status: 503 })),
        );
      if (state === "ui") server.use(http.get("/api/settings/output", () => HttpResponse.json({ target: "ui" })));
      render(<ActivePageDisplay />, { wrapper: Wrapper });
      const notice = await screen.findByTestId("silence-alert");
      expect(notice).toHaveTextContent("Message awaiting delivery");
      expect(notice).not.toHaveTextContent("Silenced");
      expect(await screen.findByTestId("silence-held")).toHaveTextContent("MESSAGE A");
      expect(screen.getByTestId("silence-discard-held")).toBeEnabled();
    },
  );

  it("scopes failed and successful discard to the selected board", async () => {
    const held = fixture();
    const calls: string[] = [];
    let fail = true;
    server.use(
      http.delete("/api/silence-queue", ({ request }) => {
        const board = new URL(request.url).searchParams.get("board_id")!;
        calls.push(board);
        if (fail) return HttpResponse.json({ detail: "disk full" }, { status: 503 });
        held[board] = false;
        return HttpResponse.json({ board_id: board, discarded: true });
      }),
    );
    const user = userEvent.setup();
    render(
      <>
        <SwitchBoard />
        <ActivePageDisplay />
      </>,
      { wrapper: Wrapper },
    );
    expect(await screen.findByTestId("silence-held")).toHaveTextContent("MESSAGE A");
    await user.click(screen.getByRole("button", { name: "Select second board" }));
    await waitFor(() => expect(screen.getByTestId("silence-held")).toHaveTextContent("MESSAGE B"));
    await user.click(screen.getByTestId("silence-discard-held"));
    await waitFor(() => expect(calls).toEqual(["b"]));
    expect(screen.getByTestId("silence-held")).toHaveTextContent("MESSAGE B");
    fail = false;
    await waitFor(() => expect(screen.getByTestId("silence-discard-held")).toBeEnabled());
    await user.click(screen.getByTestId("silence-discard-held"));
    await waitFor(() => expect(screen.queryByTestId("silence-held")).not.toBeInTheDocument());
    expect(calls).toEqual(["b", "b"]);
    expect(held.a).toBe(true);
  });

  it("explains unresolved delivery without promising automatic retry", async () => {
    fixture({ enabled: false, unresolved: true });
    render(<ActivePageDisplay />, { wrapper: Wrapper });
    const notice = await screen.findByTestId("silence-alert");
    expect(notice).toHaveTextContent("Delivery needs attention");
    expect(notice).toHaveTextContent("Automatic retry is stopped");
    expect(notice).toHaveTextContent("explicitly send new content");
    expect(screen.getByTestId("silence-discard-held")).toBeEnabled();
  });
});
