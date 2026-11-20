import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { type BoardActions, BoardActionsMenu, BoardContextMenu } from "@/components/home/board-context-menu";

vi.mock("@/components/smart-link", () => ({
  default: ({ children, href, ...rest }: { children: React.ReactNode; href: string }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

function pointer(coarse: boolean) {
  vi.spyOn(window, "matchMedia").mockImplementation(
    (query: string) =>
      ({
        matches: coarse && query.includes("coarse"),
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }) as unknown as MediaQueryList,
  );
}

const actions = (): BoardActions => ({
  boardName: "Kitchen",
  summary: "Pizza Special · Override",
  onChangePage: vi.fn(),
  onCompose: vi.fn(),
  editHref: "/pages/edit/pizza",
  onCopyText: vi.fn(),
  onRefresh: vi.fn(),
  paused: false,
  onTogglePause: vi.fn(),
});

// BB-A-5 (07a `310:33402`): on a touch phone the board's actions open as a
// bottom sheet — "Kitchen" over "<page> · <mode>", 48 px rows, and no
// keyboard-shortcut letters — from the ⋯ button and from a long-press.
describe("board actions on a coarse pointer", () => {
  afterEach(() => vi.restoreAllMocks());

  it("the ⋯ button opens a sheet with the display, what it shows, and the actions", async () => {
    pointer(true);
    const a = actions();
    render(<BoardActionsMenu actions={a} />);
    fireEvent.click(screen.getByRole("button", { name: /Actions for Kitchen/ }));
    const sheet = await screen.findByRole("dialog", { name: "Kitchen" });
    expect(sheet).toHaveAttribute("data-slot", "sheet-content");
    expect(within(sheet).getByText("Pizza Special · Override")).toBeInTheDocument();
    expect(within(sheet).queryByText(/^[PCE]$/)).not.toBeInTheDocument();
    fireEvent.click(within(sheet).getByRole("button", { name: /Change Page/ }));
    expect(a.onChangePage).toHaveBeenCalled();
  });

  it("a long-press on the board opens the same sheet, not the anchored menu", async () => {
    pointer(true);
    render(
      <BoardContextMenu actions={actions()}>
        <div>board</div>
      </BoardContextMenu>,
    );
    fireEvent.contextMenu(screen.getByTestId("home-board"));
    const sheet = await screen.findByRole("dialog", { name: "Kitchen" });
    expect(sheet).toHaveAttribute("data-slot", "sheet-content");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("keeps the dropdown, with its shortcuts, on a fine pointer", async () => {
    pointer(false);
    render(<BoardActionsMenu actions={actions()} />);
    fireEvent.click(screen.getByRole("button", { name: /Actions for Kitchen/ }));
    const menu = await screen.findByRole("menu");
    expect(within(menu).getByText("P")).toBeInTheDocument();
  });
});
