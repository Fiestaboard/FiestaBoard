/**
 * Auto-generated regression stubs from .claude/ux-coverage.json.
 * Subarea: carousels (list + form + delete-confirm)
 *
 * Priority cluster #3 from the auditor: entire carousels CRUD branch is
 * untested — 11 nodes, all uncovered. Fill these early.
 *
 * Note: Carousels currently have no API helper in web/tests/helpers.ts. We
 * inline minimal fetch-based helpers below using the shared authHeaders() so
 * these stay valid under auth-enabled and auth-disabled containers alike.
 * If carousel coverage grows, promote createCarouselApi / deleteAllCarousels
 * into helpers.ts.
 */
import type { Locator, Page } from "@playwright/test";

import {
  API_URL,
  authHeaders,
  configureBoard,
  createPage,
  deleteAllPages,
  ensureAuthForFetch,
  expect,
  loginIfNeeded,
  test,
} from "../helpers";

// ---------------------------------------------------------------------------
// Inline API helpers (candidates to promote into helpers.ts)
// ---------------------------------------------------------------------------

interface CarouselApi {
  id: string;
  name: string;
  page_ids: string[];
  interval_seconds: number;
}

async function deleteAllCarousels(): Promise<void> {
  const res = await fetch(`${API_URL}/carousels`, { headers: authHeaders() });
  if (!res.ok) return;
  const data = (await res.json()) as { carousels: CarouselApi[] };
  for (const c of data.carousels) {
    await fetch(`${API_URL}/carousels/${c.id}`, {
      method: "DELETE",
      headers: authHeaders(),
    });
  }
}

async function createCarouselApi(name: string, pageIds: string[], intervalSeconds = 30): Promise<CarouselApi> {
  const res = await fetch(`${API_URL}/carousels`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      name,
      page_ids: pageIds,
      interval_seconds: intervalSeconds,
    }),
  });
  if (!res.ok) {
    throw new Error(`createCarouselApi failed: ${res.status} ${await res.text()}`);
  }
  const data = (await res.json()) as { carousel: CarouselApi };
  return data.carousel;
}

/**
 * Return the unique [data-slot="card"] element whose visible text contains
 * the given carousel name. Used to scope clicks on the inline edit pencil
 * (the only button rendered inside the card body).
 */
function carouselCard(page: Page, name: string): Locator {
  return page.locator('[data-slot="card"]', { hasText: name });
}

/**
 * Open the edit sheet for the named carousel by clicking the pencil button
 * inside its card.
 */
async function clickEditPencil(page: Page, name: string): Promise<void> {
  const card = carouselCard(page, name);
  await expect(card).toBeVisible({ timeout: 15_000 });
  // Inside the card header, the only <button> is the edit pencil (it has no
  // text node, only an svg icon child).
  await card.getByRole("button").first().click();
}

/**
 * Pick the page-picker combobox inside the CarouselForm. The form has two
 * comboboxes — interval (with accessible name "Page Duration") and the
 * add-page picker. The add-page picker has no accessible name; we identify
 * it by its placeholder/value text "Add a page...".
 */
