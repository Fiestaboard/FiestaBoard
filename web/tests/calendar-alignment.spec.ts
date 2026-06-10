/**
 * Calendar alignment verification tests.
 *
 * Verifies that time gutter labels (12am, 1am, etc.) align with the
 * horizontal grid tick marks in the schedule calendar, on both desktop
 * and mobile viewports. Uses element bounding rects for programmatic
 * verification and captures screenshots for visual inspection.
 *
 * Run against a running dev container:
 *   npx playwright test tests/calendar-alignment.spec.ts
 *
 * With screenshots saved to playwright-test-results/:
 *   npx playwright test tests/calendar-alignment.spec.ts --reporter=list
 */
import type { Page } from "@playwright/test";

import {
  API_URL,
  configureBoard,
  createPage,
  createSchedule,
  deleteAllPages,
  deleteAllSchedules,
  expect,
  suppressWizard,
  test,
} from "./helpers";

/** Pixel tolerance for alignment (subpixel rounding, borders) */
const ALIGNMENT_TOLERANCE_PX = 2;

/** Sample first N hour groups for alignment check */
const SAMPLE_HOURS = 8;

interface AlignmentResult {
  viewport: string;
  gutterTops: number[];
  daySlotTops: number[];
  maxDrift: number;
  passed: boolean;
  details: string[];
}

async function measureCalendarAlignment(page: Page): Promise<AlignmentResult> {
  return page.evaluate(
    ({ sampleHours, tolerance }) => {
      const gutterGroups = document.querySelectorAll(
        ".schedule-calendar-container .rbc-time-gutter .rbc-timeslot-group",
      );
      const daySlots = document.querySelectorAll(".schedule-calendar-container .rbc-time-content > .rbc-day-slot");
      let daySlot: Element | null = null;
      for (const ds of daySlots) {
        const style = window.getComputedStyle(ds);
        if (style.display !== "none") {
          daySlot = ds;
          break;
        }
      }
      if (!daySlot) {
        return {
          viewport: "unknown",
          gutterTops: [],
          daySlotTops: [],
          maxDrift: Infinity,
          passed: false,
          details: ["No day slot found - calendar may not be in week view"],
        };
      }
      const dayGroups = daySlot.querySelectorAll(".rbc-timeslot-group");

      const n = Math.min(sampleHours, gutterGroups.length, dayGroups.length);
      const gutterTops: number[] = [];
      const daySlotTops: number[] = [];
      const details: string[] = [];
      let maxDrift = 0;

      for (let i = 0; i < n; i++) {
        const gr = (gutterGroups[i] as Element).getBoundingClientRect();
        const dr = (dayGroups[i] as Element).getBoundingClientRect();
        gutterTops.push(gr.top);
        daySlotTops.push(dr.top);
        const drift = Math.abs(gr.top - dr.top);
        maxDrift = Math.max(maxDrift, drift);
        details.push(
          `Hour ${i}: gutter top=${gr.top.toFixed(1)} day top=${dr.top.toFixed(1)} drift=${drift.toFixed(1)}px`,
        );
      }

      const passed = maxDrift <= tolerance;
      return {
        viewport: `${window.innerWidth}x${window.innerHeight}`,
        gutterTops,
        daySlotTops,
        maxDrift,
        passed,
        details,
      };
    },
    { sampleHours: SAMPLE_HOURS, tolerance: ALIGNMENT_TOLERANCE_PX },
  );
}

async function setupScheduleWithData(page: Page) {
  await configureBoard();
  await suppressWizard(page);
  await deleteAllSchedules();
  await deleteAllPages();

  const morningId = await createPage("Morning", ["GOOD MORNING", "", "", "", "", ""] as string[]);
  const workId = await createPage("Work", ["WORK MODE", "", "", "", "", ""]);
  const eveningId = await createPage("Evening", ["GOOD EVENING", "", "", "", "", ""]);
  const overnightId = await createPage("Overnight", ["OVERNIGHT MODE", "", "", "", "", ""]);

  await createSchedule(morningId, "06:00", "09:00", "weekdays");
  await createSchedule(workId, "09:00", "17:00", "weekdays");
  await createSchedule(eveningId, "17:00", "22:00", "all");
  await createSchedule(overnightId, "22:00", "06:00", "all"); // 10pm-6am, spans midnight

  await fetch(`${API_URL}/schedules/enabled`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled: true }),
  });
}

async function teardownSchedule() {
  await fetch(`${API_URL}/schedules/enabled`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled: false }),
  });
  await deleteAllSchedules();
  await deleteAllPages();
}

