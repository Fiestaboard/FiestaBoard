/**
 * Regression test for issue #1586.
 *
 * `POST /pages` responds with `{ status, page }` — the new page id lives at
 * `data.page.id`. The save mutation's onSuccess read `data.id`, which is
 * always `undefined`, so for a NEWLY created page `targetPageId` was falsy
 * and every id-keyed cleanup behind `if (targetPageId)` was skipped: the
 * stale preview cache entry was never cleared and the page/preview queries
 * were never invalidated. Editing an existing page happened to work because
 * `pageId || data.id` short-circuits on the left.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PageBuilder } from "@/components/page-builder";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

import { server } from "./mocks/server";

const API_BASE = "/api";
const NEW_PAGE_ID = "created-page-42";

vi.mock("@/lib/preview-cache", async () => {
  const actual = await vi.importActual<typeof import("@/lib/preview-cache")>("@/lib/preview-cache");
  return { ...actual, clearPreviewCacheForPage: vi.fn() };
});

vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), forward: vi.fn() }),
}));

function TestWrapper({ children }: { children: React.ReactNode }) {
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

describe("PageBuilder — saving a new page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    server.use(
      http.post(`${API_BASE}/pages`, async () => {
        return HttpResponse.json({
          status: "success",
          page: {
            id: NEW_PAGE_ID,
            name: "Fresh Page",
            type: "template",
            device_type: "flagship",
            template: ["HELLO"],
            duration_seconds: 300,
            created_at: new Date().toISOString(),
          },
        });
      }),
    );
  });

  it("clears the preview cache for the id returned by the create response", async () => {
    const { clearPreviewCacheForPage } = await import("@/lib/preview-cache");
    const onSave = vi.fn();
    const user = userEvent.setup();

    render(<PageBuilder onClose={vi.fn()} onSave={onSave} />, { wrapper: TestWrapper });

    const nameInput = await screen.findByLabelText(/page name/i);
    await user.type(nameInput, "Fresh Page");

    const saveBtn = await screen.findByRole("button", { name: /save page/i });
    await user.click(saveBtn);

    // Guard: prove the create actually succeeded, so a 0-call assertion below
    // means "the id was wrong", not "the save never ran".
    await waitFor(() => expect(onSave).toHaveBeenCalled());

    expect(clearPreviewCacheForPage).toHaveBeenCalledWith(NEW_PAGE_ID);
  });
});
