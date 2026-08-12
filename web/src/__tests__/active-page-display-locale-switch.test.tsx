/**
 * Regression test for issue #1570: the `activePageName` useMemo in
 * ActivePageDisplay was missing `t` from its dependency array. Because the
 * memo's other deps (activePage, activePageId, scheduleEnabled,
 * activeCollection) don't change on a language switch, the memoized
 * "Schedule gap" string stayed frozen in whatever locale was active when it
 * was first computed — even though the rest of the component (which calls
 * `t()` directly during render, unmemoized) updated immediately.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

// The global test setup (src/__tests__/setup.ts) mocks `@/i18n/translations`
// with a static English-only stub for determinism. This test specifically
// exercises real locale switching, so it needs the actual react-i18next-backed
// hook instead.
vi.unmock("@/i18n/translations");

import { ActivePageDisplay } from "@/components/active-page-display";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";
import i18n from "@/i18n/i18next";

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

describe("ActivePageDisplay - locale switch (issue #1570)", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    // Always start from a known locale; changeLanguage is synchronous here
    // because all 14 locale bundles are statically imported in i18next.ts.
    await act(async () => {
      await i18n.changeLanguage("en");
    });
  });

  it("recomputes the memoized schedule-gap name when the language changes", async () => {
    server.use(
      http.get(`${API_BASE}/schedules/active/page`, () =>
        HttpResponse.json({
          page_id: null,
          source: "schedule",
          schedule_enabled: true,
        }),
      ),
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    // English first — this is the useMemo'd `activePageName` value.
    await waitFor(() => {
      expect(screen.getByText("Schedule gap (no default page set)")).toBeInTheDocument();
    });

    // A directly-rendered (unmemoized) t() call in the same component, used
    // as a control: it MUST update to Spanish immediately, proving the
    // component did re-render on the language switch.
    expect(screen.getByText(/No page scheduled for current time/i)).toBeInTheDocument();

    await act(async () => {
      await i18n.changeLanguage("es");
    });

    // Control assertion: the unmemoized string updated to Spanish.
    await waitFor(() => {
      expect(screen.getByText(/No hay página programada para la hora actual/i)).toBeInTheDocument();
    });

    // The memoized schedule-gap name must ALSO have updated to Spanish. Before
    // the fix (missing `t` dep), this stayed stuck on the English string
    // because none of the memo's other deps changed on a locale switch.
    expect(screen.getByText("Intervalo en el horario (sin página predeterminada)")).toBeInTheDocument();
    expect(screen.queryByText("Schedule gap (no default page set)")).not.toBeInTheDocument();
  });
});
