/**
 * The Collection page list (WEB-06, 07 `57:66920`, 07c `312:74870`, `312:76483`).
 *
 * Time mode is a FiestaUI SortableList of card ListRows: a pointer drags the
 * grip, the row itself takes Space / ↑ ↓ / Space / Esc, Move up / Move down
 * sit on the row and in its ••• menu, and a polite status line narrates each
 * step in the app's own copy. Random and variable modes have no order, so
 * they are one inset ListRowGroup with an × per page and no handles.
 */
import { arrayMove } from "@fiestaboard/ui";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CollectionPageList, type CollectionPageListProps } from "@/components/collection-page-list";
import type { Page } from "@/lib/api";

const pages = [
  { id: "p1", name: "Morning commute", device_type: "flagship" },
  { id: "p2", name: "Market open", device_type: "note" },
  { id: "p3", name: "Weather + surf", device_type: "note_array", notes_wide: 3, notes_tall: 2 },
  { id: "p4", name: "Good morning, Maya", device_type: "panel", grid_rows: 12, grid_cols: 29 },
] as Page[];

/** The form owns the order; this is the smallest stand-in for it. */
function Harness({
  mode = "time",
  onOrder,
  onRemove = vi.fn(),
}: {
  mode?: CollectionPageListProps["mode"];
  onOrder?: (ids: string[]) => void;
  onRemove?: (index: number) => void;
}) {
  const [ids, setIds] = useState(pages.map((p) => p.id));
  return (
    <CollectionPageList
      pageIds={ids}
      pages={pages}
      mode={mode}
      onMove={(from, to) =>
        setIds((prev) => {
          const next = arrayMove(prev, from, to);
          onOrder?.(next);
          return next;
        })
      }
      onRemove={onRemove}
    />
  );
}

function rows(): HTMLElement[] {
  return Array.from(document.querySelectorAll<HTMLElement>('[data-slot="sortable-list-item"]'));
}

function rowOf(name: string): HTMLElement {
  const found = rows().find((r) => r.textContent?.includes(name));
  if (!found) throw new Error(`no row ${name}`);
  return found;
}

function order(): string[] {
  return rows().map((r) => r.querySelector('[data-slot="list-row-title"]')?.textContent ?? "");
}

/** jsdom has no layout: rows 64px tall with an 8px gap, from y=100. */
function layout() {
  const root = document.querySelector<HTMLElement>('[data-slot="sortable-list"]');
  if (root) root.getBoundingClientRect = () => DOMRect.fromRect({ x: 0, y: 100, width: 400, height: 280 });
  rows().forEach((r, i) => {
    r.getBoundingClientRect = () => DOMRect.fromRect({ x: 0, y: 100 + i * 72, width: 400, height: 64 });
  });
}

