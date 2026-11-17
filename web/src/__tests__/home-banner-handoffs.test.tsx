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
    expect(screen.getByTestId("home-board-state")).toHaveClass("opacity-50");
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
    expect(screen.getByTestId("home-board-state")).toHaveClass("opacity-60");
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
