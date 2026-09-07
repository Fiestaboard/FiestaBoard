/**
 * Regression test for issue #1570: the validation useEffect in
 * ScheduleEntryForm was missing `t` from its dependency array. Since none of
 * the effect's other deps (pageId, startTime, endTime, ...) change on a
 * language switch, the memoized validation-error strings stayed frozen in
 * whatever locale was active when the effect last ran.
 *
 * See the header comment in active-page-display-locale-switch.test.tsx for
 * why this mocks just `@/i18n/i18next` with a tiny two-locale instance
 * (built inside the `vi.mock` factory, handed out via `vi.hoisted()`)
 * instead of `vi.unmock`-ing the app's shared 14-locale singleton: the
 * latter blew the UI Tests job's 10-minute CI budget (PR #1591, run
 * 31565310402) because v8 coverage had to instrument all 14 locale bundles
 * plus `i18next-browser-languagedetector` for the first time.
 */
import { act, render, screen, waitFor } from "@testing-library/react";
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

import { ScheduleEntryForm } from "@/components/schedule-entry-form";

const mockPages = [
  { id: "page-1", name: "Night Dashboard" },
  { id: "page-2", name: "Morning Dashboard" },
];

describe("ScheduleEntryForm - locale switch (issue #1570)", () => {
  beforeEach(async () => {
    await act(async () => {
      await i18nHolder.current!.changeLanguage("en");
    });
  });

  it("recomputes validation error messages when the language changes", async () => {
    const onSubmit = vi.fn();
    const onCancel = vi.fn();

    render(
      // No prefillPageId -> pageId starts empty -> "Please select a page" validation error.
      <ScheduleEntryForm pages={mockPages} onSubmit={onSubmit} onCancel={onCancel} prefillDayPattern="all" />,
    );

    await waitFor(() => {
      expect(screen.getByText("Please select a page")).toBeInTheDocument();
    });

    await act(async () => {
      await i18nHolder.current!.changeLanguage("es");
    });

    // Before the fix (missing `t` dep) this stayed stuck on the English
    // string because none of the effect's other deps changed on a locale switch.
    await waitFor(() => {
      expect(screen.getByText("Por favor selecciona una página")).toBeInTheDocument();
    });
    expect(screen.queryByText("Please select a page")).not.toBeInTheDocument();
  });
});
