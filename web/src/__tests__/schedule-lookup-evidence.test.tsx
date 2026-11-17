import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { ScheduleLookup } from "@/components/schedule/schedule-lookup";
import type { Collection, Page } from "@/lib/api";

import { server } from "./mocks/server";
vi.mock("@/components/board-viewport", () => ({
  BoardViewport: ({ message }: { message: string }) => <output>{message}</output>,
}));
const pages = [
  { id: "a", name: "Actual A", device_type: "flagship", template: ["A"] },
  { id: "b", name: "Simulated B", device_type: "flagship", template: ["B"] },
] as Page[];
const collections = [{ id: "collection:other", name: "Other collection" }] as Collection[];
function setup(timezone = "UTC") {
  const renders: Record<string, unknown>[] = [];
  server.use(
    http.get("/api/schedules/active/page", () =>
      HttpResponse.json({
        page_id: "a",
        resolved_page_id: "a",
        source: "schedule",
        temporary_override: { active: false },
      }),
    ),
    http.post("/api/templates/render", async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      renders.push(body);
      return HttpResponse.json({ lines: body.template, line_count: 1 });
    }),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const tree = (zone: string) => (
    <QueryClientProvider client={client}>
      <ScheduleLookup boardId="board" timezone={zone} pages={pages} collections={collections} />
    </QueryClientProvider>
  );
  const view = render(tree(timezone));
  return { renders, rerenderZone: (zone: string) => view.rerender(tree(zone)) };
}
describe("Schedule evidence separation", () => {
  it("keeps the actual A preview separate from an unrelated collection's simulated B", async () => {
    server.use(
      http.post("/api/collections/collection%3Aother/dry-run", () =>
        HttpResponse.json({ page_id: "b", rules: [], timeline: [], shown_on: [], sources: {} }),
      ),
    );
    const { renders } = setup();
    fireEvent.click(screen.getByRole("button", { name: "Check instant" }));
    const actual = await screen.findByRole("region", { name: "Active page at instant" });
    await within(actual).findByText("A");
    fireEvent.click(screen.getByRole("button", { name: "Edit JSON values" }));
    fireEvent.change(screen.getByLabelText("Sample values (JSON object of variable paths)"), {
      target: { value: '{"weather.temp":70}' },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run collection dry run" }));
    const simulated = await screen.findByRole("region", { name: "Collection dry run" });
    expect(await within(simulated).findByText("B")).toBeInTheDocument();
    expect(within(actual).getByText("A")).toBeInTheDocument();
    expect(within(actual).queryByText("B")).not.toBeInTheDocument();
    expect(
      renders
        .filter((body) => (body.template as string[])[0] === "A")
        .every((body) => !(body.preview as Record<string, unknown>).values),
    ).toBe(true);
  });
  it("does not render an actual page as a substitute for a simulation with no winner", async () => {
    server.use(
      http.post("/api/collections/collection%3Aother/dry-run", () =>
        HttpResponse.json({ page_id: null, rules: [], timeline: [], shown_on: [], sources: {} }),
      ),
    );
    setup();
    fireEvent.click(screen.getByRole("button", { name: "Check instant" }));
    await screen.findByText("A");
    fireEvent.click(screen.getByRole("button", { name: "Run collection dry run" }));
    const simulated = await screen.findByRole("region", { name: "Collection dry run" });
    expect(within(simulated).getAllByText("None").length).toBeGreaterThan(0);
    expect(within(simulated).queryByText("A")).not.toBeInTheDocument();
  });
  it("does not apply sample values to any preview before the hub accepts the dry run", async () => {
    server.use(
      http.post("/api/collections/collection%3Aother/dry-run", () =>
        HttpResponse.json({ detail: "Bad variable path" }, { status: 422 }),
      ),
    );
    const { renders } = setup();
    fireEvent.click(screen.getByRole("button", { name: "Check instant" }));
    await screen.findByText("A");
    fireEvent.click(screen.getByRole("button", { name: "Edit JSON values" }));
    fireEvent.change(screen.getByLabelText("Sample values (JSON object of variable paths)"), {
      target: { value: '{"bad.path":70}' },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run collection dry run" }));
    await screen.findByText("Bad variable path");
    expect(renders.every((body) => !(body.preview as Record<string, unknown>).values)).toBe(true);
  });
  it("invalidates checked evidence when the hub timezone changes", async () => {
    const view = setup("America/Los_Angeles");
    fireEvent.click(screen.getByRole("button", { name: "Check instant" }));
    await screen.findByText("A");
    view.rerenderZone("UTC");
    expect(screen.queryByRole("region", { name: "Active page at instant" })).not.toBeInTheDocument();
    const value = (screen.getByLabelText("Instant") as HTMLInputElement).value;
    expect(value.slice(11, 13)).toBe(new Date().getUTCHours().toString().padStart(2, "0"));
  });
  it("uses hub timezone for timeline labels", async () => {
    server.use(
      http.post("/api/collections/collection%3Aother/dry-run", () =>
        HttpResponse.json({
          page_id: null,
          rules: [],
          timeline: [{ from: "2026-11-17T12:00:00Z", until: "2026-11-17T13:00:00Z", page_id: "b" }],
          shown_on: [],
          sources: {},
        }),
      ),
    );
    setup("Asia/Tokyo");
    fireEvent.click(screen.getByRole("button", { name: "Check instant" }));
    await screen.findByText("A");
    fireEvent.click(screen.getByRole("button", { name: "Run collection dry run" }));
    await waitFor(() => expect(screen.getByText(/Nov 17, 2026, 9:00 PM/)).toBeInTheDocument());
  });
});

it("offers quick moments and sends simulated missing paths only with the collection check", async () => {
  let body: Record<string, unknown> = {};
  server.use(
    http.post("/api/collections/collection%3Aother/dry-run", async ({ request }) => {
      body = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({
        page_id: null,
        matched_rule: 0,
        rules: [{ index: 0, expression: "DEFAULT(weather.temp, 0) < 10", matched: true, value: "true" }],
        timeline: [],
        shown_on: [],
        sources: { weather: { state: "stale", updated_at: "2026-11-17T12:00:00Z" } },
      });
    }),
  );
  setup("UTC");
  fireEvent.click(screen.getByRole("radio", { name: "Tomorrow 3:00 PM" }));
  const value = (screen.getByLabelText("Instant") as HTMLInputElement).value;
  expect(value.slice(11)).toBe("15:00");
  fireEvent.click(screen.getByRole("button", { name: "Check instant" }));
  await screen.findByText("A");
  fireEvent.change(screen.getByLabelText("Treat as missing (one variable path per line)"), {
    target: { value: "weather.temp\ntransit" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Run collection dry run" }));
  expect(await screen.findByText("First winning rule")).toBeInTheDocument();
  expect(body.missing).toEqual(["weather.temp", "transit"]);
  expect(Number(body.window_seconds) / Number(body.step_seconds) + 1).toBeLessThanOrEqual(96);
  expect(screen.getByText("Stale")).toBeInTheDocument();
});
it("uses a truthful UTC fallback for an invalid hub timezone", () => {
  setup("invalid/zone");
  expect(screen.getByText("Hub timezone is unavailable or invalid; using UTC.")).toBeInTheDocument();
});

it("builds What if value chips without requiring the advanced JSON editor", async () => {
  let body: Record<string, unknown> = {};
  server.use(
    http.post("/api/collections/collection%3Aother/dry-run", async ({ request }) => {
      body = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ page_id: null, rules: [], timeline: [], shown_on: [], sources: {} });
    }),
  );
  setup();
  fireEvent.click(screen.getByRole("button", { name: "Check instant" }));
  await screen.findByText("A");
  fireEvent.click(screen.getByRole("button", { name: "Add a value…" }));
  fireEvent.change(screen.getByLabelText("Variable path"), { target: { value: "weather.temperature" } });
  fireEvent.change(screen.getByLabelText("Value (text or JSON)"), { target: { value: "70" } });
  fireEvent.click(screen.getByRole("button", { name: "Add value" }));
  expect(screen.getByText("weather.temperature = 70")).toBeInTheDocument();
  expect(screen.queryByLabelText("Sample values (JSON object of variable paths)")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Run collection dry run" }));
  await waitFor(() => expect(body.values).toEqual({ "weather.temperature": 70 }));
  fireEvent.click(screen.getByRole("button", { name: "Remove weather.temperature" }));
  expect(screen.queryByText("weather.temperature = 70")).not.toBeInTheDocument();
});
