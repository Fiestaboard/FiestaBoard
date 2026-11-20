import { Text } from "@fiestaboard/ui";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Collection, Page } from "@/lib/api";

import { CollectionForm } from "../../app/routes/collections";

const pages = [
  { id: "page-1", name: "Page One", device_type: "flagship" },
  { id: "page-2", name: "Page Two", device_type: "note" },
] as Page[];

function makeCollection(mode: Collection["selection_mode"] = "time"): Collection {
  return {
    id: "collection:layout",
    name: "Morning rotation",
    page_ids: ["page-1"],
    selection_mode: mode,
    time: { interval_seconds: 30 },
    random: mode === "random" ? { interval_seconds: 30 } : null,
    variable:
      mode === "variable"
        ? {
            rules: [
              { expression: "1 == 1", page_id: "page-1" },
              { expression: "2 == 2", page_id: "page-1" },
            ],
            default_page_id: "page-1",
            poll_seconds: 10,
          }
        : null,
    created_at: "2025-01-01T00:00:00Z",
  };
}

function renderForm(mode: Collection["selection_mode"] = "time", withPreview = false, isNew = false) {
  const onSubmit = vi.fn().mockResolvedValue(undefined);
  // The reusable form must also render without a query provider; live preview
  // belongs to the route's optional preview slot.
  const view = render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <CollectionForm
        collection={isNew ? undefined : makeCollection(mode)}
        pages={pages}
        onSubmit={onSubmit}
        onCancel={vi.fn()}
        preview={
          withPreview ? (dirty) => <Text>{dirty ? "Preview has unsaved changes" : "Saved preview"}</Text> : undefined
        }
      />
    </QueryClientProvider>,
  );
  return { ...view, onSubmit };
}

