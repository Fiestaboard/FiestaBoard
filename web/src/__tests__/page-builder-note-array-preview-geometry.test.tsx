/**
 * The page editor previews a note-array page at the page's own size (#2032).
 *
 * The preview pane and the live-edit send both go through `/templates/render*`,
 * which defaults to a single 3x15 Note when the request carries no
 * `notes_wide`/`notes_tall`. A 2x1 array page therefore previewed 15 tiles wide
 * — `{{filled:-}}` stopped halfway — while the same page reached the physical
 * board at its full 30, because the page send path forwards the geometry.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PageBuilder } from "@/components/page-builder";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";
import type { BoardSettings, Page } from "@/lib/api";
import { api } from "@/lib/api";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual("@/lib/api");
  return {
    ...actual,
    api: {
      ...(actual as { api: object }).api,
      renderTemplate: vi.fn(),
      renderTemplateLive: vi.fn(),
      getTemplateVariables: vi.fn(),
      getPage: vi.fn(),
      getBoardSettings: vi.fn(),
    },
  };
});

function TestWrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <ConfigOverridesProvider>
        <ThemeProvider attribute="class" defaultTheme="light">
          {children}
        </ThemeProvider>
      </ConfigOverridesProvider>
    </QueryClientProvider>
  );
}

const boardSettings: BoardSettings = {
  board_type: "black",
  boards: [
    {
      id: "board-1",
      name: "Wide Array",
      device_type: "note_array",
      board_color: "black",
      enabled: true,
      api_mode: "cloud",
      host: "",
      local_api_key: "",
      cloud_key: "",
      note_array_token: "***",
      notes_wide: 2,
      notes_tall: 1,
    },
  ],
  devices: ["note_array"],
};

const wideArrayPage: Page = {
  id: "page-1",
  name: "Wide Fill",
  type: "template",
  device_type: "note_array",
  notes_wide: 2,
  notes_tall: 1,
  template: ["{{filled:-}}", "", ""],
  line_metadata: [
    { alignment: "left", wrap: false },
    { alignment: "left", wrap: false },
    { alignment: "left", wrap: false },
  ],
  duration_seconds: 30,
  created_at: "2026-01-01T00:00:00Z",
};

describe("PageBuilder note-array preview geometry", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(api.getTemplateVariables).mockResolvedValue({
      variables: {},
      max_lengths: {},
      colors: {},
      symbols: [],
      filters: [],
      formatting: {},
      syntax_examples: {},
    });
    vi.mocked(api.renderTemplate).mockResolvedValue({
      rendered: "-".repeat(30),
      lines: ["-".repeat(30), " ".repeat(30), " ".repeat(30)],
      line_count: 3,
    });
    vi.mocked(api.getBoardSettings).mockResolvedValue(boardSettings);
    vi.mocked(api.getPage).mockResolvedValue(wideArrayPage);
  });

  it("passes the page's notes_wide and notes_tall to the preview render", async () => {
    render(<PageBuilder pageId="page-1" onClose={vi.fn()} onSave={vi.fn()} />, { wrapper: TestWrapper });

    await waitFor(
      () => {
        const last = vi.mocked(api.renderTemplate).mock.calls.at(-1);
        expect(last).toBeTruthy();
        const [, , deviceType, notesWide, notesTall] = last!;
        expect(deviceType).toBe("note_array");
        expect(notesWide).toBe(2);
        expect(notesTall).toBe(1);
      },
      { timeout: 5000 },
    );
  });
});
