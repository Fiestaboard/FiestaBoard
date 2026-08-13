import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BootGate } from "@/components/boot-gate";
import { TemplateEditorToolbar } from "@/components/tiptap-template-editor/components/TemplateEditorToolbar";
import { UpdateProvider } from "@/components/update-context";

import { server } from "./mocks/server";

const API_BASE = "/api";

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <UpdateProvider>{children}</UpdateProvider>
    </QueryClientProvider>
  );
}

/**
 * The last two of the #1568 fixes that had no coverage of their own.
 */
describe("state that must land in the first commit", () => {
  describe("BootGate", () => {
    beforeEach(() => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
      window.localStorage.clear();
    });
    afterEach(() => {
      vi.useRealTimers();
      window.localStorage.clear();
    });

    it("reveals the app once the health check answers", async () => {
      server.use(http.get(`${API_BASE}/health`, () => HttpResponse.json({ status: "ok" })));

      render(
        <BootGate>
          <output data-testid="app">app</output>
        </BootGate>,
        { wrapper: TestWrapper },
      );

      expect(await screen.findByTestId("app")).toBeInTheDocument();
    });

    it("holds the splash while the health check is failing", async () => {
      server.use(http.get(`${API_BASE}/health`, () => new HttpResponse(null, { status: 503 })));

      render(
        <BootGate>
          <output data-testid="app">app</output>
        </BootGate>,
        { wrapper: TestWrapper },
      );

      // Past the no-flash delay, the gate is showing the waiting splash and
      // the children are still gated.
      await vi.advanceTimersByTimeAsync(1000);
      await waitFor(() => expect(screen.queryByTestId("app")).not.toBeInTheDocument());
      expect(screen.getByRole("status")).toBeInTheDocument();
    });
  });

  describe("TemplateEditorToolbar", () => {
    /** Undo/redo available and a live selection — everything would be enabled. */
    function fakeEditor() {
      return {
        can: () => ({ undo: () => true, redo: () => true }),
        state: { selection: { from: 0, to: 3 }, doc: { textBetween: () => "abc" } },
        on: vi.fn(),
        off: vi.fn(),
      };
    }

    function renderToolbar(editor: unknown) {
      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      return render(
        <QueryClientProvider client={queryClient}>
          {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
          <TemplateEditorToolbar editor={editor as any} deviceType="flagship" />
        </QueryClientProvider>,
      );
    }

    it("disables undo once the editor it acts on is gone", async () => {
      const { rerender } = renderToolbar(fakeEditor());
      await waitFor(() => expect(screen.getByRole("button", { name: "Undo" })).not.toBeDisabled());

      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      rerender(
        <QueryClientProvider client={queryClient}>
          <TemplateEditorToolbar editor={null} deviceType="flagship" />
        </QueryClientProvider>,
      );

      // No waitFor: an editor that has gone away must disable the buttons in
      // the same commit, not a frame later.
      expect(screen.getByRole("button", { name: "Undo" })).toBeDisabled();
    });
  });
});
