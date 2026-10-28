import { API_URL, authHeaders, ensureAuthForFetch, expect, test } from "./helpers";

test("a newly switched LED panel renders canvas pixels and keeps fit modes on screen", async ({ page }) => {
  test.setTimeout(60_000);
  await ensureAuthForFetch();
  const request = async (path: string, method: string, body?: unknown) => {
    const res = await fetch(`${API_URL}${path}`, {
      method,
      headers: { "Content-Type": "application/json", ...authHeaders() },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    expect(res.ok, await res.clone().text()).toBe(true);
    return res.json();
  };
  const panel = await request("/panels", "POST", { name: "Pixel E2E", screen_diagonal_inches: 43 });
  let pageId: string | undefined;
  try {
    const ledPanel = await request(`/panels/${panel.id}`, "PATCH", { render_style: "led_matrix" });
    expect(ledPanel.cols).toBe(32);
    expect(ledPanel.rows).toBe(13);
    const created = await request("/pages", "POST", {
      name: "Pixel E2E",
      type: "template",
      device_type: "panel",
      grid_rows: ledPanel.rows,
      grid_cols: ledPanel.cols,
      template: [""],
      canvases: [{ id: "art", area: { row: 1, col: 1, rows: 1, cols: 1 }, content: { background: "#ff0000" } }],
    });
    pageId = created.id;
    const sent = await request(`/v1/boards/${panel.board_id}/message`, "POST", { page_id: pageId });
    expect(sent.sent).toBe(true);
    const frame = await request(`/panel/${panel.id}/frame`, "GET");
    const layer = frame.layers[0];
    // The screen surface centers the character grid; the first cell can
    // start below row zero. Sample inside the actual returned canvas layer.
    const sample = { x: layer.x + Math.floor(layer.width / 2) + 0.5, y: layer.y + Math.floor(layer.height / 2) + 0.5 };

    for (const mode of [null, "fill_tv", "fit_panel", "true_size"]) {
      await request(`/panels/${panel.id}`, "PATCH", { matrix_sizing: mode });
      await page.goto(`/panel/${panel.id}`);
      const matrix = page.locator('[data-slot="led-matrix-display"]');
      await expect(matrix).toHaveAttribute("data-layers", "1", { timeout: 15_000 });
      await expect(matrix).toHaveAttribute("data-matrix-width", "192");
      await expect(matrix).toHaveAttribute("data-matrix-height", "108");
      await expect
        .poll(() =>
          matrix.evaluate((el, point) => {
            const c = el.querySelector("canvas")!;
            const w = Number(el.getAttribute("data-matrix-width"));
            const h = Number(el.getAttribute("data-matrix-height"));
            return Array.from(
              c
                .getContext("2d")!
                .getImageData(Math.floor((point.x * c.width) / w), Math.floor((point.y * c.height) / h), 1, 1).data,
            ).slice(0, 3);
          }, sample),
        )
        .toEqual([255, 0, 0]);
      if (mode === null || mode === "fit_panel") {
        // Canvas contents alone can pass while the DOM clips the art off screen.
        await expect(async () => {
          const rect = await matrix.boundingBox();
          expect(rect).not.toBeNull();
          expect(rect!.x).toBeGreaterThanOrEqual(0);
          expect(rect!.y).toBeGreaterThanOrEqual(0);
          expect(rect!.x + rect!.width).toBeLessThanOrEqual(page.viewportSize()!.width + 1);
          expect(rect!.y + rect!.height).toBeLessThanOrEqual(page.viewportSize()!.height + 1);
          await expect(matrix).toBeVisible();
        }).toPass({ timeout: 10_000 });
      }
    }
  } finally {
    if (pageId) await request(`/pages/${pageId}`, "DELETE");
    await request(`/panels/${panel.id}`, "DELETE");
  }
});
