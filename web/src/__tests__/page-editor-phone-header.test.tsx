/**
 * DD-W166 (FABLE-2652 §4): the phone's live-page header. The primary keeps its
 * full label, Save draft leaves the header for a "Save draft now" row in the
 * dock's More, and the state under the name drops its time (the full state is
 * its title and More's first line).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
  phone();
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

function phone() {
  vi.spyOn(window, "matchMedia").mockImplementation((query) => ({
    matches: ["(max-width: 639px)", "(max-width: 1023px)", "(max-width: 767px), (pointer: coarse)"].includes(query),
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

const header = () => {
  const el = document.querySelector<HTMLElement>('[data-slot="card-header"]');
  if (!el) throw new Error("no header yet");
  return el;
};
const live = (saveDraft = vi.fn()) => ({
  live: "Live on Kitchen",
  liveBoard: "Kitchen",
  saveDraft,
  draftSavedAt: new Date().toISOString(),
});

describe("Phone live-page header (DD-W166)", () => {
  it("keeps the full primary and moves Save draft out of the header", async () => {
    renderBuilder({ draftState: live() });
    const bar = await waitFor(() => {
      const el = header();
      expect(within(el).getByRole("button", { name: /Save & update board/ })).toBeVisible();
      return el;
    });
    expect(within(bar).queryByRole("button", { name: "Save draft" })).toBeNull();
  });

  it("says the state under the name without its time, the time in its title", async () => {
    renderBuilder({ draftState: live() });
    const state = await within(await waitFor(header)).findByTestId("page-editor-save-state");
    expect(state).toHaveTextContent(/^Draft saved$/);
    expect(state.getAttribute("title")).toMatch(/^Draft saved just now/);
  });

  it("offers Save draft now and the full state in the dock's More", async () => {
    const saveDraft = vi.fn();
    const user = userEvent.setup();
    renderBuilder({ draftState: live(saveDraft) });
    await waitFor(header);
    const more = await screen.findAllByRole("button", { name: "More" });
    await user.click(more[more.length - 1]);
    expect(await screen.findByTestId("more-save-state")).toHaveTextContent("Draft saved just now");
    await user.click(await screen.findByRole("button", { name: "Save draft now" }));
    expect(saveDraft).toHaveBeenCalledOnce();
  });

  it("leaves a non-live phone page's Save · Show now pair alone", async () => {
    renderBuilder();
    const bar = await waitFor(header);
    expect(await within(bar).findByRole("button", { name: "Save Page" })).toBeVisible();
    expect(within(bar).getByRole("button", { name: /Show now/ })).toBeVisible();
    expect(await within(bar).findByTestId("page-editor-save-state")).toHaveTextContent(/^Saved$/);
  });
});
