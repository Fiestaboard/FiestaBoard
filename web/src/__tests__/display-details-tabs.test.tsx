import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { expect, it, vi } from "vitest";

import type { ToolCall } from "@/lib/ai-chat-types";
import { resolveAnchor } from "@/lib/ai-choreography/anchors";
import { homeFor } from "@/lib/ai-choreography/home";
import { getScript } from "@/lib/ai-choreography/registry";
import type { ChoreographyContext } from "@/lib/ai-choreography/types";

import DisplayPage from "../../app/routes/displays.$boardId";
import { server } from "./mocks/server";

const search = { value: "section=playback" };
const replace = vi.fn();
const board = { id: "route-board", name: "Desk", device_type: "note", board_color: "black", output: "vestaboard" };
vi.mock("@/components/settings/display-settings", () => ({
  useDisplayBoards: () => ({ boards: [board], saving: false, updateBoard: vi.fn() }),
}));
vi.mock("@/components/displays/display-editor", () => ({
  DisplayEditor: () => <div data-ai-anchor="settings.board.route-board" />,
}));
vi.mock("@/components/displays/display-transition", () => ({ DisplayTransition: () => null }));
vi.mock("@/components/displays/display-live-preview", () => ({ DisplayLivePreview: () => null }));
vi.mock("@/components/board-out-of-sync-banner", () => ({ BoardOutOfSyncBanner: () => null }));
vi.mock("@/hooks/use-router", () => ({
  useParams: () => ({ boardId: "route-board" }),
  useRouter: () => ({ push: vi.fn(), replace }),
  useSearchParams: () => new URLSearchParams(search.value),
}));

it("retains an unsaved silence change when switching display tabs", async () => {
  server.use(
    http.get("/api/settings/all", () =>
      HttpResponse.json({
        general: { timezone: "UTC" },
        silence_schedule: { config: { enabled: true, mode: "indicator", indicator_text: "SNOOZING" } },
      }),
    ),
  );
  const user = userEvent.setup();
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <DisplayPage />
    </QueryClientProvider>,
  );
  const input = await screen.findByLabelText(/message text/i);
  await user.clear(input);
  await user.type(input, "QUIET");
  await user.click(screen.getByRole("tab", { name: "Settings" }));
  await waitFor(() => expect(input).not.toBeVisible());
  await user.click(screen.getByRole("tab", { name: "Playback" }));
  expect(await screen.findByLabelText(/message text/i)).toHaveValue("QUIET");
});

it("reveals the board settings anchor after choreography navigates on the same display route", async () => {
  search.value = "section=overview";
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={client}>
      <DisplayPage />
    </QueryClientProvider>,
  );
  const destination = homeFor({ name: "update_board", args: { board_id: board.id } });
  search.value = destination.href.split("?")[1] ?? "";
  view.rerender(
    <QueryClientProvider client={client}>
      <DisplayPage />
    </QueryClientProvider>,
  );
  await waitFor(() => expect(resolveAnchor(destination.anchor)).toBeVisible());
  expect(screen.getByRole("tab", { name: "Settings" })).toHaveAttribute("aria-selected", "true");
});

it("reveals the actual silence switch after a same-route Playback navigation", async () => {
  search.value = "section=overview";
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={client}>
      <DisplayPage />
    </QueryClientProvider>,
  );
  const call = {
    name: "update_setting",
    args: { category: "silence_schedule", values: { board_id: board.id, enabled: true } },
  } as unknown as ToolCall;
  const steps = getScript(call.name).narrate(call, {
    t: () => "Working",
    label: () => "Silence",
    currentBoardId: () => "different-sidebar-board",
  } as unknown as ChoreographyContext);
  const destination = steps.find((step) => step.kind === "navigate")!;
  expect(destination).toMatchObject({ href: "/displays/route-board?section=playback" });
  search.value = destination.href.split("?")[1];
  view.rerender(
    <QueryClientProvider client={client}>
      <DisplayPage />
    </QueryClientProvider>,
  );
  await waitFor(() => expect(resolveAnchor("settings.silence_schedule.enabled")).toBeVisible());
  expect(screen.getByRole("tab", { name: "Playback" })).toHaveAttribute("aria-selected", "true");
});
