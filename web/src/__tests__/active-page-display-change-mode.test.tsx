// The schedule-mode "Change Page" dialog offers two independent actions as
// pressable cards: override temporarily, or turn schedule mode off.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

import { server } from "./mocks/server";

const API_BASE = "/api";

vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
  }),
}));

vi.mock("@/components/smart-link", () => ({
  default: ({ children, href, ...rest }: { children: React.ReactNode; href: string }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

import { ActivePageDisplay } from "@/components/active-page-display";

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
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

function activeScheduleResponse(overrides: Record<string, unknown> = {}) {
  return {
    page_id: "page-1",
    source: "manual",
    schedule_enabled: false,
    temporary_override: {
      active: false,
      page_id: null,
      expires_at: null,
      remaining_seconds: null,
      revert_mode: null,
      revert_page_id: null,
    },
    ...overrides,
  };
}

describe("ActivePageDisplay - change page in schedule mode", () => {
  it("turns schedule mode off from the change-page dialog", async () => {
    let patchBody: unknown = null;
    server.use(
      http.get(`${API_BASE}/schedules/active/page`, () =>
        HttpResponse.json(activeScheduleResponse({ schedule_enabled: true, source: "schedule" })),
      ),
      http.patch(`${API_BASE}/v1/boards/:boardId`, async ({ request }) => {
        patchBody = await request.json();
        return HttpResponse.json({});
      }),
    );
    const user = userEvent.setup();
    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await user.click(await screen.findByRole("button", { name: /change page/i }));
    await user.click(await screen.findByRole("button", { name: "Turn off schedule mode" }));

    await waitFor(() => expect(patchBody).toEqual({ schedule_enabled: false }));
  });
});