function addPageCombobox(dialog: Locator): Locator {
  return dialog.getByRole("combobox").filter({ hasText: "Add a page..." });
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

test.beforeEach(async ({ context, page }) => {
  await ensureAuthForFetch();
  await loginIfNeeded(context);
  await configureBoard();
  await page.addInitScript(() => {
    localStorage.setItem("fiestaboard_wizard_complete", "true");
  });
  await deleteAllCarousels();
});

test.afterEach(async () => {
  await deleteAllCarousels();
  await deleteAllPages();
});

// ---------------------------------------------------------------------------
// carousels.list
// ---------------------------------------------------------------------------

test.describe("regression: carousels.list", () => {
  /**
   * UX node: carousels.list.loading
   * Route: /carousels
   * Preconditions: api:pending
   * Expected: skeleton/loader while carousels query is in flight
   * Source refs: web/src/app/carousels/page.tsx (isLoadingCarousels branch)
   */
  test("carousels.list.loading — list shows skeleton placeholder while query is pending", async ({ page }) => {
    let release: (() => void) | null = null;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route("**/api/carousels", async (route) => {
      if (route.request().method() !== "GET") return route.fallback();
      await gate;
      return route.continue();
    });

    const nav = page.goto("/carousels");

    await expect(page.locator('[data-slot="skeleton"]').first()).toBeVisible({
      timeout: 10_000,
    });

    release!();
    await nav;
    await expect(page.getByRole("heading", { name: "Carousels", exact: true })).toBeVisible({ timeout: 15_000 });
  });

  /**
   * UX node: carousels.list.empty
   * Route: /carousels
   * Preconditions: carousels:[]
   * Expected: empty-state copy + 'Create Your First Carousel' CTA visible
   * Source refs: web/src/app/carousels/page.tsx
   */
  test("carousels.list.empty — empty state shows the create-first CTA", async ({ page }) => {
    await page.goto("/carousels");
    await expect(page.getByRole("heading", { name: "Carousels", exact: true })).toBeVisible({ timeout: 15_000 });

    await expect(page.getByText("No carousels yet")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("Carousels automatically cycle through a collection of pages.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Create Your First Carousel" })).toBeVisible();
  });

  /**
   * UX node: carousels.list.with-entries
   * Route: /carousels
   * Preconditions: carousels:>=1
   * Expected: carousel rows render with name, page-count, edit affordance
   * Source refs: web/src/app/carousels/page.tsx
   */
  test("carousels.list.with-entries — rows render with name, page-count and edit pencil", async ({ page }) => {
    const pageNameA = `E2E Page A ${Date.now()}`;
    const pageNameB = `E2E Page B ${Date.now()}`;
    const pageIdA = await createPage(pageNameA);
    const pageIdB = await createPage(pageNameB);
    const name = `E2E Carousel ${Date.now()}`;
    await createCarouselApi(name, [pageIdA, pageIdB], 15);

    await page.goto("/carousels");
    await expect(page.getByRole("heading", { name: "Carousels", exact: true })).toBeVisible({ timeout: 15_000 });

    const card = carouselCard(page, name);
    await expect(card).toBeVisible({ timeout: 10_000 });

    // Row shows name as the CardTitle heading and the page-count + interval
    // summary in the description.
    await expect(card.getByRole("heading", { name })).toBeVisible();
    await expect(card.getByText(/2 pages\s*·\s*15s per page/)).toBeVisible();

    // Edit pencil is the only button rendered inside the card.
    await expect(card.getByRole("button").first()).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// carousels.form
// ---------------------------------------------------------------------------

async function openCreateSheet(page: Page): Promise<Locator> {
  const firstCta = page.getByRole("button", { name: "Create Your First Carousel" });
  if (await firstCta.isVisible().catch(() => false)) {
    await firstCta.click();
  } else {
    await page.getByRole("button", { name: "New Carousel" }).first().click();
  }
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible({ timeout: 10_000 });
  return dialog;
}

test.describe("regression: carousels.form", () => {
  /**
   * UX node: carousels.form.sheet-create
   * Route: /carousels
   * Interactions: click:new-carousel → sheet opens
   * Expected: sheet has name input, page-picker, interval control; Submit disabled until valid
   * Source refs: web/src/app/carousels/page.tsx (CarouselForm)
   */
  test("carousels.form.sheet-create — sheet opens with controls and submit-disabled-until-valid", async ({ page }) => {
    await createPage(`E2E Page ${Date.now()}`);

    await page.goto("/carousels");
    await expect(page.getByRole("heading", { name: "Carousels", exact: true })).toBeVisible({ timeout: 15_000 });

    const dialog = await openCreateSheet(page);
    await expect(dialog.getByRole("heading", { name: "New Carousel" })).toBeVisible();

    // Form controls are present.
    await expect(dialog.getByLabel("Name")).toBeVisible();
    await expect(dialog.getByText("Page Duration")).toBeVisible();
    await expect(dialog.getByText("Pages in Carousel")).toBeVisible();

    // Submit is initially disabled (empty name + no pages selected).
    const submit = dialog.getByRole("button", { name: "Create Carousel" });
    await expect(submit).toBeDisabled();

    // Type a name — still disabled (no pages added).
    await dialog.getByLabel("Name").fill("Sheet Test Carousel");
    await expect(submit).toBeDisabled();
  });

  /**
   * UX node: carousels.form.sheet-edit
   * Route: /carousels
   * Interactions: click:edit on a row → sheet opens prefilled
   * Expected: form pre-populates from entity; Delete button visible in edit mode
   * Source refs: web/src/app/carousels/page.tsx
   */
  test("carousels.form.sheet-edit — edit sheet pre-populates name and exposes Delete", async ({ page }) => {
    const pageId = await createPage(`E2E Page ${Date.now()}`);
    const name = `E2E Edit Carousel ${Date.now()}`;
    await createCarouselApi(name, [pageId], 10);

    await page.goto("/carousels");
    await clickEditPencil(page, name);

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible({ timeout: 10_000 });
    await expect(dialog.getByRole("heading", { name: "Edit Carousel" })).toBeVisible();

    await expect(dialog.getByLabel("Name")).toHaveValue(name);

    await expect(dialog.getByRole("button", { name: "Delete" })).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Update Carousel" })).toBeVisible();
  });

  /**
   * UX node: carousels.form.empty-pages-warning
   * Route: /carousels (sheet)
   * Preconditions: page-picker:no-selection
   * Expected: inline placeholder copy ('No pages added yet'); Submit disabled
   * Source refs: web/src/app/carousels/page.tsx (selectedPageIds.length === 0)
   */
  test("carousels.form.empty-pages-warning — empty pages placeholder is shown and Submit stays disabled", async ({
    page,
  }) => {
    await createPage(`E2E Page ${Date.now()}`);

    await page.goto("/carousels");
    const dialog = await openCreateSheet(page);

    await dialog.getByLabel("Name").fill("Carousel With No Pages");

    await expect(dialog.getByText("No pages added yet")).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Create Carousel" })).toBeDisabled();
  });

  /**
   * UX node: carousels.form.creating
   * Route: /carousels (sheet)
   * Preconditions: create-mutation:pending
   * Expected: Submit button shows pending state (disabled + spinner) while mutation in flight
   * Source refs: web/src/app/carousels/page.tsx (isSubmitting branch)
   */
  test("carousels.form.creating — Submit becomes disabled with spinner while POST is in flight", async ({ page }) => {
    const pageName = `E2E Page ${Date.now()}`;
    await createPage(pageName);

    let release: (() => void) | null = null;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route("**/api/carousels", async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      await gate;
      return route.continue();
    });

    await page.goto("/carousels");
    const dialog = await openCreateSheet(page);
    await dialog.getByLabel("Name").fill("Creating State Carousel");

    await addPageCombobox(dialog).click();
    await page.getByRole("option", { name: pageName }).click();

    const submit = dialog.getByRole("button", { name: "Create Carousel" });
    await expect(submit).toBeEnabled();
    await submit.click();

    await expect(submit).toBeDisabled({ timeout: 5_000 });
    await expect(submit.locator("svg.animate-spin")).toBeVisible();

    release!();
    await expect(dialog).toBeHidden({ timeout: 10_000 });
  });

  /**
   * UX node: carousels.form.create-error
   * Route: /carousels (sheet)
   * Preconditions: create-mutation:error
   * Expected: error toast; sheet remains open; input preserved
   * Source refs: web/src/app/carousels/page.tsx (createMutation onError)
   */
  test("carousels.form.create-error — failed POST shows error toast, leaves sheet open with input preserved", async ({
    page,
  }) => {
    const pageName = `E2E Page ${Date.now()}`;
    await createPage(pageName);

    await page.route("**/api/carousels", async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "boom" }),
      });
    });

    await page.goto("/carousels");
    const dialog = await openCreateSheet(page);
    const distinctName = `Preserved Name ${Date.now()}`;
    await dialog.getByLabel("Name").fill(distinctName);

    await addPageCombobox(dialog).click();
    await page.getByRole("option", { name: pageName }).click();

    await dialog.getByRole("button", { name: "Create Carousel" }).click();

    // Error toast appears (scope to the Notifications region so we don't
    // pick up the Next.js dev runtime-error overlay which mirrors the
    // thrown message).
    const toasts = page.getByLabel("Notifications alt+T");
    await expect(toasts.getByText(/Failed to create carousel|boom/i)).toBeVisible({
      timeout: 10_000,
    });

    // Sheet stays open with the typed name preserved.
    await expect(dialog).toBeVisible();
    await expect(dialog.getByLabel("Name")).toHaveValue(distinctName);
  });

  /**
   * UX node: carousels.form.updating
   * Route: /carousels (sheet)
   * Preconditions: update-mutation:pending
   * Expected: Update Carousel button disabled + spinner while PUT in flight
   * Source refs: web/src/app/carousels/page.tsx (isSubmitting branch)
   */
  test("carousels.form.updating — Update Carousel button shows pending state while PUT is in flight", async ({
    page,
  }) => {
    const pageId = await createPage(`E2E Page ${Date.now()}`);
    const name = `E2E Updating Carousel ${Date.now()}`;
    const carousel = await createCarouselApi(name, [pageId], 30);

    let release: (() => void) | null = null;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route(`**/api/carousels/${carousel.id}`, async (route) => {
      if (route.request().method() !== "PUT") return route.continue();
      await gate;
      return route.continue();
    });

    await page.goto("/carousels");
    await clickEditPencil(page, name);

    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("heading", { name: "Edit Carousel" })).toBeVisible();
    await dialog.getByLabel("Name").fill(`${name} edited`);

    const submit = dialog.getByRole("button", { name: "Update Carousel" });
    await submit.click();

    await expect(submit).toBeDisabled({ timeout: 5_000 });
    await expect(submit.locator("svg.animate-spin")).toBeVisible();

    release!();
    await expect(dialog).toBeHidden({ timeout: 10_000 });
  });

  /**
   * UX node: carousels.form.update-error
   * Route: /carousels (sheet)
   * Preconditions: update-mutation:error
   * Expected: error toast; sheet remains open; edits preserved
   * Source refs: web/src/app/carousels/page.tsx (updateMutation onError)
   */
  test("carousels.form.update-error — failed PUT shows error toast and preserves edits", async ({ page }) => {
    const pageId = await createPage(`E2E Page ${Date.now()}`);
    const name = `E2E Update Error ${Date.now()}`;
    const carousel = await createCarouselApi(name, [pageId], 30);

    await page.route(`**/api/carousels/${carousel.id}`, async (route) => {
      if (route.request().method() !== "PUT") return route.continue();
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "kaboom" }),
      });
    });

    await page.goto("/carousels");
    await clickEditPencil(page, name);

    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("heading", { name: "Edit Carousel" })).toBeVisible();
    const editedName = `${name} dirty`;
    await dialog.getByLabel("Name").fill(editedName);

    await dialog.getByRole("button", { name: "Update Carousel" }).click();

    // Scope to the Notifications region so the Next.js dev runtime-error
    // overlay (which echoes the thrown server message) doesn't collide
    // with the Sonner toast in strict mode.
    const toasts = page.getByLabel("Notifications alt+T");
    await expect(toasts.getByText(/Failed to update carousel|kaboom/i)).toBeVisible({
      timeout: 10_000,
    });

    await expect(dialog).toBeVisible();
    await expect(dialog.getByLabel("Name")).toHaveValue(editedName);
  });
});

