import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { useDisplaysNeedingALook } from "@/hooks/use-displays-needing-a-look";
import type { BoardInstance } from "@/lib/api";

import { server } from "./mocks/server";

// BB-A-10: the header switcher must not call a display fine while Home and
// Displays say it needs a look. Same rules as the Displays list.
const kitchen = { id: "kitchen", name: "Kitchen", device_type: "flagship" } as BoardInstance;
const den = { id: "den", name: "Den TV", device_type: "panel", output: "fiestapanel" } as unknown as BoardInstance;
const hall = { id: "hall", name: "Hallway", device_type: "note" } as BoardInstance;

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useDisplaysNeedingALook", () => {
  it("flags an unreachable display and a panel no TV is showing", async () => {
    server.use(
      http.get("/api/v1/status", () =>
        HttpResponse.json({
          boards: {
            kitchen: { health: { reachable: true } },
            hall: { health: { reachable: false } },
            den: { health: { reachable: null } },
          },
        }),
      ),
      http.get("/api/panels", () =>
        HttpResponse.json({ panels: [{ id: "panel-den", board_id: "den", is_display: false }] }),
      ),
      http.get("/api/auth/sessions", () => HttpResponse.json({ sessions: [] })),
    );
    const { result } = renderHook(() => useDisplaysNeedingALook([kitchen, den, hall]), { wrapper });
    await waitFor(() => expect(result.current.has("hall")).toBe(true));
    await waitFor(() => expect(result.current.has("den")).toBe(true));
    expect(result.current.has("kitchen")).toBe(false);
  });
});
