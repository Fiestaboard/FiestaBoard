/**
 * BB-C-20 (backup + AI provider part): the backup and AI-provider toasts were
 * literal English, so a German or Japanese user got "Backup download
 * started" / "AI provider settings saved". They now come from the messages.
 *
 * Uses a two-locale i18next instance, like
 * schedule-entry-form-locale-switch.test.tsx (see its header for why the
 * shared 14-locale singleton is not unmocked).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { toast } from "sonner";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { i18nHolder } = vi.hoisted(() => ({ i18nHolder: {} as { current?: import("i18next").i18n } }));

vi.mock("@/i18n/i18next", async () => {
  const { default: i18next } = await import("i18next");
  const { initReactI18next } = await import("react-i18next");
  const { default: en } = await import("../../messages/en.json");
  const { default: de } = await import("../../messages/de.json");

  const instance = i18next.createInstance();
  await instance.use(initReactI18next).init({
    resources: { en: { translation: en }, de: { translation: de } },
    lng: "en",
    fallbackLng: "en",
    interpolation: { escapeValue: false, prefix: "{{", suffix: "}}" },
    returnNull: false,
    react: { useSuspense: false },
  });
  i18nHolder.current = instance;
  return { default: instance };
});
vi.unmock("@/i18n/translations");
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } }));

import { AiSettings } from "@/components/settings/ai-settings";
import { BackupSettings } from "@/components/settings/backup-settings";

import de from "../../messages/de.json";
import { server } from "./mocks/server";

function withClient(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return <QueryClientProvider client={client}>{ui}</QueryClientProvider>;
}

/** Switch to German after finding controls by their English names. */
async function toGerman() {
  await act(async () => {
    await i18nHolder.current!.changeLanguage("de");
  });
}

beforeEach(async () => {
  vi.mocked(toast.success).mockClear();
  vi.mocked(toast.error).mockClear();
  await act(async () => {
    await i18nHolder.current!.changeLanguage("en");
  });
});

describe("Settings toasts follow the language (BB-C-20)", () => {
  it("says the hub could not be reached for a backup export in German", async () => {
    server.use(http.get("*/api/backup/export", () => HttpResponse.error()));
    render(withClient(<BackupSettings />));
    const exportButton = screen.getByRole("button", { name: "Export backup" });
    await toGerman();
    await userEvent.setup().click(exportButton);
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(de.settings.backup.exportUnreachable));
  });

  it("rejects a file that is not a backup in German", async () => {
    const { container } = render(withClient(<BackupSettings />));
    await toGerman();
    const input = container.querySelector<HTMLInputElement>('input[type="file"]')!;
    await userEvent.setup().upload(input, new File(['{"hello": 1}'], "notes.json", { type: "application/json" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(de.settings.backup.notABackup));
  });

  it("confirms a saved AI provider in German", async () => {
    server.use(
      http.get("*/api/settings/ai", () =>
        HttpResponse.json({
          enabled: true,
          providers: [
            {
              id: "p1",
              name: "Test",
              base_url: "https://example.test/v1",
              api_key: "***",
              models: ["test-model"],
              default_model: "test-model",
            },
          ],
          default_provider_id: "p1",
        }),
      ),
      http.put("*/api/settings/ai", async ({ request }) => HttpResponse.json(await request.json())),
    );
    render(withClient(<AiSettings />));
    const user = userEvent.setup();
    await user.click(await screen.findByText("Test"));
    const name = await screen.findByLabelText(/^Name$/);
    await user.clear(name);
    await user.type(name, "Renamed");
    const save = screen.getByRole("button", { name: /save changes/i });
    await toGerman();
    await user.click(save);
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith(de.settings.ai.savedToast));
  });
});
