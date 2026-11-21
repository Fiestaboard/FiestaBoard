import { getViolations, injectAxe } from "axe-playwright";

import { configureBoard, expect, suppressWizard, test } from "../helpers";

const sections = [
  ["network", "Network"],
  ["language-time", "Language & time"],
  ["system", "System & backups"],
  ["ai-provider", "AI provider"],
  ["fiestabot", "FiestaBot"],
  ["appearance", "Appearance"],
  ["accessibility", "Accessibility"],
] as const;

const configuredAi = {
  enabled: true,
  approval_mode: "ask",
  max_model_calls: null,
  max_tool_calls: null,
  default_provider_id: "parity-ollama",
  providers: [
    {
      id: "parity-ollama",
      name: "Ollama",
      protocol: "openai",
      base_url: "http://localhost:11434/v1",
      api_key: "",
      models: ["llama3.1:8b"],
      default_model: "llama3.1:8b",
    },
    {
      id: "parity-openai",
      name: "OpenAI",
      protocol: "openai",
      base_url: "https://api.openai.com/v1",
      api_key: "***",
      models: ["gpt-4.1"],
      default_model: "gpt-4.1",
    },
  ],
};

for (const width of [390, 768, 1280]) {
  for (const theme of ["light", "dark"] as const) {
    test(`Settings sections fit ${width}px in ${theme}`, async ({ page }, testInfo) => {
      test.setTimeout(120_000);
      await configureBoard();
      await suppressWizard(page);
      await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
      await page.setViewportSize({ width, height: 900 });
      await page.addInitScript((value) => localStorage.setItem("theme", value), theme);
      // Exercise supported configured controls without changing the hub's Wi-Fi
      // or contacting an AI provider. Unconfigured readiness has unit coverage.
      for (const [path, method, json] of [
        ["/api/network/wifi/capability", "GET", { available: true, reason: null }],
        [
          "/api/network/wifi/status",
          "GET",
          {
            connected: true,
            ssid: "Home 5G",
            ip_address: "192.168.1.50",
            gateway: "192.168.1.1",
            signal: 85,
            internet_reachable: true,
          },
        ],
        ["/api/network/wifi/scan", "POST", [{ ssid: "Home 5G", signal: 85, security: "WPA2", in_use: true }]],
        ["/api/network/wifi/saved", "GET", [{ name: "Home 5G", autoconnect: true }]],
        ["/api/settings/ai", "GET", configuredAi],
      ] as const) {
        await page.route(`**${path}`, async (route) => {
          expect(route.request().method()).toBe(method);
          await route.fulfill({ json });
        });
      }
      await page.route("**/api/settings/ai/test", async (route) => {
        expect(route.request().method()).toBe("POST");
        expect(route.request().postDataJSON()).toEqual({
          provider_id: "parity-ollama",
          provider: configuredAi.providers[0],
        });
        await route.fulfill({
          json: { ok: true, message: "Connected. Model replied: ok", model_used: "llama3.1:8b" },
        });
      });
      for (const [section, title] of sections) {
        await page.goto(`/settings/${section}`);
        const detail = page.getByRole("region", { name: title, exact: true });
        await expect(detail).toBeVisible();
        await expect(detail.locator('[data-slot="skeleton"]')).toHaveCount(0);
        let captureState: string = section;
        if (section === "network") {
          captureState = "network-connected";
          await expect(detail.getByText("Home 5G", { exact: true })).toHaveCount(3);
          await expect(detail.getByText("85%", { exact: true })).toBeVisible();
          await expect(detail.getByText("Internet reachable", { exact: true })).toBeVisible();
          await expect(detail.getByRole("button", { name: "Rescan", exact: true })).toBeEnabled();
        } else if (section === "system") {
          // The desktop Settings index can leave a narrow detail pane even
          // above the viewport's sm breakpoint. Both backup actions must fit
          // their content row without consuming the card's inset.
          for (const name of ["Export backup", "Import backup…"]) {
            const action = detail.getByRole("button", { name, exact: true });
            await expect(action).toBeVisible();
            expect(
              await action.evaluate((button) => {
                const bounds = button.getBoundingClientRect();
                const content = button.parentElement!.getBoundingClientRect();
                return bounds.left >= content.left - 1 && bounds.right <= content.right + 1;
              }),
              `${name} stays inside its padded content row`,
            ).toBe(true);
          }
        } else if (section === "ai-provider") {
          captureState = "ai-provider-configured";
          const ollamaToggle = detail.getByRole("button", { name: /^Ollama\b/ });
          const openaiToggle = detail.getByRole("button", { name: /^OpenAI\b/ });
          for (const toggle of [ollamaToggle, openaiToggle]) {
            await expect(toggle).toBeVisible();
            if ((await toggle.getAttribute("aria-expanded")) !== "true") await toggle.click();
          }
          await expect(detail.locator("#address-parity-ollama")).toHaveValue("http://localhost:11434/v1");
          await expect(detail.locator("#default-parity-ollama")).toHaveValue("llama3.1:8b");
          await expect(detail.getByText("Prompts go to http://localhost:11434", { exact: true })).toBeVisible();
          await expect(detail.getByText("Prompts go to https://api.openai.com", { exact: true })).toBeVisible();
          const cloudKey = detail.getByLabel("API Key", { exact: true });
          await expect(cloudKey).toHaveAttribute("type", "password");
          await expect(cloudKey).toHaveValue("***");
          const ollama = detail
            .locator('[data-slot="collapsible"]')
            .filter({ has: page.getByRole("button", { name: /^Ollama\b/ }) });
          await ollama.getByRole("button", { name: "Test connection", exact: true }).click();
          await expect(ollama.getByText("Connected. Model replied: ok", { exact: true })).toBeVisible();
        } else if (section === "fiestabot") {
          captureState = "fiestabot-ready";
          await expect(detail.getByRole("button", { name: "Open FiestaBot", exact: true })).toBeEnabled();
          await expect(detail.getByRole("link", { name: "Set up AI provider", exact: true })).toHaveCount(0);
        }
        await expect
          .poll(() => page.locator("html").evaluate((html) => html.classList.contains("dark")))
          .toBe(theme === "dark");
        // Visibility can precede the kit's header and outlet entrance fades.
        // Audit final colors and capture the settled shell at each destination.
        await page.evaluate(async () => {
          await document.fonts.ready;
          const finiteAnimations = document
            .getAnimations()
            .filter((animation) => Number.isFinite(animation.effect?.getComputedTiming().endTime ?? Infinity));
          await Promise.all(finiteAnimations.map((animation) => animation.finished.catch(() => {})));
          // Expanding and testing a provider scrolls its controls into view.
          // Restore the origin so fixed chrome belongs at the image's top.
          document.scrollingElement?.scrollTo({ top: 0, left: 0, behavior: "instant" });
          for (const element of document.querySelectorAll<HTMLElement>("*")) {
            if (!element.checkVisibility()) continue;
            const style = getComputedStyle(element);
            if (/(auto|scroll)/.test(`${style.overflowX} ${style.overflowY}`))
              element.scrollTo({ top: 0, left: 0, behavior: "instant" });
          }
          await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
        });
        await expect
          .poll(() =>
            detail.evaluate((element) => {
              let opacity = 1;
              for (let node: Element | null = element; node; node = node.parentElement) {
                opacity *= Number(getComputedStyle(node).opacity);
              }
              return opacity;
            }),
          )
          .toBe(1);
        if (width < 768) {
          await expect(page.getByRole("link", { name: "Settings", exact: true })).toHaveAttribute("href", "/settings");
          await expect(page.locator('[data-slot="settings-index"]')).toHaveCount(0);
        } else {
          // A row's name is its title, then the value it reads (07e: "Appearance System").
          const rowName = new RegExp(`^${title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?![a-z])`);
          await expect(page.getByRole("link", { name: rowName })).toHaveAttribute("aria-current", "page");
        }
        // Classic vertical scrollbars reduce the content viewport. Assert no
        // horizontal overflow against that viewport rather than window width.
        await expect
          .poll(() =>
            page.evaluate(
              () =>
                Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) -
                document.documentElement.clientWidth,
            ),
          )
          .toBeLessThanOrEqual(0);
        await injectAxe(page);
        const violations = await getViolations(page, '[data-slot="settings-detail"]', {
          runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] },
          // axe disables this WCAG 2.2 AA rule by default; browser layout is available here.
          rules: { "target-size": { enabled: true } },
        });
        expect(
          violations,
          `Settings ${section} ${width} ${theme} violations:\n${JSON.stringify(violations, null, 2)}`,
        ).toEqual([]);
        await page.screenshot({
          path: testInfo.outputPath(`impl-settings-${captureState}-${width}-${theme}.png`),
          fullPage: true,
          animations: "disabled",
        });
      }
    });
  }
}
