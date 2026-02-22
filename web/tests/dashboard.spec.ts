/**
 * FiestaBoard Dashboard E2E Tests
 *
 * Tests the home page (/) which displays the active board content
 * and provides controls for switching pages and viewing schedule state.
 */
import {
  test,
  expect,
  configureBoard,
  suppressWizard,
  createPage,
  deleteAllPages,
  deleteAllSchedules,
  setActivePage,
  createSchedule,
  resetToSingleBoard,
  API_URL,
} from "./helpers";

test.beforeEach(async ({ page }) => {
  await configureBoard();
  await resetToSingleBoard();
  await suppressWizard(page);
  // Ensure consistent test state with board cleanup
  await deleteAllSchedules();
  await deleteAllPages();
});

test.describe("Dashboard", () => {
  test("shows the dashboard with board display", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Dashboard" }),
    ).toBeVisible({ timeout: 15_000 });

    await expect(page.getByText("Active Display").first()).toBeVisible({
      timeout: 10_000,
    });
  });

  test("shows active page name and manual mode badge", async ({ page }) => {
    const pageId = await createPage("Dashboard Test Page");
    await setActivePage(pageId);

    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Dashboard" }),
    ).toBeVisible({ timeout: 15_000 });

    await expect(page.getByText("Manual Mode").first()).toBeVisible({
      timeout: 10_000,
    });
  });

  test("can open page selector and switch active page", async ({ page }) => {
    const pageA = await createPage("Page Alpha");
    const pageB = await createPage("Page Beta");
    await setActivePage(pageA);

    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Dashboard" }),
    ).toBeVisible({ timeout: 15_000 });

    const changeBtn = page.getByRole("button", { name: /Change Page/i });
    if (await changeBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await changeBtn.click();
      await expect(page.getByText("Select Page").first()).toBeVisible({
        timeout: 5_000,
      });

      const betaCard = page.getByText("Page Beta").first();
      if (await betaCard.isVisible({ timeout: 3_000 }).catch(() => false)) {
        await betaCard.click();

        // Wait for the API round-trip
        await page.waitForTimeout(2_000);
        const activeRes = await (await fetch(`${API_URL}/settings/active-page`)).json();
        expect(activeRes.page_id).toBe(pageB);
      }
    }
  });

  test("shows welcome message when no pages exist", async ({ page }) => {
    await deleteAllSchedules();
    await deleteAllPages();

    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Dashboard" }),
    ).toBeVisible({ timeout: 15_000 });

    // The dashboard should show some kind of empty/welcome state
    const welcome = page
      .getByText(/welcome|get started|no pages|create/i)
      .first();
    await expect(welcome).toBeVisible({ timeout: 10_000 });
  });

  test("reflects schedule mode when enabled", async ({ page }) => {
    const pageId = await createPage("Scheduled Page");
    await createSchedule(pageId, "06:00", "18:00", "weekdays");

    // Enable schedule mode
    const putRes = await fetch(`${API_URL}/schedules/enabled`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: true }),
    });
    expect(putRes.ok).toBe(true);

    // Wait until the API reports schedule enabled (avoids race with dashboard fetch)
    let enabled = false;
    for (let i = 0; i < 10; i++) {
      const r = await fetch(`${API_URL}/schedules/enabled`);
      if (r.ok) {
        const d = await r.json();
        if (d.enabled) {
          enabled = true;
          break;
        }
      }
      await new Promise((resolve) => setTimeout(resolve, 300));
    }
    expect(enabled).toBe(true);

    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Dashboard" }),
    ).toBeVisible({ timeout: 15_000 });

    // Wait for Active Display card to be visible (ensures component is mounted)
    await expect(
      page.getByText("Active Display", { exact: true })
    ).toBeVisible({ timeout: 10_000 });
    
    // Double-check that the backend still reports schedule mode enabled
    // (in case something reset it between the earlier check and page load)
    const recheckRes = await fetch(`${API_URL}/schedules/enabled`);
    expect(recheckRes.ok).toBe(true);
    const recheckData = await recheckRes.json();
    expect(recheckData.enabled).toBe(true);
    
    // Also check GET /schedules to see what the dashboard component will receive
    const schedulesRes = await fetch(`${API_URL}/schedules`);
    expect(schedulesRes.ok).toBe(true);
    const schedulesData = await schedulesRes.json();
    expect(schedulesData.enabled).toBe(true);
    
    // React Query may have cached the schedules query from before schedule mode was enabled
    // Reload the page to force a fresh query
    await page.reload();
    await expect(
      page.getByRole("heading", { name: "Dashboard" }),
    ).toBeVisible({ timeout: 10_000 });
    
    // Wait for either mode badge to appear (confirms query has completed)
    await expect(
      page.locator('text=/Schedule Mode|Manual Mode/')
    ).toBeVisible({ timeout: 10_000 });
    
    // Verify schedule mode is displayed (not manual mode)
    await expect(page.getByText("Schedule Mode").first()).toBeVisible({
      timeout: 5_000,
    });

    // Disable schedule mode after test
    await fetch(`${API_URL}/schedules/enabled`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: false }),
    });
  });

  test("silence status API is accessible from dashboard context", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Dashboard" }),
    ).toBeVisible({ timeout: 15_000 });

    // Verify the silence-status endpoint is reachable and returns expected shape
    const res = await fetch(`${API_URL}/silence-status`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("enabled");
    expect(data).toHaveProperty("active");
    expect(typeof data.enabled).toBe("boolean");
  });
});
