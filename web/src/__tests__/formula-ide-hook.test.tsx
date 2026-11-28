import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { FormulaIdeContext, useFormulaIdeBridge } from "@/components/formula-ide/formula-ide-context";
import { PreviewHeaderControls } from "@/components/formula-ide/preview-data-controls";
import { useFormulaIde } from "@/components/formula-ide/use-formula-ide";
import type { RenderTarget } from "@/lib/api/formula-debug";

import { server } from "./mocks/server";

const TEMPLATE = ["GOOD MORNING", "{{weather.temp}}°", '{{= IF(weather.temp > 80, "HOT", "NICE") }} OUT'];
const target: RenderTarget = { template: TEMPLATE, deviceType: "flagship", boardId: "kitchen" };
const bodies: Array<Record<string, unknown>> = [];
// BB-FP-11: the one-line render that reads the template's variables for their chips.
const PROBE = ["{{= weather.temp }}"];
const pageRenders = () => bodies.filter((body) => JSON.stringify(body.template) !== JSON.stringify(PROBE));

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
      if (JSON.stringify(body.template) === JSON.stringify(PROBE)) {
        return HttpResponse.json({
          rendered: "72",
          lines: [],
          line_count: 1,
          diagnostics: {
            formulas: [
              {
                line: 1,
                start: 0,
                end: 19,
                source: " weather.temp ",
                value: missing ? "#REF" : "72",
                error: missing ? "#REF" : null,
                error_at: null,
                message: null,
              },
            ],
            lines: [],
          },
        });
      }
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

const LIVE_DIAGNOSTICS = {
  formulas: [
    {
      line: 3,
      start: 0,
      end: 43,
      source: 'IF(weather.temp > 80, "HOT", "NICE")',
      value: "HOT",
      error: null,
      error_at: null,
      message: null,
    },
  ],
  lines: [],
};

function Harness({
  desktop,
  onOpen,
  empty = false,
  withLive = false,
  liveFailed = false,
  mirroring = false,
  template,
}: {
  desktop: boolean;
  onOpen?: () => void;
  empty?: boolean;
  withLive?: boolean;
  liveFailed?: boolean;
  mirroring?: boolean;
  /** Replaces the page template (an edit), keeping the board. */
  template?: string[];
}) {
  const ide = useFormulaIde({
    target: empty ? null : template ? { ...target, template } : target,
    available: true,
    ...(withLive
      ? { live: { diagnostics: LIVE_DIAGNOSTICS, lines: ["GOOD MORNING", "72°", "HOT OUT"], failed: liveFailed } }
      : {}),
    desktop,
    mirroring,
    stopMirroring: vi.fn(),
    boardCols: 22,
    editTemplateLine: vi.fn(),
  });
  return (
    <FormulaIdeContext.Provider value={ide.bridge}>
      <div data-testid="override">{ide.previewOverride ?? "ordinary"}</div>
      <div data-testid="render-failed">{String(ide.renderFailed)}</div>
      <div data-testid="inspecting">{String(ide.view?.inspect ?? false)}</div>
      {ide.view && <PreviewHeaderControls data={ide.view} zoom={null} size="default" />}
      {ide.moreControls}
      {ide.caption}
      {ide.previewFooter}
      <Chip onOpen={onOpen} />
      {ide.rightSlot}
      {ide.overlays}
    </FormulaIdeContext.Provider>
  );
}

const chipCancel = vi.fn();

function Chip({ onOpen }: { onOpen?: () => void }) {
  const bridge = useFormulaIdeBridge();
  const hint = bridge?.hint('IF(weather.temp > 80, "HOT", "NICE")');
  const variable = bridge?.variableHint?.("weather.temp");
  return (
    <div>
      <span data-testid="hint">{hint ? `${hint.state}:${JSON.stringify(hint.value)}` : "none"}</span>
      <span data-testid="variable-hint">{variable ? JSON.stringify(variable.value) : "none"}</span>
      <button
        type="button"
        onClick={() => {
          const docked = bridge?.openFormula({ expression: "x", apply: vi.fn(), cancel: chipCancel });
          if (!docked) onOpen?.();
        }}
      >
        open
      </button>
    </div>
  );
}

function renderHarness(
  desktop: boolean,
  onOpen?: () => void,
  empty = false,
  withLive = false,
  extra: { liveFailed?: boolean; mirroring?: boolean; template?: string[] } = {},
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const tree = (more: typeof extra) => (
    <QueryClientProvider client={client}>
      <Harness desktop={desktop} onOpen={onOpen} empty={empty} withLive={withLive} {...extra} {...more} />
    </QueryClientProvider>
  );
  const result = render(tree({}));
  return { ...result, rerenderWith: (more: typeof extra) => result.rerender(tree(more)) };
}

