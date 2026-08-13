import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { FestiveMonthsSettings } from "@/components/settings/festive-months-settings";
import { HIDE_FESTIVE_COOKIE } from "@/lib/pride";

function clearCookie() {
  document.cookie = `${HIDE_FESTIVE_COOKIE}=; path=/; max-age=0`;
}

/**
 * The switch reflects a browser cookie, which used to be read in a mount
 * effect — one of the 42 `react-hooks/set-state-in-effect` warnings in #1568.
 * That made the control render OFF and then visibly flip ON for users who had
 * opted out. It now reads the cookie in the state initializer.
 */
describe("FestiveMonthsSettings", () => {
  beforeEach(clearCookie);
  afterEach(clearCookie);

  it("shows the switch on when the hide_festive_months cookie is set", () => {
    document.cookie = `${HIDE_FESTIVE_COOKIE}=true; path=/`;
    render(<FestiveMonthsSettings />);

    expect(screen.getByRole("switch", { name: "Hide festive months" })).toBeChecked();
  });

  it("shows the switch off when the cookie is absent", () => {
    render(<FestiveMonthsSettings />);

    expect(screen.getByRole("switch", { name: "Hide festive months" })).not.toBeChecked();
  });

  it("reads the cookie before the first paint, with no off-then-on flip", () => {
    // The effect version committed `false` first. Asserting on the very first
    // committed value is what distinguishes the two implementations.
    document.cookie = `${HIDE_FESTIVE_COOKIE}=true; path=/`;
    const { container } = render(<FestiveMonthsSettings />);

    // No await, no waitFor: the initial synchronous render must already be on.
    expect(container.querySelector('[role="switch"]')).toHaveAttribute("aria-checked", "true");
  });
});
