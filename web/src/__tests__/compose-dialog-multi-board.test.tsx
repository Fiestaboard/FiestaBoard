// The one-off compose surface on a multi-board install (issue #1787).
//
// The temporary-override store is PRIMARY-only ("triggers and temporary
// overrides are the PRIMARY board's feature set", src/main.py), so a composed
// message always lands on boards[0] no matter which board the sidebar has
// selected. The dialog must therefore be sized to the PRIMARY board and must
// say so — sizing it to the *current* board would preview a 15x3 Note and then
// send the content to a 22x6 Flagship.
//
// A single-board install can't catch this: there, current === primary.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CurrentBoardProvider, useCurrentBoard } from "@/components/current-board-context";
import { HomeCompose } from "@/components/home/home-compose";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

import { server } from "./mocks/server";

const API_BASE = "/api";

vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
  }),
}));

vi.mock("@/components/smart-link", () => ({
  default: ({ children, href, ...rest }: { children: React.ReactNode; href: string }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

/** Primary is a Flagship (22x6); the second board is a Note (15x3). */
const FLAGSHIP_PRIMARY_NOTE_SECONDARY = {
  board_type: "black",
  boards: [
    { id: "board-1", name: "Living Room", device_type: "flagship", board_color: "black", enabled: true },
    { id: "board-2", name: "Kitchen Note", device_type: "note", board_color: "white", enabled: true },
  ],
  devices: ["flagship", "note"],
};

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <ConfigOverridesProvider>
        <ThemeProvider attribute="class" defaultTheme="light">
          <CurrentBoardProvider>{children}</CurrentBoardProvider>
        </ThemeProvider>
      </ConfigOverridesProvider>
    </QueryClientProvider>
  );
}

/** Test-only harness for driving the board selector from inside the provider. */
function SwitchBoardButton({ to }: { to: string }) {
  const { setCurrentBoardId } = useCurrentBoard();
  return (
    <button type="button" onClick={() => setCurrentBoardId(to)}>
      switch-board-{to}
    </button>
  );
}

/** Select the Note (secondary) board, then open Compose from Home. */
async function openComposeOnTheNoteBoard() {
  const user = userEvent.setup();
  server.use(http.get(`${API_BASE}/settings/board`, () => HttpResponse.json(FLAGSHIP_PRIMARY_NOTE_SECONDARY)));
  localStorage.setItem("fiestaboard_current_board", "board-2");

  render(
    <>
      <SwitchBoardButton to="board-2" />
      <HomeCompose open onOpenChange={vi.fn()} />
    </>,
    { wrapper: TestWrapper },
  );

  await screen.findByText("Shows on Kitchen Note when you choose Show now. Nothing reaches the board before that.");
  await screen.findByRole("textbox", { name: /^Message$/i });
  return user;
}

function captureOverride() {
  const bodies: Record<string, unknown>[] = [];
  server.use(
    http.post(`${API_BASE}/settings/temporary-override`, async ({ request }) => {
      bodies.push((await request.json()) as Record<string, unknown>);
      return HttpResponse.json({ active: true });
    }),
  );
  return bodies;
}

// Since H1 every display has its own override, so Compose shows on the
// display in the switcher (07a "Show on" defaults to it), not the primary.
describe("Compose a message on a multi-display install (H1)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it("shows on the selected display, at its own size", async () => {
    const bodies = captureOverride();
    const user = await openComposeOnTheNoteBoard();
    await user.type(screen.getByRole("textbox", { name: /^Message$/i }), "HI");
    await user.click(screen.getByRole("button", { name: /^Show now$/i }));

    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toMatchObject({ board_id: "board-2", device_type: "note", template: ["HI"] });
  });

  it("names the selected display under Show on", async () => {
    await openComposeOnTheNoteBoard();
    expect(screen.getByRole("combobox", { name: "Show on" })).toHaveTextContent("Kitchen Note · Note 15 × 3");
  });

  it("rejects a message that overflows the selected Note", async () => {
    const user = await openComposeOnTheNoteBoard();
    await user.type(screen.getByRole("textbox", { name: /^Message$/i }), "ONE{Enter}TWO{Enter}THREE{Enter}FOUR");
    await waitFor(() => expect(screen.getByRole("button", { name: /^Show now$/i })).toBeDisabled());
    expect(screen.getByRole("alert")).toHaveTextContent("Too many lines: this board shows 3.");
  });

  it("shows on another display when Show on changes, at that display's size", async () => {
    const bodies = captureOverride();
    const user = await openComposeOnTheNoteBoard();
    await user.click(screen.getByRole("combobox", { name: "Show on" }));
    await user.click(await screen.findByRole("option", { name: /Living Room/ }));
    await screen.findByText("Shows on Living Room when you choose Show now. Nothing reaches the board before that.");
    await user.type(screen.getByRole("textbox", { name: /^Message$/i }), "ONE{Enter}TWO{Enter}THREE{Enter}FOUR");
    await user.click(screen.getByRole("button", { name: /^Show now$/i }));
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toMatchObject({ board_id: "board-1", device_type: "flagship" });
  });
});