function stubCoarsePointer(matches: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query === "(pointer: coarse)" ? matches : false,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("CollectionPageList, time mode", () => {
  it("renders one focusable card row per page with its handle, position and shape", () => {
    render(<Harness />);
    expect(order()).toEqual(["Morning commute", "Market open", "Weather + surf", "Good morning, Maya"]);
    const first = rowOf("Morning commute");
    expect(first).toHaveAttribute("tabindex", "0");
    expect(first.querySelector('[data-slot="sortable-list-handle"]')).not.toBeNull();
    expect(first.querySelector('[data-slot="list-row"]')).toHaveAttribute("data-variant", "card");
    expect(within(first).getByText("1")).toBeInTheDocument();
    expect(within(first).getByText("Flagship")).toBeInTheDocument();
    expect(within(rowOf("Market open")).getByText("Note")).toBeInTheDocument();
    expect(within(rowOf("Weather + surf")).getByText("Note Array 3×2")).toBeInTheDocument();
    expect(within(rowOf("Good morning, Maya")).getByText("Panel 12×29")).toBeInTheDocument();
  });

  it("lifts with Space, moves with the arrow keys, drops with Space and narrates each step", async () => {
    const user = userEvent.setup();
    const onOrder = vi.fn();
    render(<Harness onOrder={onOrder} />);
    rowOf("Morning commute").focus();
    await user.keyboard(" ");
    expect(screen.getByRole("status")).toHaveTextContent(
      "Morning commute lifted · position 1 of 4 · ↑ ↓ to move, Space to drop, Esc to cancel",
    );
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("status")).toHaveTextContent("Morning commute · moving to position 2 of 4");
    await user.keyboard("{ArrowDown}");
    await user.keyboard(" ");
    expect(screen.getByRole("status")).toHaveTextContent("Morning commute dropped · position 3 of 4");
    expect(order()).toEqual(["Market open", "Weather + surf", "Morning commute", "Good morning, Maya"]);
    expect(onOrder).toHaveBeenLastCalledWith(["p2", "p3", "p1", "p4"]);
    expect(rowOf("Morning commute")).toHaveFocus();
  });

  it("Esc puts a lifted row back where it started", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    rowOf("Market open").focus();
    await user.keyboard(" {ArrowDown}{ArrowDown}{Escape}");
    expect(order()).toEqual(["Morning commute", "Market open", "Weather + surf", "Good morning, Maya"]);
    expect(screen.getByRole("status")).toHaveTextContent("Market open returned to position 2 of 4");
  });

  it("Move up and Move down on the row move it one place and say where it went", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const row = rowOf("Weather + surf");
    await user.click(within(row).getByRole("button", { name: "Move up" }));
    expect(order()).toEqual(["Morning commute", "Weather + surf", "Market open", "Good morning, Maya"]);
    expect(screen.getByRole("status")).toHaveTextContent("Weather + surf moved to position 2 of 4");
    await user.click(within(rowOf("Weather + surf")).getByRole("button", { name: "Move down" }));
    expect(order()).toEqual(["Morning commute", "Market open", "Weather + surf", "Good morning, Maya"]);
  });

  it("disables Move up on the first row and Move down on the last", () => {
    render(<Harness />);
    expect(within(rowOf("Morning commute")).getByRole("button", { name: "Move up" })).toBeDisabled();
    expect(within(rowOf("Good morning, Maya")).getByRole("button", { name: "Move down" })).toBeDisabled();
  });

  it("a pointer drag on the grip reorders once, on drop", () => {
    const onOrder = vi.fn();
    render(<Harness onOrder={onOrder} />);
    layout();
    const handle = rowOf("Morning commute").querySelector<HTMLElement>('[data-slot="sortable-list-handle"]')!;
    fireEvent.pointerDown(handle, { button: 0, pointerId: 1, clientY: 130 });
    fireEvent.pointerMove(handle, { pointerId: 1, clientY: 130 + 80 });
    expect(screen.getByRole("status")).toHaveTextContent("Morning commute · moving to position 2 of 4");
    expect(onOrder).not.toHaveBeenCalled();
    fireEvent.pointerUp(handle, { pointerId: 1, clientY: 210 });
    expect(onOrder).toHaveBeenCalledTimes(1);
    expect(onOrder).toHaveBeenCalledWith(["p2", "p1", "p3", "p4"]);
    expect(screen.getByRole("status")).toHaveTextContent("Morning commute dropped · position 2 of 4");
  });

  it("the ••• menu moves the row and removes the page", async () => {
    const user = userEvent.setup();
    const onRemove = vi.fn();
    render(<Harness onRemove={onRemove} />);
    await user.click(screen.getByRole("button", { name: "More actions for Market open" }));
    await user.click(await screen.findByRole("menuitem", { name: "Move up" }));
    expect(order()).toEqual(["Market open", "Morning commute", "Weather + surf", "Good morning, Maya"]);

    await user.click(screen.getByRole("button", { name: "More actions for Market open" }));
    const moveUp = await screen.findByRole("menuitem", { name: "Move up" });
    expect(moveUp).toHaveAttribute("aria-disabled", "true");
    await user.click(screen.getByRole("menuitem", { name: "Move down" }));
    expect(order()).toEqual(["Morning commute", "Market open", "Weather + surf", "Good morning, Maya"]);

    await user.click(screen.getByRole("button", { name: "More actions for Weather + surf" }));
    await user.click(await screen.findByRole("menuitem", { name: "Remove Weather + surf" }));
    expect(onRemove).toHaveBeenCalledWith(2);
  });

  it("disables the menu's Move down on the last row", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "More actions for Good morning, Maya" }));
    expect(await screen.findByRole("menuitem", { name: "Move down" })).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByRole("menuitem", { name: "Move up" })).not.toHaveAttribute("aria-disabled", "true");
  });

  it("names a panel without a grid size plainly", () => {
    const panel = [{ id: "px", name: "Lobby panel", device_type: "panel" }] as Page[];
    render(<CollectionPageList pageIds={["px"]} pages={panel} mode="time" onMove={vi.fn()} onRemove={vi.fn()} />);
    expect(within(rowOf("Lobby panel")).getByText("Panel")).toBeInTheDocument();
  });

  it("shows the keyboard legend for a fine pointer", () => {
    stubCoarsePointer(false);
    render(<Harness />);
    expect(screen.getByTestId("collection-reorder-keys")).toBeInTheDocument();
  });

  it("drops the keyboard legend for a coarse pointer, whatever the width", () => {
    stubCoarsePointer(true);
    render(<Harness />);
    expect(screen.queryByTestId("collection-reorder-keys")).not.toBeInTheDocument();
  });

  it("gives a coarse pointer the larger ••• button", () => {
    stubCoarsePointer(true);
    render(<Harness />);
    expect(screen.getByRole("button", { name: "More actions for Market open" })).toHaveAttribute(
      "data-size",
      "icon-lg",
    );
  });

  it("keeps the compact ••• button for a fine pointer", () => {
    stubCoarsePointer(false);
    render(<Harness />);
    expect(screen.getByRole("button", { name: "More actions for Market open" })).toHaveAttribute(
      "data-size",
      "icon-sm",
    );
  });

  it("gives a coarse pointer the 44px handle", () => {
    stubCoarsePointer(true);
    render(<Harness />);
    const handle = rowOf("Morning commute").querySelector('[data-slot="sortable-list-handle"]');
    expect(handle).toHaveAttribute("data-size", "touch");
    expect(rowOf("Morning commute").querySelector('[data-slot="list-row"]')).toHaveAttribute("data-size", "touch");
  });

  it("keeps the default handle for a fine pointer", () => {
    stubCoarsePointer(false);
    render(<Harness />);
    const handle = rowOf("Morning commute").querySelector('[data-slot="sortable-list-handle"]');
    expect(handle).toHaveAttribute("data-size", "default");
  });
});

