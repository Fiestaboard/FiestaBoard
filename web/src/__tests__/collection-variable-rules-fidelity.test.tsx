import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Collection, Page } from "@/lib/api";

import { CollectionForm } from "../../app/routes/collections";

// BB-FP-21: the variable-collection rule rows follow Figma 312:78075.

const pages = [
  { id: "rain", name: "Rainy day", device_type: "flagship" },
  { id: "evening", name: "Evening commute", device_type: "flagship" },
  { id: "morning", name: "Good morning", device_type: "flagship" },
] as Page[];

const collection: Collection = {
  id: "collection:weather",
  name: "Weather-aware morning",
  page_ids: ["rain", "evening", "morning"],
  selection_mode: "variable",
  time: { interval_seconds: 30 },
  random: null,
  variable: {
    rules: [
      { expression: 'weather.condition = "rain"', page_id: "rain" },
      { expression: "IF(date_time.hour >= 17, 7, 0)", page_id: "evening" },
    ],
    default_page_id: "morning",
    poll_seconds: 10,
  },
  created_at: "2025-01-01T00:00:00Z",
};

const ruleResults = [
  { index: 0, value: "No", error: null, message: null, matched: false },
  { index: 1, value: "7", error: null, message: null, matched: true },
];

function renderForm(props: Partial<React.ComponentProps<typeof CollectionForm>> = {}) {
  const onSubmit = vi.fn().mockResolvedValue(undefined);
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <CollectionForm
        collection={collection}
        pages={pages}
        onSubmit={onSubmit}
        onCancel={vi.fn()}
        ruleResults={ruleResults}
        evaluatedPageId="morning"
        {...props}
      />
    </QueryClientProvider>,
  );
  return { onSubmit };
}

describe("Variable collection rules (BB-FP-21)", () => {
  it("uses the Figma intro and Add rule copy", () => {
    renderForm();
    expect(
      screen.getByText(
        "Rules are checked top to bottom whenever their values change. The first rule that is true picks the page; if none match, the Default page shows.",
      ),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Add rule" })).toBeInTheDocument();
  });

  it("shows the expression as a one-line sans field, not a mono code box", () => {
    renderForm();
    const field = screen.getByRole("button", { name: "Expression for rule 1" });
    expect(field).toHaveTextContent('weather.condition = "rain"');
    expect(field.className).not.toMatch(/font-mono/);
  });

  it("picks each rule's page from a Select in the row and saves it", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderForm();
    const target = screen.getByRole("combobox", { name: "Page for rule 1" });
    expect(target).toHaveTextContent("Rainy day");
    await user.click(target);
    await user.click(await screen.findByRole("option", { name: "Good morning" }));
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          variable: expect.objectContaining({
            rules: [
              { expression: 'weather.condition = "rain"', page_id: "morning" },
              { expression: "IF(date_time.hour >= 17, 7, 0)", page_id: "evening" },
            ],
          }),
        }),
      ),
    );
  });

  it("badges each rule true/false from the evaluation, with the value it saw now", () => {
    renderForm();
    const rule1 = screen.getByRole("group", { name: "Rule 1" });
    expect(within(rule1).getByText("false")).toBeInTheDocument();
    expect(within(rule1).getByText("now → false")).toBeInTheDocument();
    const rule2 = screen.getByRole("group", { name: "Rule 2" });
    expect(within(rule2).getByText("true")).toBeInTheDocument();
    expect(within(rule2).getByText("now: “7” → true")).toBeInTheDocument();
    expect(screen.queryByText("No")).not.toBeInTheDocument();
  });

  it("says when a test-at-a-time result is not now", () => {
    renderForm({ ruleResultsAt: "2026-11-20T07:02:00" });
    const rule2 = screen.getByRole("group", { name: "Rule 2" });
    expect(within(rule2).getByText(/^at .*7:02.*: “7” → true$/)).toBeInTheDocument();
  });

  it("labels the Default row as Figma does", () => {
    renderForm();
    expect(screen.getByText("Default", { selector: "[data-slot=badge]" })).toBeInTheDocument();
    expect(screen.getByText("Showing now")).toBeInTheDocument();
    expect(screen.queryByText("Default Page")).not.toBeInTheDocument();
  });

  it("gives Re-check interval and Pages in collection real disclosure triggers", async () => {
    const user = userEvent.setup();
    renderForm();
    for (const name of ["Re-check Interval", "Pages in Collection"]) {
      const trigger = screen.getByRole("button", { name });
      expect(trigger).toHaveAttribute("aria-expanded", "false");
      expect(trigger.querySelector("svg")).not.toBeNull();
      await user.click(trigger);
      expect(trigger).toHaveAttribute("aria-expanded", "true");
    }
  });
});
