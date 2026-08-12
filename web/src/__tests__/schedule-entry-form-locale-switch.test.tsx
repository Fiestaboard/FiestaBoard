/**
 * Regression test for issue #1570: the validation useEffect in
 * ScheduleEntryForm was missing `t` from its dependency array. Since none of
 * the effect's other deps (pageId, startTime, endTime, ...) change on a
 * language switch, the memoized validation-error strings stayed frozen in
 * whatever locale was active when the effect last ran.
 */
import { act, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// The global test setup (src/__tests__/setup.ts) mocks `@/i18n/translations`
// with a static English-only stub for determinism. This test specifically
// exercises real locale switching, so it needs the actual react-i18next-backed
// hook instead.
vi.unmock("@/i18n/translations");

import { ScheduleEntryForm } from "@/components/schedule-entry-form";
import i18n from "@/i18n/i18next";

const mockPages = [
  { id: "page-1", name: "Night Dashboard" },
  { id: "page-2", name: "Morning Dashboard" },
];

describe("ScheduleEntryForm - locale switch (issue #1570)", () => {
  beforeEach(async () => {
    await act(async () => {
      await i18n.changeLanguage("en");
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
      await i18n.changeLanguage("es");
    });

    // Before the fix (missing `t` dep) this stayed stuck on the English
    // string because none of the effect's other deps changed on a locale switch.
    await waitFor(() => {
      expect(screen.getByText("Por favor selecciona una página")).toBeInTheDocument();
    });
    expect(screen.queryByText("Please select a page")).not.toBeInTheDocument();
  });
});
