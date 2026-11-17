import { expect, type Locator } from "@playwright/test";

/** Compare rendered surfaces to the active theme, including dark mode. */
export async function expectSurfaceToken(surface: Locator, token: "card" | "popover" | "muted") {
  const colors = await surface.evaluate((element, name) => {
    const probe = document.createElement("span");
    probe.style.backgroundColor = `var(--${name})`;
    document.body.append(probe);
    const expected = getComputedStyle(probe).backgroundColor;
    probe.remove();
    return { expected, actual: getComputedStyle(element).backgroundColor };
  }, token);
  expect(colors.actual).toBe(colors.expected);
}

/** A viewport-width box can still be painted beneath the root scrollbar gutter. */
export async function expectViewportEdges(surface: Locator) {
  await expect
    .poll(() =>
      surface.evaluate((element) => {
        const bounds = element.getBoundingClientRect();
        const y = Math.min(innerHeight - 2, Math.max(2, bounds.y + bounds.height / 2));
        return [2, innerWidth - 2].map((x) => element.contains(document.elementFromPoint(x, y)));
      }),
    )
    .toEqual([true, true]);
}
