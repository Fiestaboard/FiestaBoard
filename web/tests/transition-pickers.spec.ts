/**
 * Transition pickers (beta): the two surfaces that select a transition.
 *
 * Transition plugins shipped fully wired on the backend but with no UI to
 * select one -- a user following a plugin's SETUP guide could not apply it
 * at all (Discord report, PR #1589). These tests pin the two controls that
 * closed that gap, and assert against the *API* after each interaction
 * rather than trusting the rendered state: the bug being guarded is
 * precisely "the control exists but nothing reaches the backend".
 *
 * Every test forces the transition-plugins beta on, since both pickers hide
 * their plugin groups when it is off, and restores the prior state after.
 */
import { API_URL, authHeaders, createPage, deletePage, expect, test, waitForApi } from "./helpers";

/** A bundled transition plugin, present in every install. */
const PLUGIN_ID = "typewriter";
const PLUGIN_NAME = "Typewriter";
/** A bundled *data* plugin, used as a positive control on Integrations. */
const DATA_PLUGIN_NAME = "Date & Time";

async function setBeta(enabled: boolean): Promise<void> {
  const res = await fetch(`${API_URL}/settings/beta`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ transition_plugins_enabled: enabled }),
  });
  expect(res.ok, `failed to set beta flag to ${enabled}`).toBe(true);
}

async function getGlobalStrategy(): Promise<string | null> {
  const res = await fetch(`${API_URL}/settings/transitions`, { headers: authHeaders() });
  expect(res.ok).toBe(true);
  return (await res.json()).strategy ?? null;
}

async function setGlobalStrategy(strategy: string | null): Promise<void> {
  await fetch(`${API_URL}/settings/transitions`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ strategy }),
  });
}

async function getPageStrategy(pageId: string): Promise<string | null> {
  const res = await fetch(`${API_URL}/pages/${pageId}`, { headers: authHeaders() });
  expect(res.ok).toBe(true);
  return (await res.json()).transition_strategy ?? null;
}

test.describe("transition pickers", () => {
  let priorStrategy: string | null = null;

  test.beforeEach(async () => {
    await waitForApi();
    priorStrategy = await getGlobalStrategy();
    await setBeta(true);
  });

  test.afterEach(async () => {
    await setGlobalStrategy(priorStrategy);
    await setBeta(false);
  });

  test("global picker saves a transition plugin as plugin:<id>", async ({ page }) => {
    await page.goto("/settings");
    await page.getByRole("tab", { name: /behavior/i }).click();

    const option = page.getByRole("button", { name: PLUGIN_NAME, exact: true });
    await expect(option, "transition plugin missing from Board Transitions").toBeVisible();
    await option.click();

    // The card auto-saves on a 1s debounce; poll the API rather than the DOM
    // so this asserts the value actually reached the backend.
    await expect.poll(getGlobalStrategy, { timeout: 10_000 }).toBe(`plugin:${PLUGIN_ID}`);
  });

  test("global picker hides plugin options when the beta is off", async ({ page }) => {
    await setBeta(false);
    await page.goto("/settings");
    await page.getByRole("tab", { name: /behavior/i }).click();

    // The built-in strategies must still be there -- only the plugin group
    // goes. "Wave" is the display label for the `column` strategy.
    await expect(page.getByRole("button", { name: /^wave$/i })).toBeVisible();
    await expect(page.getByRole("button", { name: PLUGIN_NAME, exact: true })).toHaveCount(0);
  });

  test("page picker saves an override and clears it back to the global default", async ({ page }) => {
    const pageId = await createPage("Transition Picker E2E", ["HELLO"]);

    try {
      await page.goto(`/pages/edit?id=${pageId}`);

      const trigger = page.getByRole("button", { name: /transition/i }).first();
      await expect(trigger, "per-page Transition control missing").toBeVisible();

      // --- set an override ---
      await trigger.click();
      await page.getByRole("menuitemradio", { name: PLUGIN_NAME }).click();
      await page.getByRole("button", { name: /save/i }).first().click();

      await expect.poll(() => getPageStrategy(pageId), { timeout: 10_000 }).toBe(`plugin:${PLUGIN_ID}`);

      // --- it survives a reload, selected in the menu ---
      await page.reload();
      await trigger.click();
      await expect(page.getByRole("menuitemradio", { name: PLUGIN_NAME })).toHaveAttribute("aria-checked", "true");

      // --- clear it: must persist as null, not stay sticky ---
      await page.getByRole("menuitemradio", { name: /use global default/i }).click();
      await page.getByRole("button", { name: /save/i }).first().click();

      await expect.poll(() => getPageStrategy(pageId), { timeout: 10_000 }).toBeNull();
    } finally {
      await deletePage(pageId);
    }
  });

  test("integrations badges a transition plugin and offers no enable toggle", async ({ page }) => {
    await page.goto("/integrations");

    const row = page.getByRole("row").filter({ hasText: PLUGIN_NAME });
    await expect(row).toBeVisible();
    await expect(row.getByText("Transition", { exact: true })).toBeVisible();
    // The toggle is a no-op for transitions -- get_transition_plugin() ignores
    // the enabled flag -- so it must not be offered.
    await expect(row.getByRole("switch")).toHaveCount(0);

    // Positive control: a data plugin in the same table still gets its
    // toggle. Without this, the assertion above would also pass if the
    // switch selector simply stopped matching anything.
    const dataRow = page.getByRole("row").filter({ hasText: DATA_PLUGIN_NAME });
    await expect(dataRow).toBeVisible();
    await expect(dataRow.getByRole("switch")).toHaveCount(1);
    await expect(dataRow.getByText("Transition", { exact: true })).toHaveCount(0);
  });
});
