/**
 * Integrations → Marketplace → "Add from Git": the dialog installs from a
 * repository URL through the shared `useGitPluginInstall` / `GitInstallFields`
 * (also used by Displays → Marketplace). Pinned here so extracting them kept
 * the dialog's behaviour: the request body, the success toast and closing,
 * and the server's message on failure.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import IntegrationsPage from "../../app/routes/integrations._index";
import { server } from "./mocks/server";

const toastMock = vi.hoisted(() => ({ success: vi.fn(), info: vi.fn(), error: vi.fn(), warning: vi.fn() }));
vi.mock("sonner", () => ({ toast: toastMock, Toaster: () => null }));
vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), forward: vi.fn() }),
  useParams: () => ({}),
  usePathname: () => "/integrations",
  useSearchParams: () => new URLSearchParams("tab=marketplace"),
}));

const GIT = "https://github.com/example/fiestaboard-plugin--example.git";

function setup(respond: () => Response) {
  const bodies: unknown[] = [];
  server.use(
    http.get("/api/plugins", () =>
      HttpResponse.json({ plugins: [], plugin_system_enabled: true, total: 0, enabled_count: 0 }),
    ),
    http.get("/api/plugins/registry", () => HttpResponse.json({ entries: [], plugin_system_enabled: true })),
    http.post("/api/plugins/install", async ({ request }) => {
      bodies.push(await request.json());
      return respond();
    }),
  );
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <IntegrationsPage />
    </QueryClientProvider>,
  );
  return bodies;
}

async function installFromDialog(branch = "") {
  await userEvent.click(await screen.findByRole("button", { name: /Add from Git/ }));
  const dialog = await screen.findByRole("dialog", { name: "Install Plugin from Git" });
  await userEvent.type(within(dialog).getByLabelText("Repository URL"), GIT);
  if (branch) await userEvent.type(within(dialog).getByLabelText("Branch (optional)"), branch);
  await userEvent.click(within(dialog).getByRole("button", { name: /Install Plugin/ }));
  return dialog;
}

beforeEach(() => {
  toastMock.success.mockReset();
  toastMock.error.mockReset();
});

describe("Integrations → Add from Git", () => {
  it("installs from the repository and closes", async () => {
    const bodies = setup(() => HttpResponse.json({ plugin_id: "example", message: "ok" }, { status: 201 }));
    await installFromDialog("main");
    await waitFor(() => expect(bodies).toEqual([{ repository: GIT, branch: "main" }]));
    await waitFor(() => expect(toastMock.success).toHaveBeenCalledWith("example installed from git"));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("shows the server's reason when the install is refused, and stays open", async () => {
    setup(() => HttpResponse.json({ detail: "Not a FiestaBoard plugin: no manifest.json" }, { status: 400 }));
    const dialog = await installFromDialog();
    await waitFor(() =>
      expect(toastMock.error).toHaveBeenCalledWith("Failed to install: Not a FiestaBoard plugin: no manifest.json"),
    );
    expect(dialog).toBeInTheDocument();
  });
});
