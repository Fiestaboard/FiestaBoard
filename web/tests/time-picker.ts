import { expect, type Locator, type Page } from "@playwright/test";

/**
 * Sets a FiestaUI TimePicker (the schedule form's Start / End Time since
 * FiestaUI #444, BB-FC-7) the way a person does: open the trigger, pick the
 * hour and the minute, then close the panel with Esc. `hhmm` is 24-hour `HH:MM`; the
 * picker shows 12-hour text, so the trigger then reads e.g. "9:00 AM".
 */
export async function pickTime(page: Page, trigger: Locator, hhmm: string) {
  const [hh, mm] = hhmm.split(":");
  const hour = Number(hh);
  const hourLabel = `${hour % 12 === 0 ? 12 : hour % 12} ${hour >= 12 ? "PM" : "AM"}`;
  await trigger.click();
  const panel = page.getByRole("dialog", { name: "Choose a time", exact: true });
  await expect(panel).toBeVisible();
  await panel
    .getByRole("listbox", { name: "Hour", exact: true })
    .getByRole("option", { name: hourLabel, exact: true })
    .click();
  await panel
    .getByRole("listbox", { name: "Minute", exact: true })
    .getByRole("option", { name: mm, exact: true })
    .click();
  // Esc closes only the panel (not the sheet around it), and the trigger is
  // not clicked again: a scope like `page.getByRole("dialog")` would match the
  // open panel too.
  await page.keyboard.press("Escape");
  await expect(panel).toBeHidden();
  await expect(trigger).toContainText(`${hour % 12 === 0 ? 12 : hour % 12}:${mm} ${hour >= 12 ? "PM" : "AM"}`);
}
