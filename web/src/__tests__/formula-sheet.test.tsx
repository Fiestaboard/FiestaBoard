/**
 * BB-FP-14 (Figma 306:38107): the phone Formula sheet. One amber expression
 * box with no `{{= … }}` chrome and a live result ("→ NICE", "weather.temp is
 * 72 now · 4 of 22 columns"), category chips over two-line function rows, and
 * one full-width primary "Insert formula" / "Update formula". Nothing is put
 * into the template before the user confirms.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { type FormulaIdeBridge, FormulaIdeContext } from "@/components/formula-ide/formula-ide-context";
import { FormulaResult } from "@/components/formula-ide/formula-result";
import { FormulaEditorPanel } from "@/components/tiptap-template-editor/components/FormulaEditorPanel";
import { serializeTemplateSimple } from "@/components/tiptap-template-editor/utils/serialization";
import { api } from "@/lib/api";

import { server } from "./mocks/server";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual("@/lib/api");
  return {
    ...actual,
    api: {
      ...(actual as { api: object }).api,
      getFormulaFunctions: vi.fn().mockResolvedValue({
        functions: {
          IF: { category: "logic", signature: "IF(test, then, else)", summary: "Show one value or another" },
          AND: { category: "logic", signature: "AND(a, b)", summary: "True when both are true" },
          ROUND: { category: "math", signature: "ROUND(n, digits)", summary: "Round a number" },
        },
      }),
      validateTemplate: vi.fn().mockResolvedValue({ valid: true, errors: [], warnings: [] }),
      getTemplateVariables: vi.fn().mockResolvedValue({
        variables: {},
        max_lengths: {},
        colors: {},
        symbols: [],
        filters: [],
        formatting: {},
        syntax_examples: {},
      }),
    },
  };
});

function Wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const EXPR = 'IF(weather.temp > 80, "HOT", "NICE")';
const bodies: Array<Record<string, unknown>> = [];

beforeEach(() => {
  bodies.length = 0;
  vi.mocked(api.validateTemplate).mockClear();
  server.use(
    http.post("/api/templates/render", async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      bodies.push(body);
      const formula = {
        line: 1,
        start: 0,
        end: 42,
        source: ` ${EXPR} `,
        value: "NICE",
        error: null,
        error_at: null,
        message: null,
      };
      return HttpResponse.json({
        rendered: "NICE",
        lines: ["NICE"],
        line_count: 1,
        diagnostics: { formulas: [formula], lines: [] },
        debug: {
          trace: {
            ...formula,
            truncated: false,
            events: [
              {
                id: 1,
                parent: null,
                kind: "variable",
                label: "weather.temp",
                start: 3,
                end: 15,
                value: "72",
                value_truncated: false,
                error: null,
              },
            ],
          },
          source_map: null,
          source_map_status: "not_requested",
        },
      });
    }),
  );
});

describe("phone Formula sheet layout (BB-FP-14)", () => {
  it("drops the {{= }} chrome and the uppercase label for one expression box", async () => {
    render(<FormulaEditorPanel layout="sheet" mode="create" onConfirm={vi.fn()} />, { wrapper: Wrapper });
    expect(screen.queryByText("{{=")).toBeNull();
    expect(screen.queryByText("}}")).toBeNull();
    expect(screen.getByText("Formula expression")).toHaveClass("sr-only");
    expect(screen.getByTestId("formula-expression-box")).toHaveClass("border-brand");
  });

  it("lists functions under category chips, signature over description", async () => {
    render(<FormulaEditorPanel layout="sheet" mode="create" onConfirm={vi.fn()} />, { wrapper: Wrapper });
    const chips = await screen.findByRole("radiogroup", { name: "Functions" });
    expect(await within(chips).findByRole("radio", { name: "Logic" })).toBeChecked();
    const row = screen.getByRole("button", { name: /IF\(test, then, else\)/ });
    expect(row).toHaveTextContent("Show one value or another");
    expect(screen.queryByRole("button", { name: /ROUND/ })).toBeNull();
    await userEvent.click(within(chips).getByRole("radio", { name: "Math" }));
    expect(screen.getByRole("button", { name: /ROUND\(n, digits\)/ })).toBeInTheDocument();
  });

  it("wraps the category chips instead of scrolling them out of view", async () => {
    render(<FormulaEditorPanel layout="sheet" mode="create" onConfirm={vi.fn()} />, { wrapper: Wrapper });
    const chips = await screen.findByRole("radiogroup", { name: "Functions" });
    expect(chips).not.toHaveClass("w-max");
    expect(chips.parentElement).not.toHaveClass("overflow-x-auto");
  });

  it("announces results from a live region that is always there", () => {
    render(<FormulaEditorPanel layout="sheet" mode="create" onConfirm={vi.fn()} result={() => null} />, {
      wrapper: Wrapper,
    });
    expect(screen.getByTestId("formula-result-region")).toHaveAttribute("aria-live", "polite");
  });

  it("has one full-width primary action and no Cancel/Done row", async () => {
    render(<FormulaEditorPanel layout="sheet" mode="create" onConfirm={vi.fn()} />, { wrapper: Wrapper });
    const insert = screen.getByRole("button", { name: "Insert formula" });
    expect(insert).toHaveClass("w-full");
    expect(insert).toBeDisabled();
    expect(screen.queryByRole("button", { name: /^(Cancel|Done|Insert)$/ })).toBeNull();
  });

  it("names the action Update formula when editing, and confirms the expression", async () => {
    const onConfirm = vi.fn();
    render(<FormulaEditorPanel layout="sheet" mode="edit" initialExpr={EXPR} onConfirm={onConfirm} />, {
      wrapper: Wrapper,
    });
    const update = screen.getByRole("button", { name: "Update formula" });
    await waitFor(() => expect(update).toBeEnabled());
    await userEvent.click(update);
    expect(onConfirm).toHaveBeenCalledWith(EXPR);
  });
});

describe("live result line (BB-FP-14)", () => {
  const bridge = {
    hint: () => undefined,
    openFormula: () => false,
    inspectFormula: vi.fn(),
    preview: { target: { deviceType: "flagship", boardId: "kitchen" }, context: null, boardCols: 22 },
  } as unknown as FormulaIdeBridge;

  it("shows the value, the variable it read and how much of the row it takes", async () => {
    render(
      <FormulaIdeContext.Provider value={bridge}>
        <FormulaResult expression={EXPR} />
      </FormulaIdeContext.Provider>,
      { wrapper: Wrapper },
    );
    expect(await screen.findByText("→ NICE")).toBeInTheDocument();
    expect(screen.getByText("weather.temp is 72 now · 4 of 22 columns")).toBeInTheDocument();
    expect(bodies[0]).toMatchObject({
      template: [`{{= ${EXPR} }}`],
      board_id: "kitchen",
      debug: { trace: { line: 1, start: 0 } },
    });
  });

  it("renders nothing without the page editor's preview", () => {
    const { container } = render(<FormulaResult expression={EXPR} />, { wrapper: Wrapper });
    expect(container).toBeEmptyDOMElement();
  });
});

describe("an unconfirmed formula is not content (BB-FP-14)", () => {
  it("serializes an empty formula node to nothing, so the page stays saved", () => {
    const doc = {
      type: "doc",
      content: [
        {
          type: "paragraph",
          content: [
            { type: "text", text: "HI " },
            { type: "formula", attrs: { expression: "" } },
          ],
        },
      ],
    };
    expect(serializeTemplateSimple(doc, 1)).toBe("HI ");
  });
});
