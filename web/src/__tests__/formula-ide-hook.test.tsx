import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { FormulaIdeContext, useFormulaIdeBridge } from "@/components/formula-ide/formula-ide-context";
import { useFormulaIde } from "@/components/formula-ide/use-formula-ide";
import type { RenderTarget } from "@/lib/api/formula-debug";

import { server } from "./mocks/server";

const TEMPLATE = ["GOOD MORNING", "{{weather.temp}}°", '{{= IF(weather.temp > 80, "HOT", "NICE") }} OUT'];
const target: RenderTarget = { template: TEMPLATE, deviceType: "flagship", boardId: "kitchen" };
const bodies: Array<Record<string, unknown>> = [];

beforeEach(() => {
  bodies.length = 0;
  server.use(
    http.get("/api/v1/variables", () =>
      HttpResponse.json({
        variables: { weather: ["temp"], muni: ["next"] },
        max_lengths: {},
        variable_metadata: { weather: { temp: { example: "70" } }, muni: { next: { example: "4 MIN" } } },
        colors: {},
        symbols: [],
        filters: [],
        formatting: {},
        syntax_examples: {},
      }),
    ),
    http.post("/api/templates/render", async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      bodies.push(body);
      const preview = body.preview as { missing?: string[]; values?: Record<string, string> } | undefined;
      const missing = !!preview?.missing;
      return HttpResponse.json({
        rendered: missing ? "GOOD MORNING\n???°\n#REF OUT" : "GOOD MORNING\n72°\nNICE OUT",
        lines: [],
        line_count: 3,
        diagnostics: {
          formulas: [
            {
              line: 3,
              start: 0,
              end: 43,
              source: ' IF(weather.temp > 80, "HOT", "NICE") ',
              value: missing ? "#REF" : "NICE",
              error: missing ? "#REF" : null,
              error_at: null,
              message: null,
            },
          ],
          lines: [],
        },
        ...(preview ? { sources: { weather: { state: "fresh", updated_at: null } } } : {}),
      });
    }),
  );
});

function Harness({ desktop, onOpen }: { desktop: boolean; onOpen?: () => void }) {
  const ide = useFormulaIde({
    target,
    desktop,
    mirroring: false,
    stopMirroring: vi.fn(),
    boardCols: 22,
    editTemplateLine: vi.fn(),
  });
  return (
    <FormulaIdeContext.Provider value={ide.bridge}>
      <div data-testid="override">{ide.previewOverride ?? "ordinary"}</div>
      {ide.headerControls}
      {ide.bodyControls}
      {ide.previewFooter}
      <Chip onOpen={onOpen} />
      {ide.overlays}
    </FormulaIdeContext.Provider>
  );
}

function Chip({ onOpen }: { onOpen?: () => void }) {
  const bridge = useFormulaIdeBridge();
  const hint = bridge?.hint('IF(weather.temp > 80, "HOT", "NICE")');
  return (
    <div>
      <span data-testid="hint">{hint ? `${hint.state}:${JSON.stringify(hint.value)}` : "none"}</span>
      <button
        type="button"
        onClick={() => {
          const docked = bridge?.openFormula({ expression: "x", apply: vi.fn(), cancel: vi.fn() });
          if (!docked) onOpen?.();
        }}
      >
        open
      </button>
    </div>
  );
}

function renderHarness(desktop: boolean, onOpen?: () => void) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <Harness desktop={desktop} onOpen={onOpen} />
    </QueryClientProvider>,
  );
}

describe("useFormulaIde", () => {
  it("renders with H5 diagnostics and serves chip hints from the same render", async () => {
    renderHarness(true);
    await waitFor(() => expect(screen.getByTestId("hint")).toHaveTextContent('ok:{"kind":"value","text":"NICE"}'));
    expect(bodies[0]).toMatchObject({ template: TEMPLATE, diagnostics: true, board_id: "kitchen" });
    expect(bodies[0]).not.toHaveProperty("preview");
    expect(screen.getByTestId("override")).toHaveTextContent("ordinary");
  });

  it("Missing marks every referenced integration missing and shows the hub's render", async () => {
    renderHarness(true);
    const group = await screen.findByRole("radiogroup", { name: "Preview data" });
    await userEvent.click(within(group).getByRole("radio", { name: "Missing" }));
    await waitFor(() => expect(screen.getByTestId("override")).toHaveTextContent("???°"));
    expect(bodies.at(-1)).toMatchObject({ preview: { missing: ["weather"], data: "cached" } });
    expect(screen.getByTestId("hint")).toHaveTextContent('error:{"kind":"error","tag":"#REF"}');
    expect(await screen.findByTestId("missing-values")).toHaveTextContent("1 missing");
  });

  it("Sample sends each integration's example values", async () => {
    renderHarness(false);
    const group = await screen.findByRole("radiogroup", { name: "Preview data" });
    await userEvent.click(within(group).getByRole("radio", { name: "Sample" }));
    await waitFor(() => expect(bodies.at(-1)).toMatchObject({ preview: { values: { "weather.temp": "70" } } }));
  });

  it("opens the docked editor only on desktop", async () => {
    const onOpen = vi.fn();
    renderHarness(false, onOpen);
    await userEvent.click(screen.getByRole("button", { name: "open" }));
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it("toggles Inspect with I outside text inputs on desktop", async () => {
    renderHarness(true);
    const toggle = await screen.findByRole("button", { name: /Inspect/ });
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    await act(async () => {
      await userEvent.keyboard("i");
    });
    expect(toggle).toHaveAttribute("aria-pressed", "true");
  });
});
