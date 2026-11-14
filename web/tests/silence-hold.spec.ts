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

  test("Change Page during silence says it wakes the board, and Show now writes it", async ({ page }) => {
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

    await page.waitForTimeout(2_000);

    // 2.2: Change Page ends in Show now, which shows the page right away.
    // The dialog says before the tap that it wakes the board.
    await page.getByRole("button", { name: "Change Page", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "Change Page" });
    await expect(dialog.getByTestId("change-page-silence")).toBeVisible();
    await dialog.getByRole("button", { name: /Picked At Night/ }).click();
    await dialog.getByRole("button", { name: "Show now" }).click();

    await expect.poll(activePageId, { timeout: 10_000 }).toBe(picked);
    await expect
      .poll(async () => gridToText((await getMockBoardState()).current_message)[0]?.trim(), { timeout: 15_000 })
      .toContain("NIGHTPICK");
  });
});
