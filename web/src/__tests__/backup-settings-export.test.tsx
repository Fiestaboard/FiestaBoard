/**
 * BB-C-7: exporting a backup used to click a temporary `<a href=/api/backup/export>`
 * and toast "Backup download started" straight away. With the hub unreachable
 * the browser navigated the whole tab to its own error page (the app was
 * gone), and a 4xx/5xx from the hub still toasted success. The export is now
 * fetched first: only a real file is saved, and only then is success said.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { toast } from "sonner";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BackupSettings } from "@/components/settings/backup-settings";

import en from "../../messages/en.json";
import { server } from "./mocks/server";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } }));

const backup = en.settings.backup;

function renderBackup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <BackupSettings />
    </QueryClientProvider>,
  );
}

let anchorClick: ReturnType<typeof vi.spyOn>;
let clickedAnchors: HTMLAnchorElement[];

beforeEach(() => {
  vi.mocked(toast.success).mockClear();
  vi.mocked(toast.error).mockClear();
  clickedAnchors = [];
  // jsdom cannot navigate; record what the app asked the browser to open.
  anchorClick = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    clickedAnchors.push(this);
  });
  URL.createObjectURL = vi.fn(() => "blob:backup");
  URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  anchorClick.mockRestore();
});

async function exportBackup() {
  const user = userEvent.setup();
  renderBackup();
  await user.click(screen.getByRole("button", { name: backup.exportButton }));
}

describe("BackupSettings export (BB-C-7)", () => {
  it("stays in the app and says the hub could not be reached when it is unreachable", async () => {
    server.use(http.get("*/api/backup/export", () => HttpResponse.error()));
    await exportBackup();

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(backup.exportUnreachable));
    // Never point the browser at the export URL: that is what replaced the app
    // with the browser's error page.
    expect(clickedAnchors).toHaveLength(0);
    expect(toast.success).not.toHaveBeenCalled();
  });

  it("reports the hub's error instead of a success toast when the export fails", async () => {
    server.use(http.get("*/api/backup/export", () => HttpResponse.json({ detail: "Disk is full" }, { status: 500 })));
    await exportBackup();

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(expect.stringContaining("Disk is full")));
    expect(clickedAnchors).toHaveLength(0);
    expect(toast.success).not.toHaveBeenCalled();
  });

  it("saves the file under the hub's name and only then says it was downloaded", async () => {
    server.use(
      http.get(
        "*/api/backup/export",
        () =>
          new HttpResponse(JSON.stringify({ fiestaboard_backup: true }), {
            headers: {
              "Content-Type": "application/json",
              "Content-Disposition": 'attachment; filename="fiestaboard-backup-20261120-101500.json"',
            },
          }),
      ),
    );
    await exportBackup();

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith(backup.exportDone));
    expect(clickedAnchors).toHaveLength(1);
    expect(clickedAnchors[0].getAttribute("href")).toBe("blob:backup");
    expect(clickedAnchors[0].download).toBe("fiestaboard-backup-20261120-101500.json");
    expect(toast.error).not.toHaveBeenCalled();
    // Not revoked straight away: WebKit may not have started the download yet.
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(URL.revokeObjectURL).not.toHaveBeenCalled();
  });
});
