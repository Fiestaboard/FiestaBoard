import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useLineOverflow } from "@/hooks/use-line-overflow";
import { validateTemplateAt } from "@/lib/api/template-validation";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function mockFetch(body: unknown, status = 200) {
  const fetch = vi.fn(
    async () => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }),
  );
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("validateTemplateAt", () => {
  it("asks the hub to validate at the board and geometry the editor renders", async () => {
    const fetch = mockFetch({ valid: true, errors: [], rows: 24, cols: 96 });
    await validateTemplateAt({
      template: ["A"],
      lineMetadata: [{ alignment: "left", wrap: false }],
      boardId: "lobby",
      deviceType: "panel",
      grid: { rows: 24, cols: 96 },
    });
    const [url, init] = fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toContain("/templates/validate");
    expect(JSON.parse(init.body as string)).toEqual({
      template: ["A"],
      line_metadata: [{ alignment: "left", wrap: false }],
      board_id: "lobby",
      device_type: "panel",
      grid_rows: 24,
      grid_cols: 96,
    });
  });

  it("sends a note array's notes and nothing extra for a Flagship", async () => {
    const fetch = mockFetch({ valid: true, errors: [] });
    await validateTemplateAt({ template: ["A"], deviceType: "note_array", notesWide: 2, notesTall: 2 });
    await validateTemplateAt({ template: ["A"], deviceType: "flagship", notesWide: 2, grid: { rows: 1, cols: 1 } });
    const bodies = fetch.mock.calls.map((call) =>
      JSON.parse((call as unknown as [string, RequestInit])[1].body as string),
    );
    expect(bodies[0]).toEqual({ template: ["A"], device_type: "note_array", notes_wide: 2, notes_tall: 2 });
    expect(bodies[1]).toEqual({ template: ["A"], device_type: "flagship" });
  });
});

describe("useLineOverflow", () => {
  const target = { template: ["GOOD MORNING", "N JUDAH {{muni.next}}"], deviceType: "flagship" };

  it("returns the lines the hub measured past the board's width", async () => {
    mockFetch({
      valid: false,
      rows: 6,
      cols: 22,
      errors: [{ line: 2, column: 22, message: "Line 2 is too long", code: "line_too_long", max_length: 24 }],
    });
    const { result } = renderHook(() => useLineOverflow(target, 22, true), { wrapper });
    await waitFor(() => expect(result.current.overflows).toHaveLength(1));
    expect(result.current.overflows[0]).toEqual({ line: 2, columns: 24, maxColumns: 22, cut: 2 });
    expect(result.current.checkedAt).toBeInstanceOf(Date);
  });

  it("does not ask for an empty template or when disabled", () => {
    const fetch = mockFetch({ valid: true, errors: [] });
    renderHook(() => useLineOverflow({ template: ["", " "] }, 22, true), { wrapper });
    renderHook(() => useLineOverflow(target, 22, false), { wrapper });
    expect(fetch).not.toHaveBeenCalled();
  });

  it("shows nothing when the check fails", async () => {
    const fetch = mockFetch({ detail: "boom" }, 500);
    const { result } = renderHook(() => useLineOverflow(target, 22, true), { wrapper });
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(result.current.overflows).toEqual([]);
  });
});
