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

it("writes only the supported reduce-motion field to hub display settings", async () => {
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
  await userEvent.click(await screen.findByRole("switch", { name: "Reduce motion" }));
  await waitFor(() => expect(requests).toEqual([{ reduce_motion: true }]));
});

describe("Settings section locale coverage", () => {
  it.each(locales)("includes the scope, destination and FiestaBot copy in %s", (locale) => {
    const messages = JSON.parse(fs.readFileSync(path.resolve(__dirname, `../../messages/${locale}.json`), "utf-8"));
    for (const [group, keys] of Object.entries({
      panels: ["theme", "browserTheme", "motionScope"],
      addresses: ["title", "description", "browser", "ip", "hint"],
      fiestabot: ["title", "scope", "unavailable", "open", "setup", "needsSetup", "checking", "checkFailed", "retry"],
    })) {
      for (const key of keys) expect(messages.settings[group][key]).toEqual(expect.any(String));
    }
    expect(messages.settings.ai.promptDestination).toContain("{destination}");
    expect(messages.settings.hub.sections.fiestabot.title).toBe("FiestaBot");
  });
});