test.describe("Calendar alignment", () => {
  test.beforeEach(async ({ page }) => {
    await setupScheduleWithData(page);
  });

  test.afterEach(async () => {
    await teardownSchedule();
  });

  test("time labels align with grid ticks on desktop", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto("/schedule");
    await expect(page.getByRole("heading", { name: "Schedule", exact: true })).toBeVisible({ timeout: 15_000 });

    await page.getByRole("button", { name: "Calendar" }).click();
    await page.waitForTimeout(500);

    const calendar = page.locator(".schedule-calendar-container");
    await expect(calendar).toBeVisible({ timeout: 10_000 });
    await page.waitForTimeout(1500);

    const result = await measureCalendarAlignment(page);
    for (const d of result.details) {
       
      console.log(`  ${d}`);
    }
    expect(
      result.passed,
      `Desktop alignment failed: max drift ${result.maxDrift.toFixed(1)}px > ${ALIGNMENT_TOLERANCE_PX}px. ${result.details.join("; ")}`,
    ).toBe(true);
  });

  test("time labels align with grid ticks on mobile", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto("/schedule");
    await expect(page.getByRole("heading", { name: "Schedule", exact: true })).toBeVisible({ timeout: 15_000 });

    await page.getByRole("button", { name: "Calendar" }).click();
    await page.waitForTimeout(500);

    const calendar = page.locator(".schedule-calendar-container");
    await expect(calendar).toBeVisible({ timeout: 10_000 });
    await page.waitForTimeout(1500);

    const result = await measureCalendarAlignment(page);
    for (const d of result.details) {
       
      console.log(`  ${d}`);
    }
    expect(
      result.passed,
      `Mobile alignment failed: max drift ${result.maxDrift.toFixed(1)}px > ${ALIGNMENT_TOLERANCE_PX}px. ${result.details.join("; ")}`,
    ).toBe(true);
  });

  test("captures screenshots for visual inspection", async ({ page }) => {
    const outputDir = process.env.PLAYWRIGHT_SCREENSHOT_DIR || "playwright-test-results/calendar-screenshots";

    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto("/schedule");
    await expect(page.getByRole("heading", { name: "Schedule", exact: true })).toBeVisible({ timeout: 15_000 });

    await page.getByRole("button", { name: "Calendar" }).click();
    await page.waitForTimeout(1500);

    const calendar = page.locator(".schedule-calendar-container");
    await expect(calendar).toBeVisible({ timeout: 10_000 });

    await calendar.screenshot({
      path: `${outputDir}/calendar-desktop.png`,
    });

    await page.setViewportSize({ width: 375, height: 667 });
    await page.waitForTimeout(500);

    await calendar.screenshot({
      path: `${outputDir}/calendar-mobile.png`,
    });

    const result = await measureCalendarAlignment(page);
    expect(result.passed, `Screenshots captured but alignment check failed: ${result.details.join("; ")}`).toBe(true);
  });

  test("overnight event evening block appears in correct day column", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 960 });
    await page.goto("/schedule");
    await expect(page.getByRole("heading", { name: "Schedule", exact: true })).toBeVisible({ timeout: 15_000 });

    await page.getByRole("button", { name: "Calendar" }).click();
    await page.waitForTimeout(1500);

    const calendar = page.locator(".schedule-calendar-container");
    await expect(calendar).toBeVisible({ timeout: 10_000 });

    const placement = await page.evaluate(() => {
      const daySlots = document.querySelectorAll(".schedule-calendar-container .rbc-time-content > .rbc-day-slot");

      const results: {
        dayIndex: number;
        eventCount: number;
        eventTitles: string[];
        eventTops: number[];
        eventBottoms: number[];
      }[] = [];
      daySlots.forEach((slot, idx) => {
        const events = slot.querySelectorAll(".rbc-event");
        const titles: string[] = [];
        const tops: number[] = [];
        const bottoms: number[] = [];
        events.forEach((ev) => {
          const titleEl = ev.querySelector(".schedule-event-content .font-medium");
          titles.push(titleEl?.textContent?.trim() || "unknown");
          const rect = ev.getBoundingClientRect();
          tops.push(Math.round(rect.top));
          bottoms.push(Math.round(rect.bottom));
        });
        results.push({
          dayIndex: idx,
          eventCount: events.length,
          eventTitles: titles,
          eventTops: tops,
          eventBottoms: bottoms,
        });
      });

      const gutterGroups = document.querySelectorAll(
        ".schedule-calendar-container .rbc-time-gutter .rbc-timeslot-group",
      );
      const hourTops: number[] = [];
      gutterGroups.forEach((g) => {
        hourTops.push(Math.round((g as Element).getBoundingClientRect().top));
      });

      return { daySlots: results, hourTops };
    });

    for (const day of placement.daySlots) {
      const overnightEvents = day.eventTitles.filter((t) => t === "Overnight");
      if (overnightEvents.length > 0) {
         
        console.log(`  Day ${day.dayIndex}: ${day.eventCount} events, overnight count: ${overnightEvents.length}`);
        for (let i = 0; i < day.eventTitles.length; i++) {
           
          console.log(`    "${day.eventTitles[i]}" top=${day.eventTops[i]} bottom=${day.eventBottoms[i]}`);
        }
      }
    }

    // Hour 22 (10pm) is at index 22 in the gutter
    const hour22Top = placement.hourTops[22];
     
    console.log(`  10pm gutter line top: ${hour22Top}`);
     
    console.log(`  midnight gutter line top: ${placement.hourTops[0]}`);

    // Find "Overnight" events by proximity to expected gutter lines
    function findOvernightNearest(slot: (typeof placement.daySlots)[0], targetTop: number) {
      let bestIdx = -1;
      let bestDrift = Infinity;
      for (let i = 0; i < slot.eventTitles.length; i++) {
        if (slot.eventTitles[i] === "Overnight") {
          const drift = Math.abs(slot.eventTops[i] - targetTop);
          if (drift < bestDrift) {
            bestDrift = drift;
            bestIdx = i;
          }
        }
      }
      return { idx: bestIdx, drift: bestDrift };
    }

    // Sunday should have an evening "Overnight" block near 10pm
    const sundaySlot = placement.daySlots[0];
    const sundayEvening = findOvernightNearest(sundaySlot, hour22Top);
    expect(sundayEvening.idx, "Sunday should have an Overnight evening block near 10pm").toBeGreaterThanOrEqual(0);
     
    console.log(
      `  Sunday Overnight evening block: top=${sundaySlot.eventTops[sundayEvening.idx]}, expected ~${hour22Top}, drift=${sundayEvening.drift}px`,
    );
    expect(
      sundayEvening.drift,
      `Sunday evening block should be near 10pm line (drift=${sundayEvening.drift}px)`,
    ).toBeLessThan(30);

    // Monday should have a morning "Overnight" block near midnight
    const mondaySlot = placement.daySlots[1];
    const midnightTop = placement.hourTops[0];
    const mondayMorning = findOvernightNearest(mondaySlot, midnightTop);
    expect(mondayMorning.idx, "Monday should have an Overnight morning block near midnight").toBeGreaterThanOrEqual(0);
     
    console.log(
      `  Monday Overnight morning block: top=${mondaySlot.eventTops[mondayMorning.idx]}, expected ~${midnightTop}, drift=${mondayMorning.drift}px`,
    );
    expect(
      mondayMorning.drift,
      `Monday morning block should be near midnight line (drift=${mondayMorning.drift}px)`,
    ).toBeLessThan(30);
  });

  test("captures full calendar with cross-day (10pm-6am) events", async ({ page }) => {
    const outputDir = process.env.PLAYWRIGHT_SCREENSHOT_DIR || "playwright-test-results/calendar-screenshots";

    // Setup: replace standard schedules with an overnight schedule + one daytime for context
    await configureBoard();
    await suppressWizard(page);
    await deleteAllSchedules();
    await deleteAllPages();

    const overnightId = await createPage("Overnight", ["OVERNIGHT MODE", "", "", "", "", ""]);
    const workId = await createPage("Work", ["WORK MODE", "", "", "", "", ""]);

    await createSchedule(overnightId, "22:00", "06:00", "all"); // 10pm - 6am, spans midnight
    await createSchedule(workId, "09:00", "17:00", "weekdays");

    await fetch(`${API_URL}/schedules/enabled`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: true }),
    });

    // Desktop: larger viewport to show full calendar
    await page.setViewportSize({ width: 1440, height: 960 });
    await page.goto("/schedule");
    await expect(page.getByRole("heading", { name: "Schedule", exact: true })).toBeVisible({ timeout: 15_000 });

    await page.getByRole("button", { name: "Calendar" }).click();
    await page.waitForTimeout(1500);

    const calendar = page.locator(".schedule-calendar-container");
    await expect(calendar).toBeVisible({ timeout: 10_000 });

    await calendar.screenshot({
      path: `${outputDir}/calendar-full-desktop-crossday.png`,
    });

    // Full page to capture entire calendar (24h can be tall)
    await page.screenshot({
      path: `${outputDir}/calendar-fullpage-desktop-crossday.png`,
      fullPage: true,
    });

    // Mobile: taller viewport to show more of the calendar
    await page.setViewportSize({ width: 390, height: 900 });
    await page.waitForTimeout(500);

    await calendar.screenshot({
      path: `${outputDir}/calendar-full-mobile-crossday.png`,
    });

    await page.screenshot({
      path: `${outputDir}/calendar-fullpage-mobile-crossday.png`,
      fullPage: true,
    });

    const result = await measureCalendarAlignment(page);
    expect(
      result.passed,
      `Cross-day screenshots captured but alignment check failed: ${result.details.join("; ")}`,
    ).toBe(true);
  });
});
