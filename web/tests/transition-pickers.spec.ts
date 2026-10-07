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
 * Every display owns its transition (settings v6), so the "global" picker is
 * now each display's Transition section on its page. Every test forces the
 * transition-plugins beta on, since both pickers hide their plugin groups
 * when it is off, and restores the prior state after.
 */
import {
  API_URL,
  authHeaders,
  configureBoard,
  createPage,
  deletePage,
  type DisplayTransitionFields,
  expect,
  getDisplayTransition,
  setDisplayTransition,
  setTransitionPlugins,
  test,
  waitForApi,
} from "./helpers";

/** A bundled transition plugin, present in every install. */
const PLUGIN_ID = "typewriter";
const PLUGIN_NAME = "Typewriter";
/** A bundled *data* plugin, used as a positive control on Integrations. */
const DATA_PLUGIN_NAME = "Date & Time";

async function firstBoardId(): Promise<string> {
  const res = await fetch(`${API_URL}/settings/board`, { headers: authHeaders() });
  expect(res.ok).toBe(true);
  return (await res.json()).boards[0].id;
}

async function displayStrategy(): Promise<string | null> {
  return (await getDisplayTransition()).transition ?? null;
}

async function pluginsEnabled(): Promise<boolean> {
  const res = await fetch(`${API_URL}/settings/plugins`, { headers: authHeaders() });
  expect(res.ok).toBe(true);
  return (await res.json()).transition_plugins_enabled;
}

async function getPageStrategy(pageId: string): Promise<string | null> {
  const res = await fetch(`${API_URL}/pages/${pageId}`, { headers: authHeaders() });
  expect(res.ok).toBe(true);
  return (await res.json()).transition_strategy ?? null;
}

test.describe("transition pickers", () => {
  let priorTransition: DisplayTransitionFields = {};

  test.beforeEach(async () => {
    await waitForApi();
    await configureBoard();
    priorTransition = await getDisplayTransition();
    await setTransitionPlugins(true);
  });

  test.afterEach(async () => {
    await setDisplayTransition(priorTransition);
    await setTransitionPlugins(false);
  });

  test("a display's picker saves a transition plugin as plugin:<id>", async ({ page }) => {
    await page.goto(`/displays/${await firstBoardId()}`);
    const section = page.getByTestId("display-transition");

    const option = section.getByRole("radio", { name: new RegExp(PLUGIN_NAME) });
    await expect(option, "transition plugin missing from the display's Transition").toBeVisible({ timeout: 15_000 });
    await option.click();

    // Poll the API rather than the DOM so this asserts the value actually
    // reached the display's board.
    await expect.poll(displayStrategy, { timeout: 10_000 }).toBe(`plugin:${PLUGIN_ID}`);
  });

  test("a display's picker hides plugin options when the beta is off", async ({ page }) => {
    await setTransitionPlugins(false);
    await page.goto(`/displays/${await firstBoardId()}`);
    const section = page.getByTestId("display-transition");

    // The built-in strategies must still be there -- only the plugins go.
    // "Wave" is the display label for the `column` strategy.
    await expect(section.getByRole("radio", { name: /^wave/i })).toBeVisible({ timeout: 15_000 });
    await expect(section.getByRole("radio", { name: new RegExp(PLUGIN_NAME) })).toHaveCount(0);
  });

  test("the display's transition plugins switch turns them on for every display", async ({ page }) => {
    await setTransitionPlugins(false);
    await page.goto(`/displays/${await firstBoardId()}`);
    const plugins = page.getByTestId("display-transition-plugins");
    await expect(plugins).toContainText(/all displays/i, { timeout: 15_000 });

    await plugins.getByRole("switch", { name: "Transition Plugins" }).click();

    await expect.poll(pluginsEnabled, { timeout: 10_000 }).toBe(true);
    await expect(
      page.getByTestId("display-transition").getByRole("radio", { name: new RegExp(PLUGIN_NAME) }),
    ).toBeVisible();
  });

  test("a display's step interval saves with its board", async ({ page }) => {
    await setDisplayTransition({ transition: "column", transition_step_interval_ms: null });
    await page.goto(`/displays/${await firstBoardId()}`);

    const interval = page.getByRole("spinbutton", { name: "Step Interval (ms)" });
    await interval.fill("40");
    await interval.press("Enter");

    await expect
      .poll(async () => (await getDisplayTransition()).transition_step_interval_ms, { timeout: 10_000 })
      .toBe(40);
  });

  test("page picker saves an override and clears it back to the display's transition", async ({ page }) => {
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
      await page.getByRole("menuitemradio", { name: /use the display's transition/i }).click();
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
