/**
 * BB-C-1 / BB-C-2: the Schedule route explains overlaps where the reader is.
 *
 * - The entry sheet asks the hub about the unsaved draft and says which entry
 *   shows during the overlap, with a one-tap fix, at every width.
 * - Saving an entry that still overlaps is a warning, not "Schedule created".
 * - The header badge reads localized sentences and keeps listing gaps.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router";
import { beforeEach, expect, it, vi } from "vitest";

import { ScheduleEditorBridgeProvider } from "@/components/schedule-editor-bridge-context";
import { FormatPreferencesProvider } from "@/hooks/use-format-preferences";

import SchedulePage from "../../app/routes/schedule";
import { server } from "./mocks/server";

const toasts = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }));
vi.mock("sonner", () => ({ toast: toasts }));
vi.mock("@/components/current-board-context", () => ({
  useCurrentBoard: () => ({
    currentBoardId: "board-1",
    currentBoard: { id: "board-1", name: "Kitchen", device_type: "flagship", board_color: "black" },
    boards: [{ id: "board-1", name: "Kitchen", device_type: "flagship", board_color: "black" }],
  }),
}));

const base = {
  board_id: "",
  day_pattern: "weekdays",
  recurrence_type: "weekly",
  start_type: "fixed",
  end_type: "fixed",
  enabled: true,
  edit_protocol: "schedule-revision-v1",
  revision: "r1",
};
const clock = { ...base, id: "clock", page_id: "p-clock", start_time: "09:00", end_time: "12:00" };
const blank = { ...base, id: "blank", page_id: "p-blank", start_time: "10:00", end_time: "11:00" };
const overlapWith = (self: string, other: string, winner: string) => ({
  schedule1_id: other,
  schedule2_id: self,
  conflict_description:
    "Schedules overlap on friday, monday, thursday, tuesday, wednesday: 09:00-12:00 and 10:00-11:00",
  days: ["monday", "tuesday", "wednesday", "thursday", "friday"],
  start_time: "10:00",
  end_time: "11:00",
  winner_id: winner,
});

type Body = { candidate?: { start_time: string; end_time: string }; candidate_id?: string };
let requests: Body[] = [];

function hub(gaps: { start_time: string; end_time: string; days: string[] }[] = []) {
  server.use(
    http.get("/api/settings/all", () =>
      HttpResponse.json({ general: { timezone: "UTC", time_format: "12h" }, silence_schedule: { config: {} } }),
    ),
    http.get("/api/v1/schedules", () =>
      HttpResponse.json({ schedules: [clock, blank], enabled: true, default_page_id: null }),
    ),
    http.get("/api/v1/pages", () =>
      HttpResponse.json({
        pages: [
          { id: "p-clock", name: "Clock & Date", device_type: "flagship" },
          { id: "p-blank", name: "Blank", device_type: "flagship" },
        ],
      }),
    ),
    http.post("/api/schedules/validate", async ({ request }) => {
      const body = (await request.json()) as Body;
      requests.push(body);
      const candidate = body.candidate;
      if (!candidate)
        return HttpResponse.json({ valid: false, overlaps: [overlapWith("blank", "clock", "blank")], gaps });
      // The hub's answer for the draft: Clock & Date 11:00-12:00 no longer overlaps.
      if (candidate.start_time === "11:00") return HttpResponse.json({ valid: true, overlaps: [], gaps: [] });
      const self = body.candidate_id ?? "candidate";
      const other = self === "clock" ? "blank" : "clock";
      return HttpResponse.json({ valid: false, overlaps: [overlapWith(self, other, "blank")], gaps: [] });
    }),
  );
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <FormatPreferencesProvider>
        <MemoryRouter>
          <ScheduleEditorBridgeProvider>
            <SchedulePage />
          </ScheduleEditorBridgeProvider>
        </MemoryRouter>
      </FormatPreferencesProvider>
    </QueryClientProvider>,
  );
}

async function openEntry(name: RegExp) {
  fireEvent.click((await screen.findAllByRole("button", { name }))[0]);
  return screen.findByRole("dialog");
}

beforeEach(() => {
  vi.clearAllMocks();
  requests = [];
  localStorage.setItem("schedule-view-mode", "list");
});

it("explains, inside the entry sheet, that the entry overlaps and which one shows (BB-C-1)", async () => {
  hub();
  renderPage();
  const sheet = await openEntry(/^Blank/);

  const callout = await within(sheet).findByTestId("schedule-entry-conflict");
  expect(callout).toHaveTextContent(
    "Overlaps Clock & Date (Mon–Fri, 10:00 AM – 11:00 AM). Blank shows then: when entries overlap, the one that started most recently wins.",
  );
  expect(requests).toContainEqual(
    expect.objectContaining({ candidate_id: "blank", candidate: expect.objectContaining({ start_time: "10:00" }) }),
  );
});

it("offers a one-tap fix that changes the draft and clears the warning (BB-C-1)", async () => {
  hub();
  renderPage();
  const sheet = await openEntry(/^Clock & Date/);

  fireEvent.click(await within(sheet).findByRole("button", { name: "Start at 11:00 AM instead" }));

  expect(within(sheet).getByLabelText("Start Time")).toHaveValue("11:00");
  await waitFor(() => expect(within(sheet).queryByTestId("schedule-entry-conflict")).not.toBeInTheDocument());
});

it("warns instead of a plain success when the saved entry still overlaps (BB-C-1)", async () => {
  hub();
  server.use(
    http.put("/api/v1/schedules/blank", async ({ request }) =>
      HttpResponse.json({ ...blank, ...((await request.json()) as object), revision: "r2", warnings: [] }),
    ),
  );
  renderPage();
  const sheet = await openEntry(/^Blank/);

  fireEvent.click(within(sheet).getByRole("button", { name: "Save" }));

  await waitFor(() => expect(toasts.warning).toHaveBeenCalled());
  expect(toasts.warning.mock.calls[0][0]).toBe("Saved, but it overlaps another entry");
  expect(toasts.warning.mock.calls[0][1].description).toContain("Blank shows then");
  expect(toasts.success).not.toHaveBeenCalledWith("Schedule updated");
});

it("lists conflicts as readable sentences and still lists the gaps (BB-C-2)", async () => {
  hub([{ start_time: "23:00", end_time: "23:59", days: ["tuesday", "monday"] }]);
  renderPage();

  const badge = await screen.findByRole("button", { name: "1 schedule conflict, 1 schedule gap" });
  await userEvent.setup().click(badge);

  const menu = await screen.findByRole("menu");
  expect(menu).toHaveTextContent("Clock & Date and Blank overlap (Mon–Fri, 10:00 AM – 11:00 AM).");
  expect(menu).not.toHaveTextContent("friday, monday");
  expect(menu).toHaveTextContent("Schedule Gaps");
  expect(menu).toHaveTextContent("Mon, Tue");
  expect(menu).toHaveTextContent("11:00 PM");
});
