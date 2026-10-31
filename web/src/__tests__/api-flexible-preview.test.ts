import { http, HttpResponse } from "msw";
import { expect, it } from "vitest";

import { api } from "@/lib/api";

import { server } from "./mocks/server";

it.each([undefined, "", "missing-board"])(
  "preserves explicit preview target %s for server validation",
  async (boardId) => {
    let payload: unknown;
    server.use(
      http.post("/api/pages/preview/flexible", async ({ request }) => {
        payload = await request.json();
        return HttpResponse.json({});
      }),
    );
    const page = { name: "Draft", type: "flexible" as const, blocks: [] };
    await api.previewFlexiblePage(page, boardId);
    expect(payload).toEqual({ page, ...(boardId === undefined ? {} : { board_id: boardId }) });
  },
);
