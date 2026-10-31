import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { expect, it, vi } from "vitest";

import { ScheduleEntryForm } from "@/components/schedule-entry-form";
import { api, type ScheduleEntry } from "@/lib/api";

import { server } from "./mocks/server";

it("keeps the schedule draft's original revision when new query data arrives", async () => {
  const schedule: ScheduleEntry = {
    id: "schedule-a",
    page_id: "page-a",
    start_time: "09:00",
    end_time: "17:00",
    day_pattern: "all",
    enabled: true,
    created_at: "2026-01-01",
    revision: "original",
    edit_protocol: "schedule-revision-v1",
  };
  const pages = [{ id: "page-a", name: "Example" }];
  const onSubmit = vi.fn().mockRejectedValue(new Error("Schedule changed. Reload before saving."));
  const props = { pages, onSubmit, onCancel: vi.fn() };
  const view = render(<ScheduleEntryForm {...props} schedule={schedule} />);
  const user = userEvent.setup();
  await user.click(screen.getByRole("switch", { name: /enabled/i }));
  view.rerender(<ScheduleEntryForm {...props} schedule={{ ...schedule, revision: "newer" }} />);
  await user.click(screen.getByRole("button", { name: "Update Schedule" }));
  await waitFor(() =>
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        enabled: false,
        expected_revision: "original",
      }),
    ),
  );
  expect(await screen.findByText("Schedule changed. Reload before saving.")).toBeInTheDocument();
  expect(screen.getByRole("switch", { name: /enabled/i })).not.toBeChecked();
});

it("carries collection/schedule delete tokens and default-page preconditions in their exact request locations", async () => {
  const observed: unknown[] = [];
  server.use(
    http.delete("/api/v1/collections/:id", ({ request }) => {
      observed.push(new URL(request.url).searchParams.get("expected_revision"));
      return HttpResponse.json({ id: "collection:a" });
    }),
    http.delete("/api/v1/schedules/:id", ({ request }) => {
      observed.push(new URL(request.url).searchParams.get("expected_revision"));
      return HttpResponse.json({ id: "schedule-a" });
    }),
    http.put("/api/schedules/default-page", async ({ request }) => {
      observed.push(await request.json());
      return HttpResponse.json({
        default_page_id: null,
        revision: "next",
        edit_protocol: "schedule-default-revision-v1",
      });
    }),
  );
  await api.deleteCollection("collection:a", "original:/token");
  await api.deleteSchedule("schedule-a", "original:/token");
  await api.setDefaultPage(null, "board-a", "original:/token");
  expect(observed).toEqual([
    "original:/token",
    "original:/token",
    {
      page_id: null,
      board_id: "board-a",
      expected_revision: "original:/token",
    },
  ]);
});
