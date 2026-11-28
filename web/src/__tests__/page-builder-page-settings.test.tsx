/**
 * UX-7-1 (FP-2): the Inspector's Page tab settings are page content. They are
 * staged in the editor, join its unsaved changes and Save writes them; nothing
 * is written to the page when they are picked.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import { createRef } from "react";
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
      updatePage: vi.fn(),
      getBoardSettings: vi.fn(),
    },
  };
});

import { PageBuilder, type PageBuilderHandle } from "@/components/page-builder";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";
import type { Page } from "@/lib/api";
import { api } from "@/lib/api";

const page: Page = {
  id: "p1",
  revision: "page-rev",
  name: "Kitchen morning",
  type: "template",
  device_type: "flagship",
  template: ["GOOD MORNING", "", "", "", "", ""],
  duration_seconds: 300,
  created_at: new Date().toISOString(),
};

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
  vi.mocked(api.getBoardSettings).mockResolvedValue({ board_type: "black", boards: [], devices: ["flagship"] });
  vi.mocked(api.getPage).mockResolvedValue(page);
  vi.mocked(api.updatePage).mockResolvedValue({
    page: { ...page, revision: "page-rev-2" },
    incompatible_references: [],
  });
});

function renderBuilder() {
  const ref = createRef<PageBuilderHandle>();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ConfigOverridesProvider>
        <ThemeProvider attribute="class" defaultTheme="light">
          <PageBuilder ref={ref} pageId="p1" onClose={vi.fn()} />
        </ThemeProvider>
      </ConfigOverridesProvider>
    </QueryClientProvider>,
  );
  return ref;
}

describe("PageBuilder page settings (UX-7-1)", () => {
  it("stages a page duration as an unsaved edit that Save writes", async () => {
    const ref = renderBuilder();
    await screen.findByDisplayValue("Kitchen morning");
    expect(ref.current!.hasUnsavedChanges()).toBe(false);
    act(() => ref.current!.setPageSettings({ duration_seconds: 60 }));
    await waitFor(() => expect(ref.current!.hasUnsavedChanges()).toBe(true));
    expect(ref.current!.getCurrentPage()?.duration_seconds).toBe(60);
    expect(api.updatePage).not.toHaveBeenCalled();
    await act(async () => {
      await ref.current!.save();
    });
    expect(api.updatePage).toHaveBeenCalledWith("p1", expect.objectContaining({ duration_seconds: 60 }));
  });

  it("is clean again when the duration goes back to the saved one", async () => {
    const ref = renderBuilder();
    await screen.findByDisplayValue("Kitchen morning");
    act(() => ref.current!.setPageSettings({ duration_seconds: 60 }));
    await waitFor(() => expect(ref.current!.hasUnsavedChanges()).toBe(true));
    act(() => ref.current!.setPageSettings({ duration_seconds: 300 }));
    await waitFor(() => expect(ref.current!.hasUnsavedChanges()).toBe(false));
  });

  it("stages a transition the same way", async () => {
    const ref = renderBuilder();
    await screen.findByDisplayValue("Kitchen morning");
    act(() => ref.current!.setPageSettings({ transition_strategy: "row" }));
    await waitFor(() => expect(ref.current!.hasUnsavedChanges()).toBe(true));
    expect(ref.current!.getCurrentPage()?.transition_strategy).toBe("row");
    expect(api.updatePage).not.toHaveBeenCalled();
  });
});