describe("Collection editor layout", () => {
  it.each(["time", "random"] as const)("places the %s preview between mode chips and duration controls", (mode) => {
    renderForm(mode, true);
    const modes = screen.getByRole("radiogroup");
    const preview = screen.getByText("Saved preview");
    const duration = screen.getByLabelText(mode === "time" ? "Page Duration" : "Change every", { exact: true });
    expect(modes.compareDocumentPosition(preview) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(preview.compareDocumentPosition(duration) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getAllByText("Saved preview")).toHaveLength(1);
    // Wider than a phone the preview is always shown, with no collapse trigger.
    expect(screen.getByText("Saved preview")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Now in this Collection" })).not.toBeInTheDocument();
  });

  it("opens the phone preview independently of settings and updates its dirty state", async () => {
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query === "(max-width: 767.98px)" || query === "(pointer: coarse)",
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
    try {
      const user = userEvent.setup();
      renderForm("time", true);
      // The phone preview starts collapsed behind its trigger.
      expect(screen.getByText("Saved preview")).not.toBeVisible();
      await user.click(screen.getByRole("button", { name: "Now in this Collection" }));
      expect(screen.getByText("Saved preview")).toBeVisible();
      expect(screen.getByLabelText("Collection name")).not.toBeVisible();
      await user.click(screen.getByRole("button", { name: "Collection settings" }));
      await user.type(screen.getByLabelText("Collection name"), " edited");
      await user.click(screen.getByRole("button", { name: "Collection settings" }));
      expect(screen.getByText("Preview has unsaved changes")).toBeVisible();
      expect(screen.getByLabelText("Collection name")).not.toBeVisible();
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("submits an edit from the header Save button", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderForm();
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({ name: "Morning rotation", page_ids: ["page-1"], selection_mode: "time" }),
      ),
    );
  });

  it("offers the selection modes as mutually exclusive radio buttons", async () => {
    const user = userEvent.setup();
    renderForm();
    const time = screen.getByRole("radio", { name: "Time-based rotation" });
    const random = screen.getByRole("radio", { name: "Random selection" });
    const variable = screen.getByRole("radio", { name: "Variable / expression" });
    expect(time).toBeChecked();
    await user.click(random);
    expect(random).toBeChecked();
    expect(time).not.toBeChecked();
    await user.click(variable);
    expect(variable).toBeChecked();
    expect(random).not.toBeChecked();
  });

  it("opens the page picker from Add page and saves the selected member", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderForm();
    await user.click(screen.getByRole("button", { name: /^\+?\s*Add page$/i }));
    await user.click(await screen.findByRole("menuitem", { name: /^Page Two/ }));
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ page_ids: ["page-1", "page-2"] })),
    );
  });

  it("labels the random interval Change every without an editable no-repeat switch", () => {
    renderForm("random");
    expect(screen.getByLabelText("Change every", { exact: true })).toBeInTheDocument();
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: /repeat/i })).not.toBeInTheDocument();
  });

  it("offers rule editing, movement and removal through More actions", async () => {
    const user = userEvent.setup();
    const { container } = renderForm("variable");
    await user.click(screen.getByRole("button", { name: "More actions for rule 1" }));
    expect(await screen.findByRole("menuitem", { name: "Edit rule 1" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Move rule 1 up" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Move rule 1 down" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Remove rule" })).toBeInTheDocument();
    expect(container.querySelector("[draggable]")).toBeNull();
    await user.click(screen.getByRole("menuitem", { name: "Edit rule 1" }));
    expect(screen.getByRole("textbox", { name: "Expression for rule 1" })).toHaveValue("1 == 1");
  });
  it("reorders rules by Space and arrows and restores them on Escape", async () => {
    const user = userEvent.setup();
    const { container, onSubmit } = renderForm("variable");
    const first = container.querySelector<HTMLElement>("#collection-rule-0")!;
    first.focus();
    await user.keyboard(" {ArrowDown}{Escape}");
    expect(screen.getByRole("button", { name: "Expression for rule 1" })).toHaveTextContent("1 == 1");
    container.querySelector<HTMLElement>("#collection-rule-0")!.focus();
    await user.keyboard(" {ArrowDown} ");
    await user.click(screen.getByRole("button", { name: "Save" }));
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
  it("locks rule mutations and mode changes until a lifted rule is dropped or canceled", async () => {
    const user = userEvent.setup();
    const { container } = renderForm("variable");
    container.querySelector<HTMLElement>("#collection-rule-0")!.focus();
    await user.keyboard(" ");
    expect(screen.getByRole("button", { name: "More actions for rule 1" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "More actions for rule 2" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Add Rule" })).toBeDisabled();
    expect(screen.getByRole("radio", { name: "Random selection" })).toBeDisabled();
    await user.keyboard("{Escape}");
    expect(screen.getByRole("button", { name: "More actions for rule 1" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
  });
  it("keeps phone settings collapsible without losing name edits", async () => {
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query === "(max-width: 767.98px)" || query === "(pointer: coarse)",
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
    try {
      const user = userEvent.setup();
      const { onSubmit } = renderForm();
      expect(screen.getByLabelText("Collection name")).not.toBeVisible();
      await user.click(screen.getByRole("button", { name: "Collection settings" }));
      const name = screen.getByLabelText("Collection name");
      expect(name).toBeVisible();
      await user.clear(name);
      await user.type(name, "Changed on phone");
      await user.click(screen.getByRole("button", { name: "Collection settings" }));
      expect(name).not.toBeVisible();
      await user.click(screen.getByRole("button", { name: "Save" }));
      expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ name: "Changed on phone" }));
    } finally {
      vi.unstubAllGlobals();
    }
  });

  const phoneTouch = () =>
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query === "(max-width: 767.98px)" || query === "(pointer: coarse)",
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));

  // BB-B-25: a new Collection shows its name field first and says why Create
  // is disabled; Add page lists each page's size.
  it("opens a new Collection on its name and says what Create still needs", async () => {
    phoneTouch();
    try {
      const user = userEvent.setup();
      renderForm("time", false, true);
      expect(screen.getByLabelText("Collection name")).toBeVisible();
      expect(screen.getByRole("button", { name: "Create Collection" })).toBeDisabled();
      expect(screen.getByText("Name the Collection to create it.")).toBeInTheDocument();
      await user.type(screen.getByLabelText("Collection name"), "Lunch");
      expect(screen.getByText("Add at least one page to create it.")).toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "Add page" }));
      expect(await screen.findByRole("menuitem", { name: /Page One/ })).toHaveTextContent(/Flagship/);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  // BB-B-26 (Figma 57:66920): touch copy for rule reordering, and a rule's
  // whole expression is readable.
  it("gives touch reorder copy for rules and shows the whole expression", () => {
    phoneTouch();
    try {
      renderForm("variable");
      // Rules have no drag handle: the ··· menu is the touch way to move them.
      expect(screen.getByText("To reorder, use ··· › Move up / Move down.")).toBeInTheDocument();
      expect(screen.queryByText(/press Space to lift/)).not.toBeInTheDocument();
      const expression = screen.getByRole("button", { name: "Expression for rule 1" });
      expect(expression).toHaveTextContent("1 == 1");
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
