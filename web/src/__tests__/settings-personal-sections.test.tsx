import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import fs from "fs";
import { http, HttpResponse } from "msw";
import path from "path";
import { describe, expect, it } from "vitest";

import { AccessibilitySettings } from "@/components/settings/accessibility-settings";
import { AppearanceSettings } from "@/components/settings/appearance-settings";
import { ThemeProvider } from "@/hooks/use-theme";
import { locales } from "@/i18n/config";

import { server } from "./mocks/server";

it("saves theme in this browser", async () => {
  localStorage.setItem("theme", "light");
  render(
    <ThemeProvider>
      <AppearanceSettings />
    </ThemeProvider>,
  );
  await userEvent.click(screen.getByRole("radio", { name: "Dark" }));
  expect(localStorage.getItem("theme")).toBe("dark");
  expect(document.documentElement).toHaveClass("dark");
  localStorage.removeItem("theme");
  document.documentElement.classList.remove("dark");
});

it("keeps Accessibility's Reduce motion in this browser, off the hub (BB-FC-12)", async () => {
  const requests: unknown[] = [];
  server.use(
    http.get("/api/settings/all", () => HttpResponse.json({ display: { reduce_motion: false } })),
    http.put("/api/settings/display", async ({ request }) => {
      requests.push(await request.json());
      return HttpResponse.json({ reduce_motion: true });
    }),
  );
  render(
    <QueryClientProvider client={new QueryClient()}>
      <AccessibilitySettings />
    </QueryClientProvider>,
  );
  const toggle = await screen.findByRole("switch", { name: "Reduce motion" });
  await waitFor(() => expect(toggle).toBeEnabled());
  await userEvent.click(toggle);
  expect(localStorage.getItem("fiestaboard_a11y_reduce_motion")).toBe("on");
  expect(requests).toEqual([]);
  localStorage.removeItem("fiestaboard_a11y_reduce_motion");
});

describe("Settings section locale coverage", () => {
  it.each(locales)("includes the scope, destination and FiestaBot copy in %s", (locale) => {
    const messages = JSON.parse(fs.readFileSync(path.resolve(__dirname, `../../messages/${locale}.json`), "utf-8"));
    for (const [group, keys] of Object.entries({
      panels: ["theme", "browserTheme"],
      addresses: ["title", "description", "browser", "ip", "hint"],
      fiestabot: ["title", "scope", "unavailable", "open", "setup", "needsSetup", "checking", "checkFailed", "retry"],
    })) {
      for (const key of keys) expect(messages.settings[group][key]).toEqual(expect.any(String));
    }
    expect(messages.settings.ai.promptDestination).toContain("{destination}");
    expect(messages.settings.hub.sections.fiestabot.title).toBe("FiestaBot");
  });
});
