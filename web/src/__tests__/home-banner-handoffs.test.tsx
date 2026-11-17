import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ActivePageDisplay } from "@/components/active-page-display";
import { CurrentBoardProvider } from "@/components/current-board-context";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

import { server } from "./mocks/server";

const connection = {
  deviceOnline: true,
  hubReachable: true,
  hubKnown: true,
  lastContactAt: Date.now(),
  retry: vi.fn(),
};
vi.mock("@/hooks/use-hub-connection", () => ({ useHubConnection: () => connection }));
vi.mock("@/components/smart-link", () => ({
  default: ({ children, href, ...rest }: { children: React.ReactNode; href: string }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));
function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}
    >
      <ConfigOverridesProvider>
        <ThemeProvider defaultTheme="light">
          <CurrentBoardProvider>{children}</CurrentBoardProvider>
        </ThemeProvider>
      </ConfigOverridesProvider>
    </QueryClientProvider>
  );
}
beforeEach(() => {
  connection.deviceOnline = true;
  connection.hubReachable = true;
  localStorage.clear();
});
describe("Home banner hand-offs", () => {
  it("hub failure dims Last known and guards Change Page plus C/P shortcuts", async () => {
    connection.hubReachable = false;
    const compose = vi.fn();
    render(<ActivePageDisplay onCompose={compose} />, { wrapper: Wrapper });
    await screen.findByTestId("now-showing");
    expect(screen.getByRole("button", { name: "Change Page" })).toBeDisabled();
    expect(screen.getByText("Last known")).toBeInTheDocument();
    expect(screen.getByTestId("home-board-state")).toHaveClass("[&_[data-slot=board-viewport-bezel]]:opacity-50");
    fireEvent.keyDown(window, { key: "c" });
    fireEvent.keyDown(window, { key: "p" });
    expect(compose).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
  it("an offline display has a destructive badge and 0.6 dim while sends stay enabled", async () => {
    server.use(
      http.get("/api/v1/status", () =>
        HttpResponse.json({
          boards: {
            default: { health: { reachable: false, breaker_open: true, last_connected_at: new Date().toISOString() } },
          },
        }),
      ),
    );
    render(<ActivePageDisplay />, { wrapper: Wrapper });
    await waitFor(() => expect(screen.getByText("Offline")).toBeInTheDocument());
    expect(screen.getByTestId("home-board-state")).toHaveClass("[&_[data-slot=board-viewport-bezel]]:opacity-60");
    expect(screen.getByRole("button", { name: "Change Page" })).toBeEnabled();
  });
  it("removes the standing silence notice while keeping a held message and Discard", async () => {
    server.use(
      http.get("/api/silence-status", () =>
        HttpResponse.json({
          enabled: true,
          active: true,
          mode: "freeze",
          ends_at_utc: new Date(Date.now() + 3600000).toISOString(),
          held: { kind: "message", preview: "GOOD LUCK", queued_at: new Date().toISOString() },
        }),
      ),
    );
    render(<ActivePageDisplay />, { wrapper: Wrapper });
    await screen.findByTestId("home-held-message");
    expect(screen.queryByTestId("silence-alert")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Discard" }).length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "Show now" })).not.toBeInTheDocument();
  });
});

it.each([false, undefined, true].flatMap((enabled) => [true, false].map((timed) => ({ enabled, timed }))))(
  "held message only promises Schedule resumes when enabled ($enabled, timed=$timed)",
  async ({ enabled, timed }) => {
    server.use(
      http.get("/api/schedules/active/page", () => HttpResponse.json({ page_id: "page-1", schedule_enabled: enabled })),
      http.get("/api/silence-status", () =>
        HttpResponse.json({
          enabled: true,
          active: true,
          mode: "freeze",
          ends_at_utc: timed ? new Date(Date.now() + 3600000).toISOString() : null,
          held: { kind: "message", preview: "GOOD LUCK", queued_at: new Date().toISOString() },
        }),
      ),
    );
    render(<ActivePageDisplay />, { wrapper: Wrapper });
    const card = await screen.findByTestId("home-held-message");
    await waitFor(() =>
      expect(card).toHaveTextContent(timed ? "Shows on Flagship at" : "Waits until Silence Schedule ends"),
    );
    if (enabled === true) expect(card).toHaveTextContent("then Schedule resumes");
    else expect(card).not.toHaveTextContent("Schedule resumes");
  },
);

it("keeps a typed Compose message when the hub drops, then permits retry after recovery", async () => {
  const { ComposePageDialog } = await import("@/components/compose-page-dialog");
  const props = { open: true, onOpenChange: vi.fn(), targetBoardLabel: "Kitchen", deviceType: "flagship" as const };
  const view = render(<ComposePageDialog {...props} />, { wrapper: Wrapper });
  const editor = screen.getByRole("textbox", { name: /^message$/i });
  fireEvent.change(editor, { target: { value: "GOOD LUCK" } });
  await waitFor(() => expect(screen.getByRole("button", { name: "Show now" })).toBeEnabled());
  connection.hubReachable = false;
  view.rerender(<ComposePageDialog {...props} />);
  expect(screen.getByRole("button", { name: "Show now" })).toBeDisabled();
  expect(editor).toHaveValue("GOOD LUCK");
  const notice = screen.getByText(/Can’t reach your hub at/).closest("[data-slot='status-banner']");
  expect(notice).toHaveAttribute("data-layout", "stacked");
  expect(notice).toHaveAttribute("data-touch", "");
  expect(screen.getByText("Show now comes back when the hub answers.")).toBeInTheDocument();
  connection.hubReachable = true;
  view.rerender(<ComposePageDialog {...props} />);
  expect(screen.getByRole("button", { name: "Show now" })).toBeEnabled();
});

it("uses the expected page in Home's out-of-sync banner with one recovery action", async () => {
  server.use(
    http.get("/api/board/current-message", () =>
      HttpResponse.json({ characters: [[1]], expected_characters: [[2]], message: "OTHER APP", rows: 6, cols: 22 }),
    ),
  );
  render(<ActivePageDisplay />, { wrapper: Wrapper });
  const banner = await screen.findByTestId("board-out-of-sync");
  await waitFor(() => expect(banner).toHaveTextContent("Flagship is out of sync"));
  expect(banner).toHaveTextContent("It’s showing something other than Weather Page.");
  expect(screen.getByRole("button", { name: "Show Weather Page again" })).toBeInTheDocument();
  expect(banner.querySelectorAll("button")).toHaveLength(1);
  expect(screen.getByText("Should be showing · Flagship")).toBeInTheDocument();
});

vi.mock("@/components/wizard-provider", () => ({ useWizard: () => ({ triggerWizard: vi.fn() }) }));
it("disables header Compose during hub loss and has one standing silence banner", async () => {
  const { default: Home } = await import("../../app/routes/home");
  connection.hubReachable = false;
  const view = render(<Home />, { wrapper: Wrapper });
  expect(screen.getByRole("button", { name: "Compose a message" })).toBeDisabled();
  view.unmount();
  connection.hubReachable = true;
  server.use(
    http.get("/api/silence-status", () =>
      HttpResponse.json({
        enabled: true,
        active: true,
        mode: "freeze",
        ends_at_utc: new Date(Date.now() + 3600000).toISOString(),
      }),
    ),
  );
  render(<Home />, { wrapper: Wrapper });
  await screen.findByText(/Silence Schedule until/);
  expect(screen.getAllByText(/Silence Schedule until/)).toHaveLength(1);
  expect(screen.queryByTestId("silence-alert")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Compose a message" })).toBeEnabled();
});

it("pauses an already-open Change Page dialog when hub connectivity drops", async () => {
  const { ChangePageDialog } = await import("@/components/home/change-page-dialog");
  const props = {
    open: true,
    onOpenChange: vi.fn(),
    board: undefined,
    isPrimary: true,
    scheduleEnabled: false,
    nextChange: null,
    initialPageId: "page-1",
  };
  const view = render(<ChangePageDialog {...props} />, { wrapper: Wrapper });
  await waitFor(() => expect(screen.getByRole("button", { name: "Show now" })).toBeEnabled());
  connection.deviceOnline = false;
  view.rerender(<ChangePageDialog {...props} />);
  expect(screen.getByRole("button", { name: "Show now" })).toBeDisabled();
  expect(screen.getByText("You’re offline")).toBeInTheDocument();
});

it.each(["hub", "display"])("Last known ignores unconfirmed Live Output for %s loss", async (lost) => {
  connection.hubReachable = lost !== "hub";
  if (lost === "display")
    server.use(
      http.get("/api/v1/status", () => HttpResponse.json({ boards: { default: { health: { reachable: false } } } })),
    );
  localStorage.setItem("fiestaboard:liveOutputMessage", JSON.stringify("UNSENT MIRROR"));
  server.use(
    http.get("/api/settings/board", () =>
      HttpResponse.json({
        boards: [
          {
            id: "default",
            name: "Desk",
            device_type: "panel",
            device_model: "divoom_pixoo64",
            grid_rows: 8,
            grid_cols: 10,
          },
        ],
      }),
    ),
    http.get("/api/board/current-message", () =>
      HttpResponse.json({ message: "LAST SENT", characters: null, expected_characters: null, rows: 8, cols: 10 }),
    ),
  );
  render(<ActivePageDisplay />, { wrapper: Wrapper });
  await waitFor(() =>
    expect(screen.getByRole("img")).toHaveAttribute("aria-label", expect.stringContaining("LAST SENT")),
  );
  expect(screen.getByRole("img").getAttribute("aria-label")).not.toContain("UNSENT MIRROR");
  fireEvent(
    window,
    new StorageEvent("storage", { key: "fiestaboard:liveOutputMessage", newValue: JSON.stringify("NEW UNSENT TEXT") }),
  );
  expect(screen.getByRole("img").getAttribute("aria-label")).toContain("LAST SENT");
  expect(screen.getByRole("img").getAttribute("aria-label")).not.toContain("NEW UNSENT TEXT");
});

it.each(["silence", "live"])("does not advertise unavailable out-of-sync recovery during %s", async (state) => {
  if (state === "live") localStorage.setItem("fiestaboard:liveOutputMessage", JSON.stringify("MIRROR"));
  else
    server.use(
      http.get("/api/silence-status", () => HttpResponse.json({ active: true, enabled: true, mode: "freeze" })),
    );
  server.use(
    http.get("/api/board/current-message", () =>
      HttpResponse.json({ message: "OTHER", characters: [[1]], expected_characters: [[2]], rows: 6, cols: 22 }),
    ),
  );
  render(<ActivePageDisplay />, { wrapper: Wrapper });
  await screen.findByRole("heading", { name: "Weather Page", level: 2 });
  expect(screen.queryByTestId("board-out-of-sync")).not.toBeInTheDocument();
  expect(screen.queryByText(/The board itself reports something else/)).not.toBeInTheDocument();
  expect(screen.queryByText("Should be showing · Flagship")).not.toBeInTheDocument();
});

it.each(["before", "during"])(
  "Cancel override Undo cannot send when connectivity drops %s its status read",
  async (when) => {
    const { toast } = await import("sonner");
    const info = vi.spyOn(toast, "info");
    let reads = 0;
    let writes = 0;
    let release!: () => void;
    const pending = new Promise<void>((resolve) => {
      release = resolve;
    });
    server.use(
      http.get("/api/schedules/active/page", () =>
        HttpResponse.json({
          schedule_enabled: true,
          page_id: "page-1",
          temporary_override: {
            active: true,
            page_id: "page-2",
            expires_at: new Date(Date.now() + 3600000).toISOString(),
            revert_mode: "schedule",
          },
        }),
      ),
      http.delete("/api/settings/temporary-override", () => HttpResponse.json({ revert_mode: "schedule" })),
      http.get("/api/settings/temporary-override", async () => {
        reads++;
        if (when === "during") await pending;
        return HttpResponse.json({ active: false });
      }),
      http.post("/api/settings/temporary-override", () => {
        writes++;
        return HttpResponse.json({ active: true });
      }),
    );
    const view = render(<ActivePageDisplay />, { wrapper: Wrapper });
    fireEvent.click(await screen.findByRole("button", { name: "Cancel override" }));
    await waitFor(() => expect(info).toHaveBeenCalled());
    const undo = (
      info.mock.calls.find((args) => args[0] === "Override canceled")?.[1]?.action as unknown as {
        onClick: () => Promise<void>;
      }
    ).onClick;
    if (when === "before") {
      connection.deviceOnline = false;
      view.rerender(<ActivePageDisplay />);
      await undo();
      expect(reads).toBe(0);
    } else {
      const undoing = undo();
      await waitFor(() => expect(reads).toBe(1));
      connection.hubReachable = false;
      view.rerender(<ActivePageDisplay />);
      release();
      await undoing;
    }
    expect(writes).toBe(0);
    info.mockRestore();
  },
);