describe("CollectionPageList, random and variable modes", () => {
  it.each(["random", "variable"] as const)("%s mode is an inset list with no handles and an × per page", (mode) => {
    const onRemove = vi.fn();
    render(<Harness mode={mode} onRemove={onRemove} />);
    expect(document.querySelector('[data-slot="sortable-list"]')).toBeNull();
    expect(document.querySelector('[data-slot="sortable-list-handle"]')).toBeNull();
    const group = screen.getByRole("list");
    expect(group).toHaveAttribute("data-slot", "list-row-group");
    expect(group).toHaveAttribute("data-variant", "inset");
    expect(within(group).getAllByRole("listitem")).toHaveLength(4);
    act(() => screen.getByRole("button", { name: "Remove Weather + surf" }).click());
    expect(onRemove).toHaveBeenCalledWith(2);
  });
});

describe("CollectionPageList, random list on touch", () => {
  it("touch-sizes the rows and the × for a coarse pointer", () => {
    stubCoarsePointer(true);
    render(<Harness mode="random" />);
    for (const row of within(screen.getByRole("list")).getAllByRole("listitem")) {
      expect(row).toHaveAttribute("data-size", "touch");
    }
    expect(screen.getByRole("button", { name: "Remove Market open" })).toHaveAttribute("data-size", "icon-lg");
  });

  it("keeps compact rows and × for a fine pointer", () => {
    stubCoarsePointer(false);
    render(<Harness mode="random" />);
    for (const row of within(screen.getByRole("list")).getAllByRole("listitem")) {
      expect(row).toHaveAttribute("data-size", "default");
    }
    expect(screen.getByRole("button", { name: "Remove Market open" })).toHaveAttribute("data-size", "icon-sm");
  });
});

describe("CollectionPageList, missing pages", () => {
  it("names a page that no longer exists by its id", () => {
    render(<CollectionPageList pageIds={["gone"]} pages={pages} mode="time" onMove={vi.fn()} onRemove={vi.fn()} />);
    expect(rowOf("gone")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "More actions for gone" })).toBeInTheDocument();
  });
});
