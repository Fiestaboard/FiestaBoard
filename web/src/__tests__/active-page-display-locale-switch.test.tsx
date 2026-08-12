/**
 * Regression test for issue #1570: the `activePageName` useMemo in
 * ActivePageDisplay was missing `t` from its dependency array. Because the
 * memo's other deps (activePage, activePageId, scheduleEnabled,
 * activeCollection) don't change on a language switch, the memoized
 * "Schedule gap" string stayed frozen in whatever locale was active when it
 * was first computed — even though the rest of the component (which calls
 * `t()` directly during render, unmemoized) updated immediately.
 *
 * The global test setup (src/__tests__/setup.ts) mocks `@/i18n/translations`
 * with a static English-only stub for determinism, so this test needs the
 * real react-i18next-backed hook to exercise an actual locale switch.
 *
 * IMPORTANT (perf): don't reach for `vi.unmock("@/i18n/translations")` +
 * the app's shared `@/i18n/i18next` singleton for this. That singleton
 * eagerly statically-imports all 14 locale bundles and registers
 * `i18next-browser-languagedetector` — code no other test file ever
 * executes (they're all on the mocked stub). The first time any test
 * executes it, v8 coverage has to instrument that whole surface, which was
 * enough to blow the 10-minute CI budget for the UI Tests job (PR #1591,
 * job stalled after `schedule-entry-form-locale-switch.test.tsx` /
 * `active-page-display-locale-switch.test.tsx` with zero further test
 * output for 6+ minutes before being cancelled — see run 31565310402).
 * Instead, mock just `@/i18n/i18next` with a tiny isolated i18next instance
 * carrying only the `en`/`es` bundles and no language detector, while still
 * exercising the real `useTranslations()` from `@/i18n/translations` (the
 * file with the fix under test).
 *
 * The instance is built inside the `vi.mock` factory (dynamic imports, so
 * it isn't subject to the module-hoisting order that would otherwise run
 * this factory before a same-file top-level `const` is assigned) and handed
 * back out through a `vi.hoisted()` holder so the test body can drive
 * `changeLanguage` on the exact instance the component reads from.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { i18nHolder } = vi.hoisted(() => ({ i18nHolder: {} as { current?: import("i18next").i18n } }));

vi.mock("@/i18n/i18next", async () => {
  const { default: i18next } = await import("i18next");
  const { initReactI18next } = await import("react-i18next");
  const { default: en } = await import("../../messages/en.json");
  const { default: es } = await import("../../messages/es.json");

  const instance = i18next.createInstance();
  await instance.use(initReactI18next).init({
    resources: { en: { translation: en }, es: { translation: es } },
    lng: "en",
    fallbackLng: "en",
    interpolation: { escapeValue: false, prefix: "{{", suffix: "}}" },
    returnNull: false,
    react: { useSuspense: false },
  });
  i18nHolder.current = instance;
  return { default: instance };
});

// The global test setup (src/__tests__/setup.ts) mocks `@/i18n/translations`
// with a static English-only stub for determinism. This test specifically
// exercises real locale switching, so it needs the actual react-i18next-backed
// hook instead.
vi.unmock("@/i18n/translations");

import { ActivePageDisplay } from "@/components/active-page-display";
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
    // Always start from a known locale; changeLanguage resolves synchronously
    // here since both bundles are already loaded into the test i18next
    // instance set up by the mock factory above.
    await act(async () => {
      await i18nHolder.current!.changeLanguage("en");
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
      await i18nHolder.current!.changeLanguage("es");
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
