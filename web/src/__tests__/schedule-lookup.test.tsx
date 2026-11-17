import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { ScheduleLookup } from "@/components/schedule/schedule-lookup";
import type { Collection, Page } from "@/lib/api";

import { server } from "./mocks/server";

const pages = [{ id: "winner", name: "Hub chosen page", device_type: "flagship" }] as Page[];
const collections = [{ id: "collection:rules", name: "Weather rules" }] as Collection[];
function setup() {
  const requests: URL[] = [];
  server.use(
    http.get("/api/schedules/active/page", ({ request }) => {
      requests.push(new URL(request.url));
      return HttpResponse.json({
        page_id: "collection:rules",
        resolved_page_id: "winner",
        silenced: true,
        source: "schedule",
        schedule_enabled: true,
        temporary_override: { active: false },
      });
    }),
  );
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ScheduleLookup boardId="display-2" pages={pages} collections={collections} />
    </QueryClientProvider>,
  );
  return requests;
}
describe("Schedule instant lookup", () => {
  it("renders the hub's selected page and silence state for the chosen display", async () => {
    const requests = setup();
    fireEvent.click(screen.getByRole("button", { name: "Check instant" }));
    expect(await screen.findByText("Hub chosen page")).toBeInTheDocument();
    expect(screen.getByText("Silenced")).toBeInTheDocument();
    expect(requests[0].searchParams.get("board_id")).toBe("display-2");
    expect(requests[0].searchParams.get("at")).toBeTruthy();
  });
  it("renders every dry-run rule and timeline from the hub without sending a page", async () => {
    let dryBody: Record<string, unknown> = {};
    server.use(
      http.post("/api/collections/collection%3Arules/dry-run", async ({ request }) => {
        dryBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          collection_id: "collection:rules",
          page_id: "winner",
          rules: [
            { index: 0, expression: "weather.temp > 60", value: "true", matched: true },
            { index: 1, expression: "HOUR(NOW()) > 12", value: "false", matched: false },
          ],
          timeline: [{ from: "2026-11-17T12:00:00Z", until: "2026-11-17T13:00:00Z", page_id: "winner" }],
          shown_on: ["display-2"],
          sources: {},
          truncated: false,
        });
      }),
    );
    setup();
    fireEvent.click(screen.getByRole("button", { name: "Check instant" }));
    await screen.findByText("Hub chosen page");
    fireEvent.click(screen.getByRole("button", { name: "Run collection dry run" }));
    expect(await screen.findByText("weather.temp > 60")).toBeInTheDocument();
    expect(screen.getByText("HOUR(NOW()) > 12")).toBeInTheDocument();
    expect(screen.getByText(/Shown on: display-2/)).toBeInTheDocument();
    await waitFor(() => expect(dryBody.data).toBe("cached"));
  });
  it("does not retain an answer when the selected instant changes", async () => {
    setup();
    fireEvent.click(screen.getByRole("button", { name: "Check instant" }));
    await screen.findByText("Hub chosen page");
    fireEvent.change(screen.getByLabelText("Instant"), { target: { value: "2026-11-18T12:00" } });
    expect(screen.queryByText("Hub chosen page")).not.toBeInTheDocument();
  });
});

it("changes the instant through the keyboard-accessible day scrubber", () => {
  setup();
  const instant = (screen.getByLabelText("Instant") as HTMLInputElement).value;
  const slider = screen.getByRole("slider", { name: "Time of day" });
  fireEvent.keyDown(slider, { key: "End" });
  expect((screen.getByLabelText("Instant") as HTMLInputElement).value).not.toBe(instant);
});

it("rejects sample arrays without contacting the dry-run endpoint", async () => {
  setup();
  fireEvent.click(screen.getByRole("button", { name: "Check instant" }));
  await screen.findByText("Hub chosen page");
  fireEvent.change(screen.getByLabelText("Sample values (JSON object of variable paths)"), { target: { value: "[]" } });
  fireEvent.click(screen.getByRole("button", { name: "Run collection dry run" }));
  expect(screen.getByRole("alert")).toHaveTextContent("Enter a JSON object");
});
it("shows a hub lookup error without inventing a page", async () => {
  setup();
  server.use(
    http.get("/api/schedules/active/page", () =>
      HttpResponse.json({ detail: "Instant outside supported window" }, { status: 400 }),
    ),
  );
  fireEvent.click(screen.getByRole("button", { name: "Check instant" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Instant outside supported window");
  expect(screen.queryByText("Hub chosen page")).not.toBeInTheDocument();
});
it("reports a truncated collection timeline and exposes its exact raw response", async () => {
  setup();
  server.use(
    http.post("/api/collections/collection%3Arules/dry-run", () =>
      HttpResponse.json({
        page_id: null,
        rules: null,
        timeline: [],
        shown_on: [],
        sources: {},
        truncated: true,
        truncated_reason: "budget",
      }),
    ),
  );
  fireEvent.click(screen.getByRole("button", { name: "Check instant" }));
  await screen.findByText("Hub chosen page");
  fireEvent.click(screen.getByRole("button", { name: "Run collection dry run" }));
  expect(await screen.findByText("Timeline truncated: budget")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Show raw response" }));
  expect(await screen.findByText(/"truncated_reason": "budget"/)).toBeInTheDocument();
});
it("keeps a failed dry run separate from the successfully checked active page", async () => {
  setup();
  server.use(
    http.post("/api/collections/collection%3Arules/dry-run", () =>
      HttpResponse.json({ detail: "Collection is unavailable" }, { status: 404 }),
    ),
  );
  fireEvent.click(screen.getByRole("button", { name: "Check instant" }));
  await screen.findByText("Hub chosen page");
  fireEvent.click(screen.getByRole("button", { name: "Run collection dry run" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Collection is unavailable");
  expect(screen.getByText("Hub chosen page")).toBeInTheDocument();
});
