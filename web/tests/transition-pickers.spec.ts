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
 * now each display's Transition section in its Playback tab. Every test forces the
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
    await page.getByRole("tab", { name: "Playback", exact: true }).click();
    const section = page.getByTestId("display-transition");

    await section.getByRole("combobox", { name: "Transition", exact: true }).click();
    const option = page.getByRole("option", { name: PLUGIN_NAME, exact: true });
    await expect(option, "transition plugin missing from the display's Transition").toBeVisible({ timeout: 15_000 });
    await option.click();

    // Poll the API rather than the DOM so this asserts the value actually
    // reached the display's board.
    await expect.poll(displayStrategy, { timeout: 10_000 }).toBe(`plugin:${PLUGIN_ID}`);
  });

  test("a display's picker hides plugin options when the beta is off", async ({ page }) => {
    await setTransitionPlugins(false);
    await page.goto(`/displays/${await firstBoardId()}`);
    await page.getByRole("tab", { name: "Playback", exact: true }).click();
    const section = page.getByTestId("display-transition");

    // The built-in strategies must still be there -- only the plugins go.
    // "Wave" is the display label for the `column` strategy.
    await section.getByRole("combobox", { name: "Transition", exact: true }).click();
    await expect(page.getByRole("option", { name: /^wave/i })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("option", { name: PLUGIN_NAME, exact: true })).toHaveCount(0);
  });

  test("the display's transition plugins switch turns them on for every display", async ({ page }) => {
    await setTransitionPlugins(false);
    await page.goto(`/displays/${await firstBoardId()}`);
    await page.getByRole("tab", { name: "Playback", exact: true }).click();
    const plugins = page.getByTestId("display-transition-plugins");
    await expect(plugins).toContainText(/all displays/i, { timeout: 15_000 });

    await plugins.getByRole("switch", { name: "Transition Plugins" }).click();

    await expect.poll(pluginsEnabled, { timeout: 10_000 }).toBe(true);
    await page.getByTestId("display-transition").getByRole("combobox", { name: "Transition", exact: true }).click();
    await expect(page.getByRole("option", { name: PLUGIN_NAME, exact: true })).toBeVisible();
  });

  test("a display's step interval saves with its board", async ({ page }) => {
    await setDisplayTransition({ transition: "column", transition_step_interval_ms: null });
    await page.goto(`/displays/${await firstBoardId()}`);
    await page.getByRole("tab", { name: "Playback", exact: true }).click();

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

      // D6 (bug bash BB-E-13): on a desktop the page transition is the
      // Inspector Page tab's Transition row, not a header icon.
      const row = page.getByRole("button", { name: /^Transition/ });
      await expect(row, "per-page Transition control missing").toBeVisible();
      // UX-7-1 (FP-2): an inline menu on the row stages the choice like any
      // edit; the header's Save writes it with the page.
      const choose = async (option: string | RegExp) => {
        await row.click();
        await page.getByRole("menuitemradio", { name: option }).click();
        await expect(page.getByRole("menu")).toBeHidden();
        await page.getByRole("button", { name: "Save", exact: true }).click();
      };

      // --- set an override ---
      await choose(PLUGIN_NAME);
      await expect.poll(() => getPageStrategy(pageId), { timeout: 10_000 }).toBe(`plugin:${PLUGIN_ID}`);

      // --- it survives a reload, named on the row ---
      await page.reload();
      await expect(row).toContainText(PLUGIN_NAME);

      // --- clear it: must persist as null, not stay sticky ---
      await choose(/use the display's transition/i);

      await expect.poll(() => getPageStrategy(pageId), { timeout: 10_000 }).toBeNull();
    } finally {
      await deletePage(pageId);
    }
  });

  test("integrations badges a transition plugin and offers no enable toggle", async ({ page }) => {
    await page.goto("/integrations");

    const installed = page.getByRole("list", { name: "Installed", exact: true });
    const row = installed.getByRole("listitem").filter({ hasText: PLUGIN_NAME });
    await expect(row).toBeVisible();
    await expect(row.getByText("Transition", { exact: true })).toBeVisible();
    await row.getByRole("button").click();
    const settings = page.getByRole("complementary", { name: "Integration settings" });
    await expect(settings.getByRole("heading", { name: PLUGIN_NAME, exact: true })).toBeVisible();
    // The toggle is a no-op for transitions -- get_transition_plugin() ignores
    // the enabled flag -- so it must not be offered in the selected detail.
    // The pane's toggle is the header menu's Enabled item (BB-FC-9).
    const options = page.locator("[data-slot=page-header]").getByRole("button", { name: "Integration options" });
    await expect(row.getByRole("switch")).toHaveCount(0);
    await expect(settings.getByRole("switch")).toHaveCount(0);
    await options.click();
    await expect(page.getByRole("menuitem", { name: "README" })).toBeVisible();
    await expect(page.getByRole("menuitemcheckbox", { name: "Enabled" })).toHaveCount(0);
    await page.keyboard.press("Escape");

    // Positive control: opening a data integration still exposes its toggle.
    // Without this, the assertion above could pass if all toggles disappeared.
    const dataRow = installed.getByRole("listitem").filter({ hasText: DATA_PLUGIN_NAME });
    await expect(dataRow).toBeVisible();
    await expect(dataRow.getByText("Transition", { exact: true })).toHaveCount(0);
    await dataRow.getByRole("button").click();
    await expect(settings.getByRole("heading", { name: DATA_PLUGIN_NAME, exact: true })).toBeVisible();
    await options.click();
    await expect(page.getByRole("menuitemcheckbox", { name: "Enabled" })).toBeVisible();
  });
});
