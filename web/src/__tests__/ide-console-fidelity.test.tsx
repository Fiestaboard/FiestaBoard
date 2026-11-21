/**
 * BB-FP-18 (Figma 184:159319): the console's Problems / Warnings / Sent tabs
 * share the list's width, and a formula problem reads "#REF · Row 2" with the
 * hub's message beside it, not "Formula error · Row 2" over "Formula #REF: …".
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { IdeConsole, IdeProblemList } from "@/components/ide/ide-console";
import type { CreatorIdeState } from "@/components/ide/use-creator-ide";
import { problemTitleParts } from "@/lib/ide/problems";

describe("console fidelity (BB-FP-18)", () => {
  it("stretches the three tabs across the list", () => {
    const ide = { problems: [], warnings: [], sends: [], sendsError: false } as unknown as CreatorIdeState;
    render(<IdeConsole ide={ide} tab="problems" onTabChange={() => {}} />);
    for (const tab of screen.getAllByRole("tab")) expect(tab).toHaveClass("flex-1");
  });

  it("titles a formula problem by its error tag and keeps the hub's reason as detail", () => {
    render(
      <IdeProblemList
        layout="inline"
        emptyLabel="none"
        problems={[
          { id: "f", severity: "error", kind: "formula", line: 2, message: "Formula #REF: Unknown source: missing" },
        ]}
      />,
    );
    expect(screen.getByText("#REF · Row 2")).toBeInTheDocument();
    expect(screen.getByText("Unknown source: missing")).toBeInTheDocument();
    expect(screen.queryByText(/Formula error/)).toBeNull();
  });

  it("leaves other problems' wording alone", () => {
    expect(problemTitleParts({ kind: "line_too_long", message: "Line 3 is 24 of 22 columns" })).toEqual({
      tag: null,
      detail: "Line 3 is 24 of 22 columns",
    });
    expect(problemTitleParts({ kind: "formula", message: "Formula #DIV/0: Division by zero" })).toEqual({
      tag: "#DIV/0",
      detail: "Division by zero",
    });
  });
});
