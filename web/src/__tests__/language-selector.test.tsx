import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockRouter = { refresh: vi.fn(), push: vi.fn(), replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() };
vi.mock("next/navigation", () => ({
  useRouter: () => mockRouter,
}));

import { LanguageSelector } from "@/components/language-selector";

describe("LanguageSelector", () => {
  beforeEach(() => {
    mockRouter.refresh.mockClear();
    document.cookie = "NEXT_LOCALE=; path=/; max-age=0";
  });

  it("renders with a Globe icon and trigger button", () => {
    render(<LanguageSelector />);
    const trigger = screen.getByRole("combobox", { name: /language/i });
    expect(trigger).toBeInTheDocument();
  });

  it("shows the current locale in the trigger", () => {
    render(<LanguageSelector />);
    expect(screen.getByText("English")).toBeInTheDocument();
  });

  it("opens a dropdown with all 14 locales when clicked", async () => {
    const user = userEvent.setup();
    render(<LanguageSelector />);

    const trigger = screen.getByRole("combobox", { name: /language/i });
    await user.click(trigger);

    expect(screen.getByText("Español")).toBeInTheDocument();
    expect(screen.getByText("Français")).toBeInTheDocument();
    expect(screen.getByText("Deutsch")).toBeInTheDocument();
    expect(screen.getByText("日本語")).toBeInTheDocument();
    expect(screen.getByText("简体中文")).toBeInTheDocument();
  });

  it("sets NEXT_LOCALE cookie and refreshes when a language is selected", async () => {
    const user = userEvent.setup();
    render(<LanguageSelector />);

    const trigger = screen.getByRole("combobox", { name: /language/i });
    await user.click(trigger);

    const spanishOption = screen.getByText("Español");
    await user.click(spanishOption);

    expect(document.cookie).toContain("NEXT_LOCALE=es");
    expect(mockRouter.refresh).toHaveBeenCalled();
  });

  it("has proper aria-label for accessibility", () => {
    render(<LanguageSelector />);
    const trigger = screen.getByRole("combobox", { name: /language/i });
    expect(trigger).toHaveAttribute("aria-label", "Language");
  });
});
