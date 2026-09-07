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

import { ActivePageDisplay } from "@/components/active-page-display";
import { CurrentBoardProvider, useCurrentBoard } from "@/components/current-board-context";
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

/** Select the Note (secondary) board, then open the compose dialog. */
async function openComposeOnTheNoteBoard() {
  const user = userEvent.setup();
  server.use(
    http.get(`${API_BASE}/settings/board`, () => HttpResponse.json(FLAGSHIP_PRIMARY_NOTE_SECONDARY)),
    http.get(`${API_BASE}/schedules/active/page`, () =>
      HttpResponse.json({ page_id: "page-1", source: "manual", schedule_enabled: false }),
    ),
  );

  render(
    <>
      <SwitchBoardButton to="board-2" />
      <ActivePageDisplay />
    </>,
    { wrapper: TestWrapper },
  );

  await screen.findByText("Active Display", undefined, { timeout: 5000 });
  await user.click(screen.getByRole("button", { name: "switch-board-board-2" }));
  await waitFor(() => expect(screen.getByTestId("active-display-board-name")).toHaveTextContent(/Kitchen Note/i));

  await user.click(screen.getByRole("button", { name: /Change Page/i }));
  await user.click(await screen.findByRole("button", { name: /Compose a message/i }));
  await screen.findByRole("textbox", { name: /^Message$/i });

  return user;
}

describe("compose one-off on a multi-board install", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it("sends to the primary board's geometry even when a different board is selected", async () => {
    let capturedBody: Record<string, unknown> | null = null;
    server.use(
      http.post(`${API_BASE}/settings/temporary-override`, async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ active: true, template: ["HI"], device_type: "flagship" });
      }),
    );

    const user = await openComposeOnTheNoteBoard();
    await user.type(screen.getByRole("textbox", { name: /^Message$/i }), "HI");
    await user.click(screen.getByRole("button", { name: /Send to board/i }));

    await waitFor(() => expect(capturedBody).not.toBeNull());
    // The Note board is selected, but the override drives the Flagship.
    expect(capturedBody).toMatchObject({ device_type: "flagship" });
  });

  it("names the board the message will actually land on", async () => {
    await openComposeOnTheNoteBoard();
    expect(await screen.findByText(/Living Room/)).toBeInTheDocument();
  });

  it("allows a message that fits the primary Flagship but not the selected Note", async () => {
    await openComposeOnTheNoteBoard();
    const editor = screen.getByRole("textbox", { name: /^Message$/i });
    // 5 lines: over a Note's 3 rows, within a Flagship's 6.
    fireChange(editor, "A\nB\nC\nD\nE");
    await waitFor(() => expect(screen.getByRole("button", { name: /Send to board/i })).toBeEnabled());
    expect(screen.queryByText(/too many lines/i)).not.toBeInTheDocument();
  });

  it("still rejects a message that overflows the primary board", async () => {
    await openComposeOnTheNoteBoard();
    const editor = screen.getByRole("textbox", { name: /^Message$/i });
    fireChange(editor, "A\nB\nC\nD\nE\nF\nG");
    await waitFor(() => expect(screen.getByText(/too many lines/i)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /Send to board/i })).toBeDisabled();
  });
});

// userEvent.type is slow for multi-line input and swallows newlines in a
// textarea unless escaped; a direct change event is the honest way to set a
// multi-line value here.
function fireChange(element: HTMLElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set;
  setter?.call(element, value);
  element.dispatchEvent(new Event("input", { bubbles: true }));
}
