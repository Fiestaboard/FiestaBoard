/**
 * Silence holds manual page changes (issues #1943, #1944) — end to end.
 *
 * Picking a page from Home while the board is silenced must save the choice
 * but leave the board alone; "Show now" is the explicit override that writes
 * it anyway. Both are asserted against the mock board's message count, not
 * against a settings echo.
 */
import {
  API_URL,
  authHeaders,
  configureBoard,
  createPage,
  deleteAllPages,
  ensureAuthForFetch,
  expect,
  getMockBoardState,
  gridToText,
  resetMockBoard,
  setActivePage,
  test,
} from "./helpers";

function hhmmUtc(offsetMinutes: number): string {
  const d = new Date(Date.now() + offsetMinutes * 60_000);
  return `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;
}

async function putSilence(body: Record<string, unknown>): Promise<void> {
  const res = await fetch(`${API_URL}/settings/silence-schedule`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`silence-schedule PUT failed: ${res.status} ${await res.text()}`);
}

async function setScheduleEnabled(enabled: boolean): Promise<void> {
  const res = await fetch(`${API_URL}/schedules/enabled`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ enabled }),
  });
  if (!res.ok) throw new Error(`setScheduleEnabled failed: ${res.status}`);
}

async function messageCount(): Promise<number> {
  return (await getMockBoardState()).message_count ?? 0;
}

async function activePageId(): Promise<string | null> {
  const res = await fetch(`${API_URL}/settings/active-page`, { headers: authHeaders() });
  return (await res.json()).page_id ?? null;
}

test.describe("Silence holds manual page changes", () => {
  let original: { enabled: boolean; start_time_utc: string; end_time_utc: string } | null = null;

  test.beforeEach(async () => {
    await ensureAuthForFetch();
    await configureBoard();
    await setScheduleEnabled(false);
    await deleteAllPages();
    const res = await fetch(`${API_URL}/settings/silence-schedule`, { headers: authHeaders() });
    original = res.ok ? await res.json() : null;
  });

  test.afterEach(async () => {
    await putSilence({
      enabled: original?.enabled ?? false,
      start_time: original?.start_time_utc ?? "22:00+00:00",
      end_time: original?.end_time_utc ?? "07:00+00:00",
    }).catch(() => {});
    await deleteAllPages().catch(() => {});
  });

  test("picking a page during silence saves it without writing; Show now writes it", async ({ page }) => {
    const before = await createPage("Before Silence", ["AWAKE", "", "", "", "", ""]);
    const picked = await createPage("Picked At Night", ["NIGHTPICK", "", "", "", "", ""]);
    await setActivePage(before);
    await expect.poll(messageCount, { timeout: 15_000 }).toBeGreaterThanOrEqual(1);

    // A window that is open now and for the next hour.
    await putSilence({
      enabled: true,
      start_time: `${hhmmUtc(-60)}+00:00`,
      end_time: `${hhmmUtc(60)}+00:00`,
      mode: "indicator",
      indicator_text: "QUIET",
    });
    await expect
      .poll(async () => (await (await fetch(`${API_URL}/silence-status`, { headers: authHeaders() })).json()).active, {
        timeout: 15_000,
      })
      .toBe(true);

    await page.goto("/");
    await expect(page.getByTestId("silence-alert")).toBeVisible({ timeout: 15_000 });

    // Let the engine paint its silence indicator, then count from there.
    await page.waitForTimeout(2_000);
    await resetMockBoard();
    const quietCount = await messageCount();

    await page.getByRole("button", { name: /Change Page/i }).first().click();
    await expect(page.getByTestId("select-page-silence")).toBeVisible();
    await page.getByText("Picked At Night").first().click();

    // The choice is saved and the toast says it is held, with the override.
    await expect.poll(activePageId, { timeout: 10_000 }).toBe(picked);
    const toast = page.locator("[data-sonner-toast]").filter({ hasText: /will show when silence ends/ });
    await expect(toast).toBeVisible();

    // ...and the board was not written.
    await page.waitForTimeout(2_000);
    expect(await messageCount(), "a page pick during silence must not reach the board").toBe(quietCount);

    // The explicit override writes the picked page.
    await toast.getByRole("button", { name: "Show now" }).click();
    await expect
      .poll(async () => gridToText((await getMockBoardState()).current_message)[0]?.trim(), { timeout: 15_000 })
      .toContain("NIGHTPICK");
  });
});
