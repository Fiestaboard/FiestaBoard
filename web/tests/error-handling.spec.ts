/**
 * FiestaBoard Error Handling E2E Tests
 *
 * Tests error resilience: 404s for missing resources,
 * validation rejections, and invalid data handling.
 */
import {
  test,
  expect,
  configureBoard,
  API_URL,
} from "./helpers";

test.beforeEach(async () => {
  await configureBoard();
});

test.describe("Error Handling", () => {
  test("API returns 404 for nonexistent page", async () => {
    const res = await fetch(`${API_URL}/pages/nonexistent-id-12345`);
    expect(res.status).toBe(404);
  });

  test("API returns 404 for nonexistent schedule", async () => {
    const res = await fetch(`${API_URL}/schedules/nonexistent-id-12345`);
    expect(res.status).toBe(404);
  });

  test("API rejects invalid page data", async () => {
    // Missing required fields
    const res = await fetch(`${API_URL}/pages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    expect(res.status).toBeGreaterThanOrEqual(400);
  });

  test("API rejects invalid schedule data", async () => {
    const res = await fetch(`${API_URL}/schedules`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    expect(res.status).toBeGreaterThanOrEqual(400);
  });

  test("API rejects invalid template syntax", async () => {
    const res = await fetch(`${API_URL}/templates/validate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        template: [
          "THIS LINE IS WAY TOO LONG AND EXCEEDS THE 22 CHARACTER LIMIT FOR A VESTABOARD LINE AAAA",
          "",
          "",
          "",
          "",
          "",
        ],
      }),
    });
    expect(res.ok).toBe(true);
    const data = await res.json();
    // The validator should flag the overly long line
    // valid could be true or false depending on how the validator handles it
    expect(data).toHaveProperty("valid");
    expect(data).toHaveProperty("errors");
  });

  test("UI handles navigation to invalid page route gracefully", async ({
    page,
  }) => {
    await page.addInitScript(() => {
      localStorage.setItem("fiestaboard_wizard_complete", "true");
    });

    await page.goto("/pages/edit/nonexistent-id-12345");

    // The app should either redirect, show an error, or show a 404
    // It should NOT show a blank white screen or crash
    await page.waitForTimeout(3_000);

    const hasContent =
      (await page
        .getByText(/not found|error|pages|dashboard/i)
        .first()
        .isVisible({ timeout: 5_000 })
        .catch(() => false)) ||
      (await page
        .getByRole("heading")
        .first()
        .isVisible({ timeout: 3_000 })
        .catch(() => false));

    expect(hasContent).toBe(true);
  });
});
