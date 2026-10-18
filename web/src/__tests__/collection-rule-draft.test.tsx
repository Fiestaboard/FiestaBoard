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

async function editRule() {
  await userEvent.click(screen.getByRole("button", { name: "Edit rule 1" }));
  fireEvent.change(await screen.findByRole("textbox", { name: "Expression for rule 1" }), {
    target: { value: "2 == 2" },
  });
}

describe("Collection rule drafts", () => {
  it("allows Update after removing a fresh draft while another rule is being edited", async () => {
    const { onSubmit } = renderForm();
    await userEvent.click(screen.getByRole("button", { name: "Add Rule" }));
    await userEvent.click(screen.getByRole("button", { name: "Edit rule 1" }));
    await userEvent.click(screen.getByRole("button", { name: "Remove rule" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel edit" }));
    expect(screen.getByRole("button", { name: "Update Collection" })).toBeEnabled();
    await userEvent.click(screen.getByRole("button", { name: "Update Collection" }));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        variable: expect.objectContaining({ rules: [{ expression: "1 == 1", page_id: "page-1" }] }),
      }),
    );
  });

  it("cancels the fresh draft after removing an earlier rule", async () => {
    const { onSubmit } = renderForm();
    await userEvent.click(screen.getByRole("button", { name: "Add Rule" }));
    await userEvent.click(screen.getByRole("button", { name: "Remove rule" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel edit" }));
    expect(screen.getByRole("button", { name: "Update Collection" })).toBeEnabled();
    await userEvent.click(screen.getByRole("button", { name: "Update Collection" }));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ variable: expect.objectContaining({ rules: [] }) }),
    );
  });

  it("keeps fresh draft and editor identity when a collapsed draft is reordered", async () => {
    const { onSubmit, form } = renderForm();
    await userEvent.click(screen.getByRole("button", { name: "Add Rule" }));
    await userEvent.click(screen.getByRole("button", { name: "Edit rule 1" }));
    const rows = form.querySelectorAll("[draggable]");
    const draftRow = screen.getByRole("button", { name: "Edit rule 2" }).closest("[draggable]")!;
    const editorRow = screen.getByRole("textbox", { name: "Expression for rule 1" }).closest("[draggable]")!;
    fireEvent.dragStart(draftRow);
    fireEvent.dragOver(editorRow);
    fireEvent.dragEnd(rows[rows.length - 1]);
    expect(screen.getByRole("textbox", { name: "Expression for rule 2" })).toHaveValue("1 == 1");
    await userEvent.click(screen.getByRole("button", { name: "Cancel edit" }));
    await userEvent.click(screen.getByRole("button", { name: "Edit rule 1" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel edit" }));
    expect(screen.getByRole("button", { name: "Update Collection" })).toBeEnabled();
    await userEvent.click(screen.getByRole("button", { name: "Update Collection" }));
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
    const draftRow = screen.getByRole("button", { name: "Edit rule 2" }).closest("[draggable]")!;
    const editorRow = screen.getByRole("textbox", { name: "Expression for rule 1" }).closest("[draggable]")!;
    fireEvent.dragStart(draftRow);
    fireEvent.dragOver(editorRow);
    fireEvent.dragEnd(draftRow);
    expect(screen.getByRole("textbox", { name: /Expression for rule/ })).toHaveValue("2 == 2");
    expect(screen.getByRole("button", { name: "Update Collection" })).toBeDisabled();
  });

  it("blocks outer Update while an existing rule has unsaved edits and explains how to proceed", async () => {
    renderForm();
    await editRule();
    expect(screen.getByRole("button", { name: "Update Collection" })).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent(/save or cancel/i);
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
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await userEvent.click(screen.getByRole("button", { name: "Update Collection" }));
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
    await userEvent.click(screen.getByRole("button", { name: "Update Collection" }));
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
    expect(screen.getByRole("button", { name: "Update Collection" })).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent(/save or cancel/i);
    fireEvent.submit(form);
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
