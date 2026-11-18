import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { createRef } from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { PageBuilder, type PageBuilderHandle, type PageBuilderSaveActions } from "@/components/page-builder";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

import { server } from "./mocks/server";

vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
}));

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
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

beforeAll(async () => {
  await import("@/components/tiptap-template-editor/TipTapTemplateEditor");
});

describe("PageBuilder Creator IDE seams (2.11)", () => {
  it("replaces Save and Show now with the host's actions, whose save runs the header Save", async () => {
    const puts: unknown[] = [];
    server.use(
      http.put("/api/v1/pages/page-1", async ({ request }) => {
        puts.push(await request.json());
        return HttpResponse.json({
          page: { id: "page-1", name: "Test Page", type: "template", device_type: "flagship", template: [] },
          incompatible_references: [],
        });
      }),
    );
    let received: PageBuilderSaveActions | undefined;
    render(
      <PageBuilder
        pageId="page-1"
        onClose={vi.fn()}
        saveActions={(actions) => {
          received = actions;
          return (
            <button type="button" onClick={actions.save} {...actions.anchor}>
              Publish it
            </button>
          );
        }}
      />,
      { wrapper: TestWrapper },
    );
    const publish = await screen.findByRole("button", { name: "Publish it" });
    expect(screen.queryByRole("button", { name: "Show now" })).not.toBeInTheDocument();
    expect(received?.anchor).toEqual({ "data-ai-anchor": "page-editor.save" });
    await waitFor(() => expect(screen.getByRole("textbox", { name: /page name/i })).not.toHaveValue(""));
    fireEvent.click(publish);
    await waitFor(() => expect(puts).toHaveLength(1));
  });

  it("keeps Save and Show now without the seam and reports mirroring off", async () => {
    const ref = createRef<PageBuilderHandle>();
    render(<PageBuilder ref={ref} pageId="page-1" onClose={vi.fn()} />, { wrapper: TestWrapper });
    expect(await screen.findByRole("button", { name: "Show now" })).toBeInTheDocument();
    expect(ref.current?.isMirroring()).toBe(false);
  });
});