// ---------------------------------------------------------------------------
// carousels.delete-confirm
// ---------------------------------------------------------------------------

test.describe("regression: carousels.delete-confirm", () => {
  /**
   * UX node: carousels.delete-confirm
   * Route: /carousels
   * Interactions: open edit sheet → click Delete → AlertDialog → Cancel / Confirm
   * Expected: AlertDialog title 'Delete Carousel'; Cancel keeps row; Confirm removes it and toasts
   * Source refs: web/src/app/carousels/page.tsx (deleteMutation + AlertDialog)
   *
   * Safety: this test creates the carousel it deletes, so the destructive
   * Confirm path operates only on E2E-owned data.
   */
  test("carousels.delete-confirm — Cancel keeps row; Confirm removes it with success toast", async ({ page }) => {
    const pageId = await createPage(`E2E Page ${Date.now()}`);
    const name = `E2E Delete Carousel ${Date.now()}`;
    await createCarouselApi(name, [pageId], 30);

    await page.goto("/carousels");
    await clickEditPencil(page, name);

    const sheet = page.getByRole("dialog");
    await expect(sheet).toBeVisible();
    await expect(sheet.getByRole("heading", { name: "Edit Carousel" })).toBeVisible();
    await sheet.getByRole("button", { name: "Delete" }).click();

    // The sheet closes and the AlertDialog opens.
    const alert = page.getByRole("alertdialog");
    await expect(alert).toBeVisible({ timeout: 10_000 });
    await expect(alert.getByRole("heading", { name: "Delete Carousel" })).toBeVisible();

    // ---- Cancel path: dialog closes, row remains ----
    await alert.getByRole("button", { name: "Cancel" }).click();
    await expect(alert).toBeHidden();
    await expect(carouselCard(page, name)).toBeVisible();

    // ---- Confirm path: re-open via edit sheet → Delete, then confirm ----
    await clickEditPencil(page, name);
    await expect(sheet).toBeVisible();
    await sheet.getByRole("button", { name: "Delete" }).click();
    await expect(alert).toBeVisible();

    await alert.getByRole("button", { name: "Delete" }).click();

    // Success toast + row disappears.
    await expect(page.getByText("Carousel deleted")).toBeVisible({ timeout: 10_000 });
    await expect(carouselCard(page, name)).toBeHidden({ timeout: 10_000 });
  });
});
