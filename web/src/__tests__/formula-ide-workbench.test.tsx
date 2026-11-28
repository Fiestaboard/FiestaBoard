import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { type ReactNode, useCallback, useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { FormulaBuilderCard, GeneratedCodeCard } from "@/components/formula-ide/formula-builder-card";
import { FormulaCodeCard } from "@/components/formula-ide/formula-code-card";
import type { OpenFormulaState } from "@/components/formula-ide/use-formula-ide";
import type { WorkbenchProps } from "@/components/formula-ide/workbench-types";

function wrap(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

function Workbench({
  card,
  initial,
  onState,
}: {
  card: (props: WorkbenchProps) => ReactNode;
  initial: OpenFormulaState;
  onState?: (state: OpenFormulaState | null) => void;
}) {
  const [open, setOpenState] = useState<OpenFormulaState | null>(initial);
  // Stable, like the hook's state setter.
  const setOpen: WorkbenchProps["setOpen"] = useCallback(
    (next) =>
      setOpenState((current) => {
        const value = typeof next === "function" ? next(current) : next;
        onState?.(value);
        return value;
      }),
    [onState],
  );
  return (
    <>
      {card({
        open,
        setOpen,
        focus: null,
        setFocus: vi.fn(),
        inspect: false,
        iteration: 0,
        formula: undefined,
        cell: null,
        diagnostics: null,
        rendered: [],
        trace: null,
        traceLoading: false,
        traceFailed: false,
        sourceMapStatus: null,
        renderFailed: false,
        boardCols: 22,
        onReplaceFormula: vi.fn(),
      })}
      {open && <GeneratedCodeCard {...({ open, setOpen } as WorkbenchProps)} />}
    </>
  );
}

const opened = (overrides: Partial<OpenFormulaState> = {}): OpenFormulaState => ({
  key: 1,
  tab: "builder",
  draft: null,
  expression: "",
  apply: vi.fn(),
  cancel: vi.fn(),
  ...overrides,
});

describe("FormulaBuilderCard", () => {
  it("writes a fallback recipe as plain formula text", async () => {
    const apply = vi.fn();
    wrap(<Workbench card={(p) => <FormulaBuilderCard {...p} />} initial={opened({ apply })} />);
    const recipes = screen.getByRole("radiogroup", { name: "Recipes" });
    await userEvent.click(within(recipes).getByRole("radio", { name: /Fallback when missing/ }));
    await userEvent.type(screen.getByLabelText("Value"), "weather.temp");
    await waitFor(() =>
      expect(screen.getByTestId("generated-code-text")).toHaveTextContent('DEFAULT( weather.temp, "--" )'),
    );
    // A new formula (empty chip) is inserted, not updated (UX-2-5).
    await userEvent.click(screen.getByRole("button", { name: /Insert formula/ }));
    expect(apply).toHaveBeenCalledWith('DEFAULT(weather.temp, "--")');
  });

  // BB-B-14: a hand-written formula is not a blank recipe the Builder would
  // overwrite; it says it can't show it and offers Code.
  it("does not dress a hand-written formula up as an empty recipe", async () => {
    const onState = vi.fn();
    wrap(
      <Workbench
        card={(p) => <FormulaBuilderCard {...p} />}
        initial={opened({ expression: "1 / 0" })}
        onState={onState}
      />,
    );
    expect(screen.getByText(/Builder can’t show this formula/)).toBeInTheDocument();
    const recipes = screen.getByRole("radiogroup", { name: "Recipes" });
    expect(within(recipes).queryByRole("radio", { checked: true })).toBeNull();
    expect(screen.queryByLabelText("List")).toBeNull();
    expect(screen.getByRole("button", { name: /Update formula/ })).toBeDisabled();
    expect(screen.getByTestId("generated-code-text")).toHaveTextContent("1 / 0");
  });

  it("sums the list's column budget against the board", async () => {
    wrap(<Workbench card={(p) => <FormulaBuilderCard {...p} />} initial={opened()} />);
    await userEvent.click(screen.getByRole("button", { name: /Add a column/ }));
    await userEvent.click(screen.getByRole("button", { name: /Add a column/ }));
    expect(screen.getByTestId("column-budget")).toHaveTextContent("5 + 1 + 5 = 11 of 22 columns · fits on every row");
  });

  it("switches to Code from the generated code", async () => {
    const onState = vi.fn();
    wrap(<Workbench card={(p) => <FormulaBuilderCard {...p} />} initial={opened()} onState={onState} />);
    await userEvent.click(screen.getByRole("button", { name: "Edit in Code" }));
    expect(onState).toHaveBeenLastCalledWith(expect.objectContaining({ tab: "code" }));
  });

  it("cancels on Esc, as the Code card does (UX-2-5)", () => {
    const apply = vi.fn();
    const cancel = vi.fn();
    wrap(<Workbench card={(p) => <FormulaBuilderCard {...p} />} initial={opened({ apply, cancel })} />);
    fireEvent.keyDown(screen.getByTestId("formula-builder-card"), { key: "Escape" });
    expect(cancel).toHaveBeenCalledTimes(1);
    expect(apply).not.toHaveBeenCalled();
    expect(screen.queryByTestId("formula-builder-card")).toBeNull();
  });

  it("cancels without applying", async () => {
    const apply = vi.fn();
    const cancel = vi.fn();
    wrap(<Workbench card={(p) => <FormulaBuilderCard {...p} />} initial={opened({ apply, cancel })} />);
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(cancel).toHaveBeenCalled();
    expect(apply).not.toHaveBeenCalled();
  });
});

describe("FormulaCodeCard", () => {
  // axe color-contrast at 1440 light: `--warning` is a fill token (about 3:1
  // on the light surface); code text uses the kit's ink tokens.
  it("colours code with ink tokens, never the warning fill", () => {
    wrap(
      <Workbench
        card={(p) => <FormulaCodeCard {...p} />}
        initial={opened({ tab: "code", expression: "SUM(1, 80)" })}
      />,
    );
    const css = [...document.querySelectorAll("style")].map((style) => style.textContent ?? "").join("\n");
    expect(css).toContain("var(--hue-yellow)");
    expect(css).not.toMatch(/color:\s*var\(--warning\)/);
  });

  it("pretty-prints the chip's formula and writes it back flat once valid", async () => {
    const apply = vi.fn();
    wrap(
      <Workbench
        card={(p) => <FormulaCodeCard {...p} />}
        initial={opened({ tab: "code", expression: 'IF(weather.temp > 80, "HOT", "NICE")', apply })}
      />,
    );
    const code = screen.getByTestId("formula-code");
    expect(code.querySelectorAll(".cm-line")).toHaveLength(5);
    await waitFor(() => expect(screen.getByText("Valid")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: /Update formula/ }));
    expect(apply).toHaveBeenCalledWith('IF(weather.temp > 80, "HOT", "NICE")');
  });

  // BB-B-13: the docked editor opens under the preview, often below the fold;
  // opening a chip brings it into view as well as focusing it.
  it("scrolls the whole opened formula card into view", () => {
    const original = Element.prototype.scrollIntoView;
    const scrolled: Element[] = [];
    Element.prototype.scrollIntoView = function (this: Element) {
      scrolled.push(this);
    };
    try {
      wrap(
        <Workbench card={(p) => <FormulaCodeCard {...p} />} initial={opened({ tab: "code", expression: "1 / 0" })} />,
      );
      // The card, with its validation line and Update / Cancel, not just the one-line editor.
      expect(scrolled).toContain(screen.getByTestId("formula-code-card"));
    } finally {
      Element.prototype.scrollIntoView = original;
    }
  });
});
