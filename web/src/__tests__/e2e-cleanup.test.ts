import { http, HttpResponse } from "msw";
import { expect, it, vi } from "vitest";

import { API_URL, deleteAllPages, deleteAllSchedules } from "../../tests/helpers";
import { server } from "./mocks/server";

const API_BASE = new URL(API_URL, window.location.href).href.replace(/\/$/, "");

// Keep Playwright's runner out of Vitest; all cleanup/network code stays real.
vi.mock("@playwright/test", () => ({ test: { extend: () => ({}) }, expect: {} }));

it.each([
  { cleanup: deleteAllPages, resource: "pages", item: "page", list: "pages" },
  { cleanup: deleteAllSchedules, resource: "schedules", item: "schedule", list: "schedules" },
])(
  "strict $resource cleanup reports rejected deletion with resource and server detail",
  async ({ cleanup, resource, item, list }) => {
    server.use(
      http.get(`${API_BASE}/v1/${resource}`, () => HttpResponse.json({ [list]: [{ id: item }] })),
      http.delete(`${API_BASE}/v1/${resource}/${item}`, () =>
        HttpResponse.json({ detail: "Referenced by another fixture" }, { status: 409 }),
      ),
    );
    await expect(cleanup({ strict: true })).rejects.toThrow(
      new RegExp(`DELETE.*${resource}/${item}.*409.*Referenced by another fixture`),
    );
  },
);

it.each([
  { cleanup: deleteAllPages, resource: "pages" },
  { cleanup: deleteAllSchedules, resource: "schedules" },
])("strict $resource cleanup reports a failed listing", async ({ cleanup, resource }) => {
  server.use(
    http.get(`${API_BASE}/v1/${resource}`, () => HttpResponse.json({ detail: "Unavailable" }, { status: 503 })),
  );
  await expect(cleanup({ strict: true })).rejects.toThrow(new RegExp(`GET.*${resource}.*503.*Unavailable`));
});

it("clears all-board schedule references before deleting pages and preserves the replacement Welcome", async () => {
  const schedules = new Map([
    ["s1", "p1"],
    ["s2", "p2"],
  ]);
  const pages = new Set(["p1", "p2"]);
  server.use(
    http.get(`${API_BASE}/v1/schedules`, ({ request }) => {
      // Secondary/deleted-board schedules are visible only via the all-board contract.
      const allBoards = new URL(request.url).searchParams.get("board_id") === "*";
      return HttpResponse.json({
        schedules: [...schedules.keys()].filter((id) => allBoards || id === "s1").map((id) => ({ id })),
      });
    }),
    http.delete(`${API_BASE}/v1/schedules/:id`, ({ params }) => {
      schedules.delete(String(params.id));
      return new HttpResponse(null, { status: 204 });
    }),
    http.get(`${API_BASE}/v1/pages`, () => HttpResponse.json({ pages: [...pages].map((id) => ({ id })) })),
    http.delete(`${API_BASE}/v1/pages/:id`, ({ params }) => {
      if ([...schedules.values()].includes(String(params.id)))
        return HttpResponse.json({ detail: "Page is scheduled" }, { status: 409 });
      pages.delete(String(params.id));
      if (pages.size === 0) pages.add("welcome");
      return HttpResponse.json({ deleted: true });
    }),
  );
  await deleteAllPages({ strict: true, deleteSchedules: true });
  expect([...schedules]).toEqual([]);
  expect([...pages]).toEqual(["welcome"]);
});

it("stops page cleanup if unlinking schedules fails", async () => {
  const pages = new Set(["p1"]);
  server.use(
    http.get(`${API_BASE}/v1/schedules`, () => HttpResponse.json({ schedules: [{ id: "s1" }] })),
    http.delete(`${API_BASE}/v1/schedules/s1`, () =>
      HttpResponse.json({ detail: "Schedule storage unavailable" }, { status: 503 }),
    ),
    http.get(`${API_BASE}/v1/pages`, () => HttpResponse.json({ pages: [{ id: "p1" }] })),
    http.delete(`${API_BASE}/v1/pages/p1`, () => {
      pages.clear();
      return new HttpResponse(null, { status: 204 });
    }),
  );
  await expect(deleteAllPages({ strict: true, deleteSchedules: true })).rejects.toThrow("Schedule storage unavailable");
  expect([...pages]).toEqual(["p1"]);
});

it("preserves legacy best-effort cleanup for callers that do not opt into strict mode", async () => {
  server.use(
    http.get(`${API_BASE}/v1/pages`, () => HttpResponse.json({ pages: [{ id: "p1" }] })),
    http.delete(`${API_BASE}/v1/pages/p1`, () => HttpResponse.json({ detail: "Page is scheduled" }, { status: 409 })),
  );
  await expect(deleteAllPages()).resolves.toBeUndefined();
});
