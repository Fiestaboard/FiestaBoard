import { Dialog } from "@fiestaboard/ui";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AddDisplayDialog } from "@/components/displays/add-display-dialog";
import { SetupWizard } from "@/components/wizard";
import { StepEasyPlugins } from "@/components/wizard/step-easy-plugins";

import { server } from "./mocks/server";

const push = vi.fn();
vi.mock("@/hooks/use-router", () => ({ useRouter: () => ({ push }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function renderFlow(dialog = false) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      {dialog ? (
        <Dialog open>
          <AddDisplayDialog onCreated={push} onCancel={vi.fn()} />
        </Dialog>
      ) : (
        <SetupWizard />
      )}
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  push.mockClear();
});

describe("07e setup flow", () => {
  it("starts at Welcome without progress and saves the hub before choosing output", async () => {
    const writes: unknown[] = [];
    server.use(
      http.put("/api/config/general", async ({ request }) => {
        writes.push(await request.json());
        return HttpResponse.json({});
      }),
    );
    renderFlow();
    expect(await screen.findByLabelText("Name this hub")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Setup progress" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Get started" }));
    expect(await screen.findByText("Step 1 of 4")).toBeInTheDocument();
    expect(writes).toEqual([
      expect.objectContaining({ instance_name: expect.any(String), timezone: expect.any(String) }),
    ]);
    expect(screen.getByRole("list", { name: "Setup progress" })).toBeInTheDocument();
    expect(await screen.findByRole("radio", { name: /Vestaboard/ })).toBeChecked();
  });

  it("opens backup settings with one navigation when restoring", async () => {
    renderFlow();
    await userEvent.click(await screen.findByRole("button", { name: "Restore from a backup…" }));
    expect(push.mock.calls).toEqual([["/settings/system"]]);
  });

  it("selects Something else for no data sources and clears it after selecting a source", () => {
    const config = { date_time: { enabled: false, timezone: "UTC" }, registry_selected: [] };
    const props = { onConfigChange: vi.fn(), onValidChange: vi.fn() };
    const view = render(<StepEasyPlugins {...props} config={config} />);
    expect(screen.getByRole("button", { name: /Something else/ })).toHaveAttribute("aria-pressed", "true");
    view.rerender(<StepEasyPlugins {...props} config={{ ...config, registry_selected: ["weather"] }} />);
    expect(screen.getByRole("button", { name: /Something else/ })).toHaveAttribute("aria-pressed", "false");
  });

  it("allows an untested connection but blocks Continue after failure and offers recovery", async () => {
    localStorage.setItem(
      "fiestaboard_wizard_progress",
      JSON.stringify({
        currentStep: 2,
        outputId: "vestaboard",
        boardConfig: { output_config: { api_mode: "local", host: "192.0.2.60", local_api_key: "test_key" } },
      }),
    );
    server.use(
      http.post("/api/outputs/vestaboard/actions/test_connection", () =>
        HttpResponse.json({ status: "error", message: "No response" }),
      ),
    );
    renderFlow();
    await waitFor(() => expect(screen.getByRole("button", { name: "Continue" })).toBeEnabled());
    await userEvent.click(screen.getByRole("button", { name: "Test connection" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Nothing was changed on the board");
    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
    expect(screen.getByText("Try this")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Use cloud key" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Skip for now" })).toBeEnabled();
  });

  it("keeps an already known board without creating a duplicate or replacing the fleet", async () => {
    localStorage.setItem(
      "fiestaboard_wizard_progress",
      JSON.stringify({
        currentStep: 2,
        outputId: "vestaboard",
        boardConfig: { output_config: { api_mode: "local", host: "192.0.2.60", local_api_key: "test_key" } },
      }),
    );
    const writes: unknown[] = [];
    server.use(
      http.post("/api/config/board/existing", () =>
        HttpResponse.json({
          existing: [{ board_id: "kitchen", name: "Kitchen board", output: "vestaboard", matched: "host" }],
        }),
      ),
      http.get("/api/settings/board", () =>
        HttpResponse.json({
          boards: [
            {
              id: "kitchen",
              name: "Kitchen board",
              output: "vestaboard",
              device_type: "flagship",
              output_config: { api_mode: "local", host: "192.0.2.60", local_api_key: "***" },
            },
          ],
        }),
      ),
      http.post("/api/settings/board/add", async ({ request }) => {
        writes.push(await request.json());
        return HttpResponse.json({ boards: [] });
      }),
      http.put("/api/settings/board", async ({ request }) => {
        writes.push(await request.json());
        return HttpResponse.json({});
      }),
    );
    renderFlow();
    expect(await screen.findByText("This board is already connected")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Keep Kitchen board/ })).toBeChecked();
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByText("Step 3 of 4")).toBeInTheDocument();
    expect(writes).toEqual([]);
  });

  it.each([
    ["cloud", { api_mode: "cloud", cloud_key: "test_existing_cloud" }, "cloud_key"],
    ["local", { api_mode: "local", host: "Board.Local", local_api_key: "test_key" }, "host"],
  ])(
    "recognizes an existing %s board through H19 without exposing saved keys or creating duplicates",
    async (_mode, output_config, matched) => {
      localStorage.setItem(
        "fiestaboard_wizard_progress",
        JSON.stringify({ currentStep: 2, outputId: "vestaboard", boardConfig: { output_config } }),
      );
      const lookup: unknown[] = [];
      const writes: unknown[] = [];
      server.use(
        http.get("/api/settings/board", () =>
          HttpResponse.json({
            boards: [
              {
                id: "known",
                name: "Existing board",
                output: "vestaboard",
                device_type: "flagship",
                output_config: { api_mode: _mode, host: "board.local", cloud_key: "***" },
              },
            ],
          }),
        ),
        http.post("/api/config/board/existing", async ({ request }) => {
          lookup.push(await request.json());
          return HttpResponse.json({
            existing: [{ board_id: "known", name: "Existing board", output: "vestaboard", matched }],
          });
        }),
        http.post("/api/settings/board/add", async ({ request }) => {
          writes.push(await request.json());
          return HttpResponse.json({ boards: [] });
        }),
        http.put("/api/settings/board", async ({ request }) => {
          writes.push(await request.json());
          return HttpResponse.json({});
        }),
      );
      renderFlow();
      expect(await screen.findByText("This board is already connected")).toBeInTheDocument();
      expect(screen.getByRole("radio", { name: /Keep Existing board/ })).toBeChecked();
      await userEvent.click(screen.getByRole("button", { name: "Continue" }));
      expect(await screen.findByText("Step 3 of 4")).toBeInTheDocument();
      expect(lookup.length).toBeGreaterThanOrEqual(2);
      expect(lookup).toEqual(
        lookup.map(() =>
          expect.objectContaining(matched === "host" ? { host: "Board.Local" } : { cloud_key: "test_existing_cloud" }),
        ),
      );
      expect(lookup.every((body) => !("local_api_key" in (body as object)))).toBe(true);
      expect(writes).toEqual([]);
    },
  );

  it("uses a browser-detected timezone and a useful name on a fresh hub with empty defaults", async () => {
    const realFormatter = Intl.DateTimeFormat;
    const timezone = vi.spyOn(Intl, "DateTimeFormat").mockImplementation(function (locales, options) {
      const formatter = new realFormatter(locales, options);
      return {
        ...formatter,
        format: formatter.format,
        resolvedOptions: () => ({ ...formatter.resolvedOptions(), timeZone: "Europe/London" }),
      } as Intl.DateTimeFormat;
    });
    const writes: unknown[] = [];
    server.use(
      http.get("/api/config/general", () => HttpResponse.json({ instance_name: "", timezone: "America/Los_Angeles" })),
      http.put("/api/config/general", async ({ request }) => {
        writes.push(await request.json());
        return HttpResponse.json({});
      }),
    );
    try {
      renderFlow();
      expect(await screen.findByLabelText("Name this hub")).toHaveValue("My FiestaPi");
      expect(screen.getByRole("button", { name: "Get started" })).toBeEnabled();
      await userEvent.click(screen.getByRole("button", { name: "Get started" }));
      expect(await screen.findByText("Step 1 of 4")).toBeInTheDocument();
      expect(writes).toEqual([{ instance_name: "My FiestaPi", timezone: "Europe/London" }]);
    } finally {
      timezone.mockRestore();
    }
  });

  it("preserves a deliberate hub timezone when setup has already been completed", async () => {
    const original = Intl.DateTimeFormat.prototype.resolvedOptions;
    const timezone = vi.spyOn(Intl.DateTimeFormat.prototype, "resolvedOptions").mockImplementation(function (
      this: Intl.DateTimeFormat,
    ) {
      return { ...original.call(this), timeZone: "Europe/London" };
    });
    const writes: unknown[] = [];
    server.use(
      http.get("/api/config/general", () =>
        HttpResponse.json({ instance_name: "Saved Hub", timezone: "Europe/Paris" }),
      ),
      http.get("/api/settings/wizard", () => HttpResponse.json({ state: "completed" })),
      http.put("/api/config/general", async ({ request }) => {
        writes.push(await request.json());
        return HttpResponse.json({});
      }),
    );
    try {
      renderFlow();
      await waitFor(() => expect(screen.getByLabelText("Name this hub")).toHaveValue("Saved Hub"));
      await userEvent.click(screen.getByRole("button", { name: "Get started" }));
      expect(await screen.findByText("Step 1 of 4")).toBeInTheDocument();
      expect(writes).toEqual([{ instance_name: "Saved Hub", timezone: "Europe/Paris" }]);
    } finally {
      timezone.mockRestore();
    }
  });

  it("retries a failed H19 lookup without changing connection settings", async () => {
    localStorage.setItem(
      "fiestaboard_wizard_progress",
      JSON.stringify({
        currentStep: 2,
        outputId: "vestaboard",
        boardConfig: { output_config: { api_mode: "local", host: "192.0.2.80", local_api_key: "test_key" } },
      }),
    );
    let calls = 0;
    server.use(
      http.post("/api/config/board/existing", () => {
        calls++;
        return calls === 1
          ? HttpResponse.json({ detail: "Lookup unavailable" }, { status: 503 })
          : HttpResponse.json({ existing: [] });
      }),
    );
    renderFlow();
    expect(await screen.findByRole("alert")).toHaveTextContent("Lookup unavailable");
    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Continue" })).toBeEnabled());
    expect(calls).toBe(2);
  });

  it("defaults to Keep when editing the address finds a different known board", async () => {
    localStorage.setItem(
      "fiestaboard_wizard_progress",
      JSON.stringify({
        currentStep: 2,
        outputId: "vestaboard",
        boardConfig: { output_config: { api_mode: "local", host: "board-a.local", local_api_key: "test_key" } },
      }),
    );
    server.use(
      http.post("/api/config/board/existing", async ({ request }) => {
        const body = (await request.json()) as { host: string };
        const id = body.host === "board-a.local" ? "A" : "B";
        return HttpResponse.json({
          existing: [{ board_id: id, name: `Board ${id}`, output: "vestaboard", matched: "host" }],
        });
      }),
    );
    renderFlow();
    await userEvent.click(await screen.findByRole("radio", { name: /Update its connection/ }));
    await userEvent.clear(screen.getByLabelText("Address"));
    await userEvent.type(screen.getByLabelText("Address"), "board-b.local");
    expect(await screen.findByRole("radio", { name: /Keep Board B/ })).toBeChecked();
  });

  it("finishes on Home without creating pages or sending a welcome message", async () => {
    localStorage.setItem(
      "fiestaboard_wizard_progress",
      JSON.stringify({
        currentStep: 4,
        outputId: "vestaboard",
        plugins: { date_time: { enabled: false, timezone: "UTC" }, registry_selected: [] },
      }),
    );
    const pages = vi.fn();
    server.use(
      http.post("/api/pages", () => {
        pages();
        return HttpResponse.json({});
      }),
    );
    renderFlow();
    await userEvent.click(await screen.findByRole("button", { name: "Finish setup" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/"));
    expect(pages).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: /Hello from FiestaBoard/ })).not.toBeInTheDocument();
  });
});

describe("07d two-step Add display", () => {
  it("asks for a connection and requires a passing test before adding a Vestaboard", async () => {
    renderFlow(true);
    await userEvent.click(await screen.findByRole("radio", { name: /Vestaboard/ }));
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByLabelText("Display name")).toBeInTheDocument();
    expect(screen.getByLabelText("Address")).toBeInTheDocument();
    expect(screen.getByLabelText("Local API key")).toHaveAttribute("type", "password");
    expect(screen.getByRole("button", { name: "Add display" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Test connection" })).toBeInTheDocument();
  });
});
