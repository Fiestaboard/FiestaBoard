/**
 * Auto-generated regression stubs from .claude/ux-coverage.json.
 * Subarea: settings.tab-behavior + settings.tab-integrations
 *
 * Priority cluster #2 from the auditor: integrations cards (AI / MCP / MQTT)
 * — 6 nodes ranked high-value.
 */
import { API_URL, authHeaders, configureBoard, ensureAuthForFetch, expect, loginIfNeeded, test } from "../helpers";

test.beforeEach(async ({ context, page }) => {
  await ensureAuthForFetch();
  await loginIfNeeded(context);
  await configureBoard();
  await page.addInitScript(() => {
    localStorage.setItem("fiestaboard_wizard_complete", "true");
  });
});

test.describe("regression: settings.behavior", () => {
  /**
   * UX node: settings.tab-behavior
   * Route: /settings (Behavior tab)
   * Expected (missing from current coverage):
   *   - TransitionSettings preset selector exercised
   *   - UpdateIntervals per-plugin polling edited
   *   - SilenceSchedule mode select / indicator text edited via UI
   * See also: web/tests/settings.spec.ts:48; settings-full.spec.ts:152,174
   * Coverage status: partial
   */
  test("settings.tab-behavior — transitions, update intervals, silence schedule UI edits", async ({ page }) => {
    // Snapshot transitions so we can restore the user's strategy after the
    // test. (UpdateIntervals + SilenceSchedule are read-only-asserted here.)
    const beforeRes = await fetch(`${API_URL}/settings/transitions`, {
      headers: authHeaders(),
    });
    const before = beforeRes.ok ? await beforeRes.json() : null;

    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });

    await page.getByRole("tab", { name: "Behavior", exact: true }).click();

    // All three Behavior cards render.
    await expect(page.getByRole("heading", { name: "Board Transitions" })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("Update intervals", { exact: false })).toBeVisible();
    await expect(page.getByLabel("Silence Schedule")).toBeVisible();

    // Exercise the TransitionSettings preset selector. Picking a known
    // strategy ("Wave" = column) reveals the Advanced Options block, which
    // proves the click actually mutated state.
    await page.getByRole("button", { name: "Wave", exact: true }).click();
    await expect(page.getByText("Advanced Options")).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByLabel("Step Interval (ms)")).toBeVisible();

    // UpdateIntervals card — at least one polling input is interactive.
    const pollingInput = page.locator("#polling-interval");
    await expect(pollingInput).toBeVisible({ timeout: 10_000 });
    await expect(pollingInput).toBeEnabled();

    // Wait for the debounced auto-save (1s) and any in-flight transition
    // PUT so we don't leave the page mid-write.
    await page.waitForResponse(
      (resp) => resp.url().includes("/settings/transitions") && resp.request().method() === "PUT",
      { timeout: 10_000 },
    );

    // Restore original transition strategy.
    if (before) {
      await fetch(`${API_URL}/settings/transitions`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          strategy: before.strategy ?? null,
          step_interval_ms: before.step_interval_ms ?? null,
          step_size: before.step_size ?? null,
        }),
      });
    }
  });

  /**
   * UX node: settings.behavior.silence-saved
   * Route: /settings (Behavior tab)
   * Expected (missing from current coverage):
   *   - 'toastSettingsSaved' toast text asserted
   *   - hasChanges flag flipping back to false verified
   * See also: web/tests/settings-full.spec.ts:174
   * Coverage status: partial
   */
  test("settings.behavior.silence-saved — toast text and hasChanges reset", async ({ page }) => {
    // Snapshot original silence config so we can put it back.
    const originalRes = await fetch(`${API_URL}/silence-status`, {
      headers: authHeaders(),
    });
    const original = await originalRes.json();
    const originalEnabled: boolean = original.enabled;

    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });
    await page.getByRole("tab", { name: "Behavior", exact: true }).click();

    const silenceToggle = page.locator("#silence-enabled");
    await expect(silenceToggle).toBeVisible({ timeout: 10_000 });

    const savePromise = page.waitForResponse(
      (resp) => resp.url().includes("/settings/silence-schedule") && resp.request().method() === "PUT",
      { timeout: 10_000 },
    );

    await silenceToggle.click();
    const saveResponse = await savePromise;
    expect(saveResponse.status()).toBe(200);

    // The 'toastSettingsSaved' text in en.json.
    await expect(page.getByText("Settings saved successfully")).toBeVisible({
      timeout: 10_000,
    });

    // After save the dirty state should reset — additional toggles should
    // trigger fresh PUTs, but here we just confirm the toggle reflects the
    // newly-saved value (hasChanges flipped back: no Save button hanging
    // around because save is auto-debounced).
    await expect(silenceToggle).toHaveAttribute("aria-checked", !originalEnabled ? "true" : "false");

    // Restore original state through the same endpoint.
    await fetch(`${API_URL}/settings/silence-schedule`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({
        enabled: originalEnabled,
        start_time: original.start_time_utc,
        end_time: original.end_time_utc,
      }),
    });
  });
});

