/**
 * The desktop editor header (BB-E-13, BB-E-23; Figma 53:137378) and its
 * guard (BB-E-19; 306:32302). D5/D6 by Figma + Jev (program DESIGN-DELTAS).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual("@/lib/api");
  return {
    ...actual,
    api: {
      ...(actual as { api: object }).api,
      renderTemplate: vi.fn(),
      getTemplateVariables: vi.fn(),
      getPage: vi.fn(),
      getBoardSettings: vi.fn(),
    },
  };
});

import { PageBuilder } from "@/components/page-builder";
import { changedLinesSummary } from "@/components/page-editor-shell";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";
import type { BoardSettings, Page } from "@/lib/api";
import { api } from "@/lib/api";

const boards: BoardSettings = {
  board_type: "black",
  boards: [
    {
      id: "kitchen",
      name: "Kitchen",
      device_type: "flagship",
      board_color: "black",
      enabled: true,
      api_mode: "local",
      host: "192.168.1.100",
      local_api_key: "k",
      cloud_key: "",
    },
  ],
  devices: ["flagship"],
};

const page: Page = {
  id: "p1",
  revision: "r1",
  name: "Kitchen morning",
  type: "template",
  device_type: "flagship",
  template: ["GOOD MORNING", "", "", "", "", ""],
  duration_seconds: 300,
  created_at: "2026-11-17T17:00:00Z",
  updated_at: "2026-11-17T18:05:00Z",
};

function renderBuilder(props: Partial<React.ComponentProps<typeof PageBuilder>> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ConfigOverridesProvider>
        <ThemeProvider attribute="class" defaultTheme="light">
          <PageBuilder pageId="p1" embedded onClose={vi.fn()} {...props} />
        </ThemeProvider>
      </ConfigOverridesProvider>
    </QueryClientProvider>,
  );
}

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
  vi.mocked(api.renderTemplate).mockResolvedValue({ rendered: "", lines: [], line_count: 0 });
  vi.mocked(api.getBoardSettings).mockResolvedValue(boards);
  vi.mocked(api.getPage).mockResolvedValue(page);
});

const savedTime = new Date(page.updated_at!).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

describe("Desktop editor header (BB-E-13)", () => {
  it("states type, size, display and save state in the mono meta line", async () => {
    renderBuilder();
    await screen.findByDisplayValue("Kitchen morning");
    expect(await screen.findByTestId("page-editor-meta")).toHaveTextContent(
      `Flagship 22 × 6 · Kitchen · Saved ${savedTime}`,
    );
  });

  it("carries the IDE's live and draft state, with Discard for a restored draft", async () => {
    const onDiscard = vi.fn();
    renderBuilder({ draftState: { live: "Live on Kitchen", label: "Draft restored", onDiscard } });
    await screen.findByDisplayValue("Kitchen morning");
    const meta = await screen.findByTestId("page-editor-meta");
    expect(meta).toHaveTextContent("Flagship 22 × 6 · Kitchen · Live on Kitchen · Draft restored");
    within(meta).getByRole("button", { name: "Discard" }).click();
    expect(onDiscard).toHaveBeenCalledOnce();
  });

  it("keeps Transition and Delete out of the header (D6) and draws 40 px buttons", async () => {
    renderBuilder();
    await screen.findByDisplayValue("Kitchen morning");
    expect(screen.queryByRole("button", { name: "Page transition" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Delete Page" })).toBeNull();
    expect(screen.getByRole("button", { name: "Export Page" })).toHaveClass("h-10");
    expect(screen.getByRole("button", { name: "Save Page" })).toHaveClass("h-10");
  });

  it("keeps the save state whole when the meta truncates (FABLE-2583)", async () => {
    renderBuilder({ draftState: { label: "Draft restored", onDiscard: vi.fn() } });
    await screen.findByDisplayValue("Kitchen morning");
    const meta = await screen.findByTestId("page-editor-meta");
    const state = within(meta).getByText(/Draft restored/);
    expect(state).toHaveClass("shrink-0");
    expect(within(meta).getByText("Flagship 22 × 6 · Kitchen")).toHaveClass("truncate");
  });

  it("has one keyboard-shortcuts entry, the header's (D5)", async () => {
    renderBuilder();
    await screen.findByDisplayValue("Kitchen morning");
    expect(screen.getAllByRole("button", { name: /shortcuts/i })).toHaveLength(1);
  });

  it("names the page with an h1 (BB-E-23)", async () => {
    renderBuilder();
    await screen.findByDisplayValue("Kitchen morning");
    expect(screen.getByRole("heading", { level: 1, name: "Kitchen morning" })).toBeInTheDocument();
  });
});

describe("Discard guard summary (BB-E-19)", () => {
  it("lists the changed lines, 1-based, with their text", () => {
    const summary = changedLinesSummary(
      ["GOOD MORNING", "{{weather.temp}}°", "", "N JUDAH"],
      ["GOOD MORNING", "", "", "N JUDAH 4 MIN"],
      "2026-11-17T18:05:00Z",
    );
    expect(summary.count).toBe(2);
    expect(summary.lines).toEqual([
      { line: 2, text: "weather.temp°" },
      { line: 4, text: "N JUDAH" },
    ]);
    expect(summary.since).toBe(savedTime);
  });

  it("shows at most three lines but counts them all", () => {
    const summary = changedLinesSummary(["A", "B", "C", "D"], [], null);
    expect(summary.count).toBe(4);
    expect(summary.lines).toHaveLength(3);
    expect(summary.since).toBeNull();
  });
});
