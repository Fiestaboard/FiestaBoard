import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CollectionShowNow } from "@/components/collection-show-now";
import type { Collection } from "@/lib/api";

const detail = { active_page_id: "p1", schedule_enabled: true, override_started_at: null, override_expires_at: null };
const detailHook = vi.hoisted(() => vi.fn());
vi.mock("@/components/current-board-context", () => ({
  useCurrentBoard: () => ({
    currentBoard: { id: "secondary", name: "Lobby", schedule_enabled: true },
    boards: [{ id: "primary" }, { id: "secondary", name: "Lobby" }],
  }),
}));
vi.mock("@/hooks/use-board", () => ({
  useBoardSettings: () => ({ data: {} }),
  usePages: () => ({ data: { pages: [{ id: "p1", name: "Morning" }] } }),
}));
vi.mock("@/hooks/use-silence", () => ({ useSilence: () => ({ active: true, until: "2026-01-01T08:00:00Z" }) }));
vi.mock("@/components/home/use-home-data", () => ({ useBoardDetail: detailHook }));
vi.mock("@/components/home/change-page-dialog", () => ({
  ChangePageDialog: (props: object) => <div data-testid="shared-dialog">{JSON.stringify(props)}</div>,
}));
it("opens the shared dialog on the named selected display with the saved Collection preselected", () => {
  detailHook.mockReturnValue({ data: detail });
  render(<CollectionShowNow collection={{ id: "collection:c1", name: "Rotation" } as Collection} onClose={vi.fn()} />);
  expect(detailHook).toHaveBeenCalledWith("secondary");
  expect(JSON.parse(screen.getByTestId("shared-dialog").textContent!)).toMatchObject({
    board: { id: "secondary", name: "Lobby" },
    isPrimary: false,
    initialPageId: "collection:c1",
    manualPageName: "Morning",
    silence: { until: "2026-01-01T08:00:00Z" },
  });
});
