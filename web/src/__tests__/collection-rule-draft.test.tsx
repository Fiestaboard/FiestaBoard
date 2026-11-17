import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Collection, Page } from "@/lib/api";

import { CollectionForm } from "../../app/routes/collections";

const collection = {
  id: "collection:rules",
  name: "Rules",
  page_ids: ["page-1"],
  selection_mode: "variable",
  time: { interval_seconds: 30 },
  random: null,
  variable: { rules: [{ expression: "1 == 1", page_id: "page-1" }], default_page_id: "page-1", poll_seconds: 10 },
  created_at: "2025-01-01T00:00:00Z",
} as Collection;

function renderForm() {
  const onSubmit = vi.fn().mockResolvedValue(undefined);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={client}>
      <CollectionForm
        collection={collection}
        pages={[{ id: "page-1", name: "Page One" } as Page]}
        onSubmit={onSubmit}
        onCancel={vi.fn()}
      />
    </QueryClientProvider>,
  );
  return { onSubmit, form: view.container.querySelector("form")! };
}

async function ruleAction(number: number, action: string) {
  await userEvent.click(screen.getByRole("button", { name: `More actions for rule ${number}` }));
  await userEvent.click(await screen.findByRole("menuitem", { name: action }));
}

async function editRule() {
  await ruleAction(1, "Edit rule 1");
  fireEvent.change(await screen.findByRole("textbox", { name: "Expression for rule 1" }), {
    target: { value: "2 == 2" },
  });
}

describe("Collection rule drafts", () => {
  it("allows Update after removing a fresh draft while another rule is being edited", async () => {
    const { onSubmit } = renderForm();
    await userEvent.click(screen.getByRole("button", { name: "Add Rule" }));
    await ruleAction(1, "Edit rule 1");
    await ruleAction(2, "Remove rule");
    await userEvent.click(screen.getByRole("button", { name: "Cancel edit" }));
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        variable: expect.objectContaining({ rules: [{ expression: "1 == 1", page_id: "page-1" }] }),
      }),
    );
  });

  it("cancels the fresh draft after removing an earlier rule", async () => {
    const { onSubmit } = renderForm();
    await userEvent.click(screen.getByRole("button", { name: "Add Rule" }));
    await ruleAction(1, "Remove rule");
    await userEvent.click(screen.getByRole("button", { name: "Cancel edit" }));
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ variable: expect.objectContaining({ rules: [] }) }),
    );
  });

  it("keeps fresh draft and editor identity when a collapsed draft is reordered", async () => {
    const { onSubmit } = renderForm();
    await userEvent.click(screen.getByRole("button", { name: "Add Rule" }));
    await ruleAction(1, "Edit rule 1");
    await ruleAction(2, "Move rule 2 up");
    expect(screen.getByRole("textbox", { name: "Expression for rule 2" })).toHaveValue("1 == 1");
    await userEvent.click(screen.getByRole("button", { name: "Cancel edit" }));
    await ruleAction(1, "Edit rule 1");
    await userEvent.click(screen.getByRole("button", { name: "Cancel edit" }));
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        variable: expect.objectContaining({ rules: [{ expression: "1 == 1", page_id: "page-1" }] }),
      }),
    );
  });

  it("preserves unsaved expression edits when another rule is dragged across the editor", async () => {
    renderForm();
    await userEvent.click(screen.getByRole("button", { name: "Add Rule" }));
    await editRule();
    await userEvent.click(screen.getByRole("button", { name: "More actions for rule 2" }));
    expect(await screen.findByRole("menuitem", { name: "Move rule 2 up" })).toHaveAttribute("aria-disabled", "true");
    await userEvent.keyboard("{Escape}");
    expect(screen.getByRole("textbox", { name: "Expression for rule 1" })).toHaveValue("2 == 2");
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("blocks outer Update while an existing rule has unsaved edits and explains how to proceed", async () => {
    renderForm();
    await editRule();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    expect(screen.getByText(/Save or cancel the rule edit/i)).toBeInTheDocument();
  });

  it("blocks form submission while the rule draft is dirty", async () => {
    const { onSubmit, form } = renderForm();
    await editRule();
    fireEvent.submit(form);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("submits the edited rule after its inner Save", async () => {
    const { onSubmit } = renderForm();
    await editRule();
    await userEvent.click(screen.getByRole("button", { name: "Save Rule 1" }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          variable: expect.objectContaining({ rules: [{ expression: "2 == 2", page_id: "page-1" }] }),
        }),
      ),
    );
  });

  it("allows Update with the original rule after Cancel edit", async () => {
    const { onSubmit } = renderForm();
    await editRule();
    await userEvent.click(screen.getByRole("button", { name: "Cancel edit" }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          variable: expect.objectContaining({ rules: [{ expression: "1 == 1", page_id: "page-1" }] }),
        }),
      ),
    );
  });

  it("explains why a fresh empty rule must be saved or canceled before Update", async () => {
    const { onSubmit, form } = renderForm();
    await userEvent.click(screen.getByRole("button", { name: "Add Rule" }));
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    expect(screen.getByText(/Save or cancel the rule edit/i)).toBeInTheDocument();
    fireEvent.submit(form);
    expect(onSubmit).not.toHaveBeenCalled();
  });
  it("moves variable rules using keyboard-operable controls", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(
      <QueryClientProvider client={client}>
        <CollectionForm
          collection={{
            ...collection,
            variable: {
              ...collection.variable!,
              rules: [
                { expression: "1 == 1", page_id: "page-1" },
                { expression: "2 == 2", page_id: "page-1" },
              ],
            },
          }}
          pages={[{ id: "page-1", name: "Page One" } as Page]}
          onSubmit={onSubmit}
          onCancel={vi.fn()}
        />
      </QueryClientProvider>,
    );
    await ruleAction(2, "Move rule 2 up");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        variable: expect.objectContaining({
          rules: [
            { expression: "2 == 2", page_id: "page-1" },
            { expression: "1 == 1", page_id: "page-1" },
          ],
        }),
      }),
    );
  });
  it("names the rule's target-page selector while editing", async () => {
    renderForm();
    await ruleAction(1, "Edit rule 1");
    expect(
      screen.getByRole("combobox", { name: "Rule 1 · Show this page when the expression is true" }),
    ).toHaveTextContent("Page One");
  });
});
