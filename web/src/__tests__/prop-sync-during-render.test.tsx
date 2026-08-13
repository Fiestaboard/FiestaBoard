import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { describe, expect, it, vi } from "vitest";

import { DaySelector } from "@/components/day-selector";
import { ForceSetDialog } from "@/components/force-set-dialog";
import { SchemaForm } from "@/components/plugin-settings/schema-form";
import { VariableRuleRow } from "@/components/variable-rule-row";
import type { VariableRule } from "@/lib/api";

function QueryWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

/**
 * Each of these components used to copy a prop into local state from a
 * useEffect — the `react-hooks/set-state-in-effect` shape in issue #1568. They
 * now do it during render. These are the behaviours that would silently break
 * if a sync were dropped or fired on the wrong renders; none of them had a
 * test before.
 */
describe("prop-driven state syncs", () => {
  describe("DaySelector", () => {
    it("checks the days named by a changed customDays prop", () => {
      const { rerender } = render(<DaySelector value="custom" customDays={["monday"]} onChange={vi.fn()} />);
      expect(screen.getByLabelText("Monday")).toBeChecked();

      rerender(<DaySelector value="custom" customDays={["tuesday"]} onChange={vi.fn()} />);

      expect(screen.getByLabelText("Tuesday")).toBeChecked();
      expect(screen.getByLabelText("Monday")).not.toBeChecked();
    });

    it("keeps a day the user just ticked when the parent re-renders with the same prop", () => {
      const customDays = ["monday"];
      const { rerender } = render(<DaySelector value="custom" customDays={customDays} onChange={vi.fn()} />);

      fireEvent.click(screen.getByLabelText("Friday"));
      expect(screen.getByLabelText("Friday")).toBeChecked();

      rerender(<DaySelector value="custom" customDays={customDays} onChange={vi.fn()} />);
      expect(screen.getByLabelText("Friday")).toBeChecked();
    });
  });

  describe("ForceSetDialog", () => {
    it("resets the duration to the 5 min default each time it reopens", async () => {
      const user = userEvent.setup();
      const { rerender } = render(<ForceSetDialog open onOpenChange={vi.fn()} pageId="p1" pageName="Weather" />, {
        wrapper: QueryWrapper,
      });

      await user.click(await screen.findByRole("button", { name: "30 min" }));
      // Selected presets get the primary background.
      expect(screen.getByRole("button", { name: "30 min" }).className).toContain("bg-primary");

      rerender(<ForceSetDialog open={false} onOpenChange={vi.fn()} pageId="p1" pageName="Weather" />);
      rerender(<ForceSetDialog open onOpenChange={vi.fn()} pageId="p1" pageName="Weather" />);

      await waitFor(() => {
        expect(screen.getByRole("button", { name: "5 min" }).className).toContain("bg-primary");
      });
      expect(screen.getByRole("button", { name: "30 min" }).className).not.toContain("bg-primary");
    });
  });

  describe("VariableRuleRow", () => {
    const t = (key: string) => key;

    function row(rule: VariableRule, isEditing: boolean) {
      return (
        <VariableRuleRow
          rule={rule}
          index={0}
          pages={[{ id: "p1", name: "Evening" }]}
          selectablePageIds={["p1"]}
          isEditing={isEditing}
          isDragging={false}
          onRequestEdit={() => true}
          onSave={vi.fn()}
          onCancelEdit={vi.fn()}
          onRemove={vi.fn()}
          onDirtyChange={vi.fn()}
          onDragStart={vi.fn()}
          onDragOver={vi.fn()}
          onDragEnd={vi.fn()}
          t={t}
        />
      );
    }

    it("opens the editor on the rule's current expression, not the one it mounted with", () => {
      // The row is a long-lived component: its rule can be replaced (a save
      // elsewhere in the list, a reorder) while it is collapsed. Entering edit
      // mode must snapshot the rule it has NOW.
      const original: VariableRule = { expression: "date_time.hour >= 17", page_id: "p1" };
      const replaced: VariableRule = { expression: "weather.temp > 80", page_id: "p1" };

      const { rerender } = render(row(original, false), { wrapper: QueryWrapper });
      rerender(row(replaced, false));
      rerender(row(replaced, true));

      expect(screen.getByRole("textbox")).toHaveValue("weather.temp > 80");
    });
  });

  describe("SchemaForm number field", () => {
    const schema = {
      type: "object" as const,
      properties: { latitude: { type: "number" as const, title: "Latitude" } },
    };

    it("shows a value written from outside the field while it is not focused", () => {
      // This is the "use my location" button path: the parent replaces the
      // value and the input has to follow.
      const { rerender } = render(<SchemaForm schema={schema} values={{ latitude: 1 }} onChange={vi.fn()} />);
      expect((screen.getByLabelText(/Latitude/) as HTMLInputElement).value).toBe("1");

      rerender(<SchemaForm schema={schema} values={{ latitude: 40.7128 }} onChange={vi.fn()} />);
      expect((screen.getByLabelText(/Latitude/) as HTMLInputElement).value).toBe("40.7128");
    });

    it("does not overwrite the number the user is typing", async () => {
      const user = userEvent.setup();
      const values = { latitude: 1 };
      const { rerender } = render(<SchemaForm schema={schema} values={values} onChange={vi.fn()} />);

      const input = screen.getByLabelText(/Latitude/);
      await user.click(input);
      await user.clear(input);
      await user.type(input, "-12");

      // A parent re-render with the same stored value must not snap the
      // half-typed "-12" back to "1".
      rerender(<SchemaForm schema={schema} values={values} onChange={vi.fn()} />);
      expect((input as HTMLInputElement).value).toBe("-12");
    });
  });
});
