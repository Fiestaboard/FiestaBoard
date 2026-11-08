/**
 * FiestaBoard Settings E2E Tests (Full Coverage)
 *
 * Deep settings coverage beyond the existing settings.spec.ts.
 * Tests timezone, refresh interval, output target, board type,
 * service control, silence schedule, wizard rerun, debug tools,
 * and system info.
 */
import { API_URL, configureBoard, expect, suppressWizard, test } from "./helpers";

test.beforeEach(async ({ page }) => {
  await configureBoard();
  await suppressWizard(page);
});

test.describe("Settings – Full Coverage", () => {
  test("can update timezone via API", async () => {
    // Timezone is managed via the API; verify the endpoint works correctly
    const getRes = await fetch(`${API_URL}/config/general`);
    expect(getRes.ok).toBe(true);
    const getData = await getRes.json();
    expect(getData).toHaveProperty("timezone");

    const originalTz = getData.timezone;

    // Update to a different timezone
    const putRes = await fetch(`${API_URL}/config/general`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ timezone: "America/New_York" }),
    });
    expect(putRes.ok).toBe(true);
    // PUT answers with the saved config, not a status envelope (Phase 2 slice).
    const putData = await putRes.json();
    expect(putData.timezone).toBe("America/New_York");

    // Reset to original
    await fetch(`${API_URL}/config/general`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ timezone: originalTz }),
    });
  });

  test("can update refresh interval", async () => {
    // Update via API
    const res = await fetch(`${API_URL}/settings/polling`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ interval_seconds: 60 }),
    });
    expect(res.ok).toBe(true);
    const data = await res.json();
    // Bare PollingSettings + requires_restart since the conventions pass
    // (Phase 2, Task 8).
    expect(data.interval_seconds).toBe(60);

    // Verify via GET
    const getRes = await fetch(`${API_URL}/settings/polling`);
    expect(getRes.ok).toBe(true);
    const getData = await getRes.json();
    expect(getData.interval_seconds).toBe(60);

    // Reset
    await fetch(`${API_URL}/settings/polling`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ interval_seconds: 15 }),
    });
  });

  test("can change output target", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });

    // Test via API since the UI control varies
    for (const target of ["ui", "board", "both"]) {
      const res = await fetch(`${API_URL}/settings/output`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target }),
      });
      expect(res.ok).toBe(true);
      const data = await res.json();
      // Bare OutputSettings since the conventions pass (Phase 2, Task 8).
      expect(data.target).toBe(target);
    }

    // Reset to board
    await fetch(`${API_URL}/settings/output`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target: "board" }),
    });
  });

  test("can update board type", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });

    // Test via API
    const res = await fetch(`${API_URL}/settings/board`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ board_type: "white" }),
    });
    expect(res.ok).toBe(true);
    const data = await res.json();
    // Bare BoardSettings since the conventions pass (Phase 2, Task 8).
    expect(data.board_type).toBe("white");

    // Reset
    await fetch(`${API_URL}/settings/board`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ board_type: "black" }),
    });
  });

  test("can start and stop the service", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });

    // The service status lives in Advanced → Debug Tools → System Information.
    // System's update banner can say "running" but is not a service status.
    await page.getByRole("tab", { name: "Advanced", exact: true }).click();
    const advanced = page.getByRole("tabpanel", { name: "Advanced", exact: true });
    await advanced.getByRole("button", { name: "Debug Tools", exact: true }).click();
    await advanced.getByRole("button", { name: "System Information", exact: true }).click();
    await expect(advanced.getByText(/^(Running|Stopped)$/)).toBeVisible({ timeout: 10_000 });

    const initialStatus = await fetch(`${API_URL}/status`);
    expect(initialStatus.ok).toBe(true);
    expect(typeof (await initialStatus.json()).running).toBe("boolean");

    try {
      // configureBoard points at the isolated mock board, so the display
      // loop must start successfully rather than accepting server errors.
      const startRes = await fetch(`${API_URL}/start`, { method: "POST" });
      expect(startRes.status).toBe(200);
      expect(await startRes.json()).toMatchObject({ running: true });

      const runningStatus = await fetch(`${API_URL}/status`);
      expect(runningStatus.ok).toBe(true);
      expect(await runningStatus.json()).toMatchObject({ running: true });

      const stopRes = await fetch(`${API_URL}/stop`, { method: "POST" });
      expect(stopRes.status).toBe(200);
      expect(await stopRes.json()).toMatchObject({ running: false, changed: true });

      const stoppedStatus = await fetch(`${API_URL}/status`);
      expect(stoppedStatus.ok).toBe(true);
      expect(await stoppedStatus.json()).toMatchObject({ running: false });
    } finally {
      // Later specs depend on the display loop and board-state poll, even
      // when an assertion above fails after stopping the loop.
      const restored = await fetch(`${API_URL}/start`, { method: "POST" });
      expect(restored.status).toBe(200);
      expect(await restored.json()).toMatchObject({ running: true });
    }
  });

  test("silence schedule section is visible in display Playback", async ({ page }) => {
    await page.goto("/settings?section=scheduling");
    await expect(page.getByRole("tab", { name: "Playback", exact: true })).toHaveAttribute("aria-selected", "true", {
      timeout: 15_000,
    });

    // Silence Schedule lives under the display Playback tab

    const silenceSection = page.getByText(/silence/i).first();
    await expect(silenceSection).toBeVisible({ timeout: 10_000 });

    // Verify silence-status endpoint returns expected structure
    const statusRes = await fetch(`${API_URL}/silence-status`);
    expect(statusRes.ok).toBe(true);
    const data = await statusRes.json();
    expect(data).toHaveProperty("enabled");
    expect(data).toHaveProperty("active");
    expect(data).toHaveProperty("start_time_utc");
    expect(data).toHaveProperty("end_time_utc");
  });

  test("toggling silence schedule saves without 404 (regression: #597)", async ({ page }) => {
    // Snapshot original state so we can restore it at the end
    const originalRes = await fetch(`${API_URL}/silence-status`);
    const original = await originalRes.json();
    const originalEnabled: boolean = original.enabled;

    await page.goto("/settings?section=scheduling");
    await expect(page.getByRole("tab", { name: "Playback", exact: true })).toHaveAttribute("aria-selected", "true", {
      timeout: 15_000,
    });

    // Silence toggle lives under the display Playback tab

    const silenceToggle = page.locator("#silence-enabled");
    await expect(silenceToggle).toBeVisible({ timeout: 10_000 });

    // Wait for the debounced PUT triggered by the toggle. The regression
    // (#597) was that this request 404'd because the UI was calling the
    // plugin config endpoint instead of the dedicated feature endpoint.
    const savePromise = page.waitForResponse(
      (resp) => resp.url().includes("/settings/silence-schedule") && resp.request().method() === "PUT",
      { timeout: 10_000 },
    );

    await silenceToggle.click();

    const saveResponse = await savePromise;
    expect(saveResponse.status()).toBe(200);

    // Confirm the write landed: /silence-status should now reflect the flip
    await expect
      .poll(
        async () => {
          const res = await fetch(`${API_URL}/silence-status`);
          const data = await res.json();
          return data.enabled as boolean;
        },
        { timeout: 5_000 },
      )
      .toBe(!originalEnabled);

    // Restore original state via the same endpoint the UI uses
    await fetch(`${API_URL}/settings/silence-schedule`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        enabled: originalEnabled,
        board_id: original.board_id,
        start_time: original.start_time_utc,
        end_time: original.end_time_utc,
      }),
    });
  });

  test("silence status endpoint returns current time info", async () => {
    const res = await fetch(`${API_URL}/silence-status`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("current_time_utc");
    expect(data).toHaveProperty("next_change_utc");
    expect(typeof data.enabled).toBe("boolean");
    expect(typeof data.active).toBe("boolean");
  });

  test("can navigate to run setup wizard from settings", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });

    // Setup Wizard lives under the System tab
    await page.getByRole("tab", { name: "System", exact: true }).click();

    const wizardBtn = page
      .getByRole("button", { name: /run setup wizard/i })
      .first()
      .or(page.getByText(/run setup wizard/i).first());

    await expect(wizardBtn).toBeVisible({ timeout: 10_000 });
  });

  test("debug section shows system info", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });

    // Debug Tools lives under the Advanced tab and is a collapsible
    await page.getByRole("tab", { name: "Advanced", exact: true }).click();
    await page.getByText("Debug Tools").first().click();

    // Verify Debug Tools content is now visible
    await expect(page.getByText("Debug Tools").first()).toBeVisible({
      timeout: 10_000,
    });

    // Verify system info is available via API
    const res = await fetch(`${API_URL}/debug/system-info`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("version");
  });

  test("can clear board cache from debug tools", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });

    // Debug Tools lives under the Advanced tab and is a collapsible
    await page.getByRole("tab", { name: "Advanced", exact: true }).click();
    await page.getByText("Debug Tools").first().click();

    // Find "Clear Message Cache" button
    const clearBtn = page.getByRole("button", { name: /clear.*cache/i }).first();

    if (await clearBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
      const apiResponse = page.waitForResponse(
        (r) => (r.url().includes("/debug/clear-cache") || r.url().includes("/clear-cache")) && r.status() === 200,
      );
      await clearBtn.click();
      await apiResponse;
    } else {
      // Verify via direct API call
      const res = await fetch(`${API_URL}/debug/clear-cache`, {
        method: "POST",
      });
      expect(res.ok).toBe(true);
    }
  });
});