describe("useFormulaIde", () => {
  it("renders with H5 diagnostics and serves chip hints from the same render", async () => {
    renderHarness(true);
    await waitFor(() => expect(screen.getByTestId("hint")).toHaveTextContent('ok:{"kind":"value","text":"NICE"}'));
    expect(bodies[0]).toMatchObject({ template: TEMPLATE, diagnostics: true, board_id: "kitchen" });
    expect(bodies[0]).not.toHaveProperty("preview");
    expect(screen.getByTestId("override")).toHaveTextContent("ordinary");
  });

  it("reads each variable's value for its chip from one probe render (BB-FP-11)", async () => {
    renderHarness(true, undefined, false, true);
    await waitFor(() => expect(screen.getByTestId("variable-hint")).toHaveTextContent('{"kind":"value","text":"72"}'));
    const probes = bodies.filter((body) => !pageRenders().includes(body));
    expect(probes).toHaveLength(1);
    expect(probes[0]).toMatchObject({ template: PROBE, board_id: "kitchen", device_type: "flagship" });
  });

  it("doesn't probe again for an edit that keeps the same variables (BB-FP-11)", async () => {
    const { rerenderWith } = renderHarness(true, undefined, false, true);
    await waitFor(() => expect(screen.getByTestId("variable-hint")).toHaveTextContent("72"));
    rerenderWith({ template: ["GOOD AFTERNOON", "{{weather.temp}}°", "BYE"] });
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(bodies.filter((body) => !pageRenders().includes(body))).toHaveLength(1);
  });

  it("shows ??? for a missing variable, as the board does, not the evaluator's #REF (BB-FP-11)", async () => {
    renderHarness(true, undefined, false, true);
    await waitFor(() => expect(screen.getByTestId("variable-hint")).toHaveTextContent("72"));
    const group = screen.getByRole("radiogroup", { name: "Preview data" });
    await userEvent.click(within(group).getByRole("radio", { name: "Missing" }));
    await waitFor(() => expect(screen.getByTestId("variable-hint")).toHaveTextContent('{"kind":"error","tag":"???"}'));
    const probes = bodies.filter((body) => !pageRenders().includes(body));
    expect(probes.at(-1)).toMatchObject({ template: PROBE, preview: { missing: ["weather"] } });
  });

  it("reads Live values from the editor's own preview render instead of rendering again", async () => {
    renderHarness(true, undefined, false, true);
    expect(screen.getByTestId("hint")).toHaveTextContent('ok:{"kind":"value","text":"HOT"}');
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(pageRenders()).toHaveLength(0);
  });

  // FABLE-2541 N15: a preview render that failed before mirroring must not keep
  // the "couldn't be rendered" alert up while the live render (the one behind
  // the hints now) is fine.
  it("reports a failed preview render in Live, but not while mirroring", () => {
    const { unmount } = renderHarness(true, undefined, false, true, { liveFailed: true });
    expect(screen.getByTestId("render-failed")).toHaveTextContent("true");
    unmount();
    renderHarness(true, undefined, false, true, { liveFailed: true, mirroring: true });
    expect(screen.getByTestId("render-failed")).toHaveTextContent("false");
  });

  it("still renders through the hub for Missing when the editor supplies Live values", async () => {
    renderHarness(true, undefined, false, true);
    const group = screen.getByRole("radiogroup", { name: "Preview data" });
    await userEvent.click(within(group).getByRole("radio", { name: "Missing" }));
    await waitFor(() => expect(screen.getByTestId("override")).toHaveTextContent("???°"));
    expect(pageRenders()).toHaveLength(1);
    expect(pageRenders()[0]).toMatchObject({ preview: { missing: ["weather"] } });
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

  // The docked preview must not grow when the debounced template first lands
  // (menus anchored below it would move under the pointer).
  it("shows the preview controls before the template has content", () => {
    renderHarness(false, undefined, true);
    expect(screen.getByRole("radiogroup", { name: "Preview data" })).toBeInTheDocument();
    expect(bodies).toHaveLength(0);
  });

  // W-5: one formula editor, two placements. Below 1024 it is the same Code |
  // Builder editor in a bottom sheet with no scrim, so the board stays in view.
  it("opens the same editor in a bottom sheet below 1024, not the chip's own dialog (W-5)", async () => {
    const onOpen = vi.fn();
    renderHarness(false, onOpen);
    await userEvent.click(screen.getByRole("button", { name: "open" }));
    expect(onOpen).not.toHaveBeenCalled();
    const sheet = await screen.findByTestId("formula-sheet");
    const card = await within(sheet).findByTestId("formula-code-card");
    expect(card).toHaveAttribute("data-placement", "sheet");
    expect(within(sheet).getByRole("tab", { name: "Code" })).toBeInTheDocument();
    expect(within(sheet).getByRole("tab", { name: "Builder" })).toBeInTheDocument();
    expect(within(sheet).getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    expect(within(sheet).getByRole("button", { name: "Update formula" })).toBeInTheDocument();
  });

  it("cancels the sheet once on Esc, and keeps it open on a press outside (W-5)", async () => {
    chipCancel.mockClear();
    renderHarness(false);
    await userEvent.click(screen.getByRole("button", { name: "open" }));
    const sheet = await screen.findByTestId("formula-sheet");
    await within(sheet).findByTestId("formula-code-card");
    await userEvent.click(screen.getByTestId("override"));
    expect(screen.getByTestId("formula-sheet")).toBeInTheDocument();
    expect(chipCancel).not.toHaveBeenCalled();
    // The editor's Esc and the sheet's own Esc both report the one close.
    const code = sheet.querySelector<HTMLElement>(".cm-content")!;
    code.focus();
    expect(code).toHaveFocus();
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByTestId("formula-sheet")).toBeNull());
    expect(chipCancel).toHaveBeenCalledTimes(1);
  });

  it("leaves an Esc the editor used (closing autocomplete) to the editor (W-5)", async () => {
    chipCancel.mockClear();
    renderHarness(false);
    await userEvent.click(screen.getByRole("button", { name: "open" }));
    const sheet = await screen.findByTestId("formula-sheet");
    await within(sheet).findByTestId("formula-code-card");
    const code = sheet.querySelector<HTMLElement>(".cm-content")!;
    code.focus();
    // CodeMirror's completion keymap: Esc closes the list and prevents the default.
    const closeCompletion = (event: KeyboardEvent) => {
      if (event.key === "Escape") event.preventDefault();
    };
    code.addEventListener("keydown", closeCompletion);
    await userEvent.keyboard("{Escape}");
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.getByTestId("formula-sheet")).toBeInTheDocument();
    expect(chipCancel).not.toHaveBeenCalled();
    code.removeEventListener("keydown", closeCompletion);
  });

  it("docks the editor on an empty page at desktop width (W-5)", async () => {
    const onOpen = vi.fn();
    renderHarness(true, onOpen, true);
    await userEvent.click(screen.getByRole("button", { name: "open" }));
    expect(onOpen).not.toHaveBeenCalled();
    const card = await screen.findByTestId("formula-code-card");
    expect(card).toHaveAttribute("data-placement", "docked");
    expect(screen.queryByTestId("formula-sheet")).toBeNull();
  });

  it("leaves a phone to the chip's own Formula sheet (306:38107)", async () => {
    const original = window.matchMedia;
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query.includes("max-width: 639px"),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
    try {
      const onOpen = vi.fn();
      renderHarness(false, onOpen);
      await userEvent.click(screen.getByRole("button", { name: "open" }));
      expect(onOpen).toHaveBeenCalledTimes(1);
      expect(screen.queryByTestId("formula-sheet")).toBeNull();
    } finally {
      window.matchMedia = original;
    }
  });

  it("opens the editor on an empty page too, before there is a render target (W-5)", async () => {
    const onOpen = vi.fn();
    renderHarness(false, onOpen, true);
    await userEvent.click(screen.getByRole("button", { name: "open" }));
    expect(onOpen).not.toHaveBeenCalled();
    expect(await screen.findByTestId("formula-sheet")).toBeInTheDocument();
  });

  it("toggles Inspect with I outside text inputs on desktop", async () => {
    // binding: inspect
    renderHarness(true);
    expect(await screen.findByTestId("inspecting")).toHaveTextContent("false");
    await act(async () => {
      await userEvent.keyboard("i");
    });
    expect(screen.getByTestId("inspecting")).toHaveTextContent("true");
    await userEvent.click(screen.getByRole("button", { name: "View" }));
    expect(await screen.findByRole("menuitemcheckbox", { name: /Inspect/ })).toHaveAttribute("aria-checked", "true");
  });

  // UX-9-3: Esc leaves Inspect and puts the caret back in the template.
  it("leaves Inspect with Esc and returns focus to the template", async () => {
    renderHarness(true);
    const editor = document.createElement("textarea");
    editor.id = "page-template-plain";
    document.body.appendChild(editor);
    await screen.findByTestId("inspecting");
    await act(async () => {
      await userEvent.keyboard("i");
    });
    expect(screen.getByTestId("inspect-hint")).toBeInTheDocument();
    await act(async () => {
      await userEvent.keyboard("{Escape}");
    });
    expect(screen.getByTestId("inspecting")).toHaveTextContent("false");
    expect(screen.queryByTestId("inspect-hint")).toBeNull();
    expect(document.activeElement).toBe(editor);
    editor.remove();
  });

  it("puts the dock's data modes in its More, not in the preview (UX-10-2)", async () => {
    renderHarness(false);
    expect(await screen.findByRole("radiogroup", { name: "Preview data" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "View" })).toBeNull();
    expect(document.querySelector('[data-slot="preview-caption"]')).toBeNull();
  });
});
