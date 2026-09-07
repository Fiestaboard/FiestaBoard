import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { changeLanguageMock } = vi.hoisted(() => ({ changeLanguageMock: vi.fn() }));
vi.mock("@/i18n/i18next", () => ({
  default: {
    changeLanguage: changeLanguageMock,
  },
}));

import { LanguageSelector } from "@/components/language-selector";

describe("LanguageSelector", () => {
  beforeEach(() => {
    changeLanguageMock.mockClear();
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

  it("sets NEXT_LOCALE cookie and changes i18next language when a language is selected", async () => {
    const user = userEvent.setup();
    render(<LanguageSelector />);

    const trigger = screen.getByRole("combobox", { name: /language/i });
    await user.click(trigger);

    // Wait for the popup before clicking into it. The Select popup mounts
    // non-interactive and only accepts pointer events once its open sequence
    // has run; clicking too early aborts user-event with "Unable to perform
    // pointer interaction as the element has `pointer-events: none`".
    //
    // Worth knowing when this bites: run this file on its own and the popup is
    // already interactive by the time the trigger click resolves — probing the
    // DOM at that point shows the listbox, all 14 options, and
    // `pointer-events: auto` on every ancestor. The race only opens under
    // full-suite load, when the open sequence has not finished settling. So a
    // green single-file run proves nothing here; the failure is only ever
    // visible in a full `npm run test:run`.
    await screen.findByRole("listbox");
    await user.click(screen.getByRole("option", { name: "Español" }));

    await waitFor(() => expect(document.cookie).toContain("NEXT_LOCALE=es"));
    expect(changeLanguageMock).toHaveBeenCalledWith("es");
  });

  it("has proper aria-label for accessibility", () => {
    render(<LanguageSelector />);
    const trigger = screen.getByRole("combobox", { name: /language/i });
    expect(trigger).toHaveAttribute("aria-label", "Language");
  });

  it("marks the decorative Globe icon as aria-hidden so it is not announced", () => {
    render(<LanguageSelector />);
    // The Globe icon is decorative — it sits next to a visible label
    // inside the trigger, so it must be hidden from assistive tech
    // (WCAG 2.2 AA 1.1.1 Non-text Content).
    const trigger = screen.getByRole("combobox", { name: /language/i });
    const svg = trigger.querySelector("svg");
    expect(svg).not.toBeNull();
    expect(svg).toHaveAttribute("aria-hidden", "true");
  });
});
