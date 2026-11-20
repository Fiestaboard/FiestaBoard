/**
 * BB-FS-9 and BB-FS-10: shell copy and controls that drifted from Figma.
 * - FS-9 (07e `320:6520`): Language is a full-width Select with a visible
 *   "Language" field label, reading "English (US)" — not the docs-header
 *   globe chip.
 * - FS-10 (kit SkipToContent `26:798`): the skip link reads "Skip to content".
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/i18n/i18next", () => ({ default: { changeLanguage: vi.fn() } }));

import { LanguageSelector } from "@/components/language-selector";
import { SkipToContent } from "@/components/skip-to-content";

describe("BB-FS-9 Language field", () => {
  it("is labelled by a visible Language field label", () => {
    render(<LanguageSelector />);
    const trigger = screen.getByRole("combobox", { name: "Language" });
    const label = screen.getByText("Language", { selector: "label" });
    expect(label).toHaveAttribute("for", trigger.id);
  });

  it("reads English (US) and fills the width, with no globe glyph", () => {
    render(<LanguageSelector />);
    const trigger = screen.getByRole("combobox", { name: "Language" });
    expect(trigger).toHaveTextContent("English (US)");
    expect(trigger.className).toMatch(/\bw-full\b/);
    expect(trigger.querySelector("svg.lucide-globe")).toBeNull();
  });
});

describe("BB-FS-10 skip link", () => {
  it('reads "Skip to content"', () => {
    render(<SkipToContent />);
    expect(screen.getByRole("link", { name: "Skip to content" })).toHaveAttribute("href", "#main-content");
  });
});
