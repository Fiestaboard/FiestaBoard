/**
 * D4 (BB-E-17): a draft restored from the hub goes into the editor as unsaved
 * edits to the saved page. Save still sends the page's revision, so the live
 * page changes only on an explicit Save.
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

describe("PageBuilder applyContent (D4)", () => {
  it("puts a draft in the editor as unsaved edits and saves it against the page's revision", async () => {
    const ref = renderBuilder();
    await screen.findByDisplayValue("Kitchen morning");
    expect(ref.current!.hasUnsavedChanges()).toBe(false);
    act(() =>
      ref.current!.applyContent({
        name: "Kitchen morning (draft)",
        type: "template",
        device_type: "flagship",
        template: ["GOOD EVENING", "", "", "", "", ""],
        line_metadata: Array.from({ length: 6 }, () => ({ alignment: "center", wrap: false })),
      }),
    );
    await screen.findByDisplayValue("Kitchen morning (draft)");
    await waitFor(() => expect(ref.current!.hasUnsavedChanges()).toBe(true));
    expect(ref.current!.getCurrentPage()?.template?.[0]).toBe("GOOD EVENING");
    await act(async () => {
      await ref.current!.save();
    });
    expect(api.updatePage).toHaveBeenCalledWith(
      "p1",
      expect.objectContaining({ expected_revision: "page-rev", name: "Kitchen morning (draft)" }),
    );
  });
});