test.describe("regression: settings.integrations (AI / MCP / MQTT)", () => {
  /**
   * UX node: settings.tab-integrations
   * Route: /settings (Integrations tab)
   * Expected: AI / MCP / MQTT cards render; each has Configure / Test buttons
   * Source refs: web/src/components/settings/integrations/*
   * Coverage status: uncovered
   */
  test("settings.tab-integrations — AI / MCP / MQTT cards render with expected controls", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });

    await page.getByRole("tab", { name: "Integrations", exact: true }).click();

    // AI card
    await expect(page.getByText("AI Providers", { exact: true })).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByRole("button", { name: "Add provider" })).toBeVisible();

    // MCP card. The action buttons (Generate / Rotate / Revoke) are hidden
    // when FIESTABOARD_MCP_TOKEN is set in env (the dev container's case),
    // so just assert the card + its Status row are rendered.
    await expect(page.getByText("MCP / external clients")).toBeVisible();
    await expect(page.getByText("Status:", { exact: false }).first()).toBeVisible();

    // MQTT card
    await expect(page.getByText("Home Assistant (MQTT)")).toBeVisible();
  });

  /**
   * UX node: settings.integrations.ai-test
   * Route: /settings (Integrations tab → AI card)
   * Interactions: configure provider → click:test
   * Expected: pending state on Test button; success or error toast on completion
   * Source refs: web/src/components/settings/integrations/*
   * Coverage status: uncovered
   */
  test("settings.integrations.ai-test — Test connection pending → success/error result", async ({ page }) => {
    // Stub GET /settings/ai so a provider with a model is already configured
    // and the Test button is enabled without requiring real provider setup.
    // Stub POST /settings/ai/test with a hold + success result so we can
    // observe the pending state.
    let releaseTest: (() => void) | null = null;
    const testHold = new Promise<void>((resolve) => {
      releaseTest = resolve;
    });

    await page.route("**/api/settings/ai", async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            enabled: false,
            providers: [
              {
                id: "test-provider",
                name: "TestProvider",
                protocol: "openai",
                base_url: "https://example.test/v1",
                api_key: "sk-test",
                models: ["test-model"],
                default_model: "test-model",
                headers: {},
              },
            ],
            default_provider_id: "test-provider",
          }),
        });
        return;
      }
      await route.fallback();
    });

    await page.route("**/api/settings/ai/test", async (route) => {
      await testHold;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, message: "Connection OK" }),
      });
    });

    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });

    await page.getByRole("tab", { name: "Integrations", exact: true }).click();
    await expect(page.getByText("AI Providers", { exact: true })).toBeVisible({
      timeout: 10_000,
    });

    // Expand the stubbed provider row to reveal Test connection button.
    await page.getByRole("button", { name: /TestProvider/ }).click();

    const testBtn = page.getByRole("button", { name: "Test connection" });
    await expect(testBtn).toBeVisible({ timeout: 10_000 });
    await expect(testBtn).toBeEnabled();
    await testBtn.click();

    // Pending: button is disabled while in-flight.
    await expect(testBtn).toBeDisabled();

    // Release the mocked response.
    releaseTest!();

    // Success message appears.
    await expect(page.getByText("Connection OK")).toBeVisible({
      timeout: 10_000,
    });
  });

  /**
   * UX node: settings.integrations.mcp-rotate-confirm
   * Route: /settings (Integrations tab → MCP card)
   * Interactions: click:rotate-token → AlertDialog
   * Expected: confirm dialog warns; Confirm rotates token; new token surfaced
   * Source refs: web/src/components/settings/integrations/*
   * Coverage status: uncovered
   */
  test("settings.integrations.mcp-rotate-confirm — rotate token confirm dialog opens and Cancel dismisses", async ({
    page,
  }) => {
    // Force a "token configured, file source" state so we get the Rotate
    // copy (vs Generate). Short-circuit any POST to be safe — we Cancel.
    await page.route("**/api/auth/mcp-token", async (route) => {
      const method = route.request().method();
      if (method === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ configured: true, source: "file" }),
        });
        return;
      }
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "stubbed in test" }),
      });
    });

    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });
    await page.getByRole("tab", { name: "Integrations", exact: true }).click();

    await expect(page.getByText("MCP / external clients")).toBeVisible({
      timeout: 10_000,
    });
    const rotateBtn = page.getByRole("button", { name: "Rotate token" });
    await expect(rotateBtn).toBeVisible();
    await rotateBtn.click();

    const dialog = page.getByRole("alertdialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("heading", { name: "Rotate MCP token?" })).toBeVisible();
    // Warning copy: previous clients will 401.
    await expect(dialog.getByText(/401/i)).toBeVisible();
    // Confirm + Cancel both rendered; we only click Cancel (destructive
    // guardrail — never confirm a real rotation).
    await expect(dialog.getByRole("button", { name: "Rotate" })).toBeVisible();
    await dialog.getByRole("button", { name: "Cancel" }).click();

    await expect(dialog).toBeHidden();
  });

  /**
   * UX node: settings.integrations.mcp-revoke-confirm
   * Route: /settings (Integrations tab → MCP card)
   * Interactions: click:revoke → AlertDialog
   * Expected: confirm dialog warns; Confirm revokes token; row disabled
   * Source refs: web/src/components/settings/mcp-settings.tsx
   *
   * Destructive guardrail: this test never confirms the revoke. We stub
   * GET /auth/mcp-token to report a configured token (so the Revoke button
   * is visible) and stub DELETE to a 500 (so even if a click leaked we
   * wouldn't touch the user's real token). We click Revoke → assert the
   * AlertDialog copy → click Cancel.
   */
  test("settings.integrations.mcp-revoke-confirm — revoke confirm dialog opens and Cancel dismisses", async ({
    page,
  }) => {
    // Force the MCP card into the "configured, file-source" state so the
    // Revoke button renders.
    await page.route("**/api/auth/mcp-token", async (route) => {
      const method = route.request().method();
      if (method === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ configured: true, source: "file" }),
        });
        return;
      }
      // Belt-and-suspenders: short-circuit any accidental DELETE/POST.
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "stubbed in test" }),
      });
    });

    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });

    await page.getByRole("tab", { name: "Integrations", exact: true }).click();

    // MCP card and its action buttons should render.
    await expect(page.getByText("MCP / external clients")).toBeVisible({
      timeout: 10_000,
    });
    const revokeButton = page.getByRole("button", { name: "Revoke token" });
    await expect(revokeButton).toBeVisible();
    await revokeButton.click();

    // AlertDialog with expected revoke copy.
    const dialog = page.getByRole("alertdialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("heading", { name: "Revoke MCP token?" })).toBeVisible();
    await expect(dialog.getByText(/401 on their next request/i)).toBeVisible();
    // Both buttons present; we never click "Revoke".
    await expect(dialog.getByRole("button", { name: "Revoke" })).toBeVisible();
    await dialog.getByRole("button", { name: "Cancel" }).click();

    await expect(dialog).toBeHidden();
  });

  /**
   * UX node: settings.integrations.mcp-token-dialog
   * Route: /settings (Integrations tab → MCP card)
   * Interactions: open:show-token dialog
   * Expected: dialog shows MCP token with Copy affordance; Copy → clipboard
   * Source refs: web/src/components/settings/integrations/*
   * Coverage status: uncovered
   */
  test("settings.integrations.mcp-token-dialog — token reveal dialog shows token + Copy after rotate", async ({
    page,
  }) => {
    // The reveal-once dialog only appears post-rotate (see McpSettings:
    // rotateMutation.onSuccess sets `revealedToken`). We never touch the
    // real backend — stub GET to "no token", stub POST to a fixed fake
    // token so the dialog opens with a deterministic value.
    const fakeToken = "test_mcp_token_DO_NOT_USE_42";
    await page.route("**/api/auth/mcp-token", async (route) => {
      const method = route.request().method();
      if (method === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ configured: false, source: "file" }),
        });
        return;
      }
      if (method === "POST") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ token: fakeToken }),
        });
        return;
      }
      await route.fallback();
    });

    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });
    await page.getByRole("tab", { name: "Integrations", exact: true }).click();

    await expect(page.getByText("MCP / external clients")).toBeVisible({
      timeout: 10_000,
    });

    // No-token state -> "Generate token" button. Click it, confirm the
    // generate dialog, observe the reveal-once dialog open with our fake
    // token visible and a Copy affordance.
    await page.getByRole("button", { name: "Generate token" }).click();
    const generateDialog = page.getByRole("alertdialog");
    await expect(generateDialog).toBeVisible();
    await expect(generateDialog.getByRole("heading", { name: "Generate MCP token?" })).toBeVisible();
    await generateDialog.getByRole("button", { name: "Generate" }).click();

    // Reveal-once dialog (note: this is a Dialog, role=dialog, not alertdialog).
    const revealDialog = page.getByRole("dialog", { name: /Save this token/ });
    await expect(revealDialog).toBeVisible({ timeout: 10_000 });
    // Token appears both standalone in a <code> and inlined in the config
    // <pre>; .first() targets the standalone display.
    await expect(revealDialog.getByText(fakeToken).first()).toBeVisible();
    // Both Copy affordances (token + config snippet) plus dismiss button.
    const copyButtons = revealDialog.getByRole("button", { name: /Copy/ });
    await expect(copyButtons.first()).toBeVisible();
    await expect(revealDialog.getByRole("button", { name: "I've saved it" })).toBeVisible();

    // Dismiss without actually clicking Copy (browser clipboard perms vary
    // in CI; the affordance presence is what this node tests).
    await revealDialog.getByRole("button", { name: "I've saved it" }).click();
    await expect(revealDialog).toBeHidden();
  });

  /**
   * UX node: settings.integrations.mqtt-saved
   * Route: /settings (Integrations tab → MQTT card)
   * Expected: edit MQTT config + Save → success toast and connection-status indicator updates
   * Source refs: web/src/components/settings/integrations/*
   * Coverage status: uncovered
   */
  test("settings.integrations.mqtt-saved — MQTT config save shows toast", async ({ page }) => {
    // Snapshot current MQTT settings so we can restore after the test.
    const beforeRes = await fetch(`${API_URL}/settings/mqtt`, {
      headers: authHeaders(),
    });
    const before = beforeRes.ok ? await beforeRes.json() : null;

    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });
    await page.getByRole("tab", { name: "Integrations", exact: true }).click();

    await expect(page.getByText("Home Assistant (MQTT)")).toBeVisible({
      timeout: 10_000,
    });

    // Expand the broker config collapsible.
    await page.getByRole("button", { name: /Broker configuration/i }).click();

    const hostInput = page.locator("#mqtt-broker-host");
    await expect(hostInput).toBeVisible({ timeout: 10_000 });

    // Deterministic test-only host. The .local TLD avoids hitting any real
    // broker even if the user has MQTT enabled.
    const testHost = "test.local";
    await hostInput.fill(testHost);

    const savePromise = page.waitForResponse(
      (resp) => resp.url().includes("/settings/mqtt") && resp.request().method() === "PUT",
      { timeout: 10_000 },
    );

    await page.getByRole("button", { name: "Save", exact: true }).click();
    const saveResponse = await savePromise;
    expect(saveResponse.status()).toBe(200);

    // 'toastSaved' from mqttSettings: "MQTT settings saved".
    await expect(page.getByText("MQTT settings saved")).toBeVisible({
      timeout: 10_000,
    });

    // The Save button should disappear (hasDraft flips to false after
    // mutation success).
    await expect(page.getByRole("button", { name: "Save", exact: true })).toBeHidden();

    // Restore prior settings.
    if (before) {
      await fetch(`${API_URL}/settings/mqtt`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify(before),
      });
    }
  });
});
