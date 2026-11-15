/**
 * Every word the reorder list shows or announces comes from the app's
 * messages, not from FiestaUI's English defaults (which happen to match
 * `en.json`, so the main suite cannot tell them apart). Here `t` returns a
 * marked key, so a label that skipped i18n would show up unmarked.
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CollectionPageList } from "@/components/collection-page-list";
import type { Page } from "@/lib/api";

vi.mock("@/i18n/translations", () => {
  const t = (key: string, params?: Record<string, unknown>) =>
    params ? `‹${key}:${Object.values(params).join(",")}›` : `‹${key}›`;
  return { useTranslations: () => t };
});

const pages = [
  { id: "p1", name: "Uno", device_type: "flagship" },
  { id: "p2", name: "Dos", device_type: "note" },
] as Page[];

describe("CollectionPageList copy", () => {
  it("passes the app's own labels to SortableList", async () => {
    const user = userEvent.setup();
    render(<CollectionPageList pageIds={["p1", "p2"]} pages={pages} mode="time" onMove={vi.fn()} onRemove={vi.fn()} />);
    const row = screen.getAllByRole("listitem")[0];
    expect(within(row).getByRole("button", { name: "‹sortMoveUp›" })).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: "‹sortMoveDown›" })).toBeInTheDocument();
    expect(within(row).getByText("‹pageShapeFlagship›")).toBeInTheDocument();
    expect(document.getElementById(row.getAttribute("aria-describedby")!)).toHaveTextContent("‹sortInstructions›");
    row.focus();
    await user.keyboard(" ");
    expect(screen.getByRole("status")).toHaveTextContent("‹sortLifted:Uno,1,2›");
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("status")).toHaveTextContent("‹sortMoving:Uno,2,2›");
    await user.keyboard("{Escape}");
    expect(screen.getByRole("status")).toHaveTextContent("‹sortCancelled:Uno,1,2›");
    row.focus();
    await user.keyboard(" ");
    await user.keyboard(" ");
    expect(screen.getByRole("status")).toHaveTextContent("‹sortDropped:Uno,1,2›");
    await user.click(within(row).getByRole("button", { name: "‹sortMoveDown›" }));
    expect(screen.getByRole("status")).toHaveTextContent("‹sortMoved:Uno,2,2›");
  });
});
