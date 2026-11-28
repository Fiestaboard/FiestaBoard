import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { createRef } from "react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { PageBuilder, type PageBuilderDraftState, type PageBuilderHandle } from "@/components/page-builder";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

import { requestStore } from "./mocks/handlers";
import { server } from "./mocks/server";

vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
}));

const toastMock = vi.hoisted(() =>
  Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }),
);
vi.mock("sonner", async (importOriginal) => ({ ...(await importOriginal<object>()), toast: toastMock }));

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return (
    <QueryClientProvider client={queryClient}>
      <ConfigOverridesProvider>
        <ThemeProvider attribute="class" defaultTheme="light">
          {children}
        </ThemeProvider>
      </ConfigOverridesProvider>
    </QueryClientProvider>
  );
}

beforeAll(async () => {
  await import("@/components/tiptap-template-editor/TipTapTemplateEditor");
});

let puts: Record<string, unknown>[];
beforeEach(() => {
  puts = [];
  toastMock.mockClear();
  server.use(
    http.put("/api/v1/pages/page-1", async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      puts.push(body);
      return HttpResponse.json({
        page: { id: "page-1", name: body.name, type: "template", device_type: "flagship", template: [] },
        incompatible_references: [],
      });
    }),
  );
});

const nameField = () => screen.getByRole("textbox", { name: /page name/i });
const saveState = () => screen.getByTestId("page-editor-save-state");

async function renderSaved(draftState?: PageBuilderDraftState) {
  const ref = createRef<PageBuilderHandle>();
  const view = render(<PageBuilder ref={ref} pageId="page-1" onClose={vi.fn()} draftState={draftState} />, {
    wrapper: TestWrapper,
  });
  await waitFor(() => expect(nameField()).toHaveValue("Weather Page"));
  return { ref, view };
}

const key = (init: KeyboardEventInit) => act(() => void window.dispatchEvent(new KeyboardEvent("keydown", init)));

describe("editor header actions (D6, D8)", () => {
  it("shows Save draft · Save & update board while a display shows the page", async () => {
    const saveDraft = vi.fn();
    await renderSaved({ saveDraft, live: "Live on Kitchen" });
    expect(screen.queryByRole("button", { name: "Show now" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Update/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    expect(saveDraft).toHaveBeenCalledOnce();
    expect(puts).toHaveLength(0);
    const primary = screen.getByRole("button", { name: "Save & update board" });
    expect(primary).toHaveAttribute("data-ai-anchor", "page-editor.save");
    fireEvent.click(primary);
    await waitFor(() => expect(puts).toHaveLength(1));
  });

  it("shows Save · Show now on a page no display shows", async () => {
    await renderSaved();
    expect(screen.getByRole("button", { name: /^Save page$/i })).toHaveAttribute("data-ai-anchor", "page-editor.save");
    expect(screen.getByRole("button", { name: "Show now" })).toBeInTheDocument();
  });

  // binding: saveAndShow (Mod+Shift+S; ⌘S without Shift stays Save)
  it("⌘S saves the draft while live and ⌘⇧S saves and updates the board", async () => {
    const saveDraft = vi.fn();
    await renderSaved({ saveDraft });
    key({ key: "s", metaKey: true });
    expect(saveDraft).toHaveBeenCalledOnce();
    expect(puts).toHaveLength(0);
    key({ key: "S", metaKey: true, shiftKey: true });
    await waitFor(() => expect(puts).toHaveLength(1));
    expect(saveDraft).toHaveBeenCalledOnce();
  });

  it("⌘⇧S is Show now, not Save, on a page no display shows", async () => {
    await renderSaved();
    key({ key: "S", ctrlKey: true, shiftKey: true });
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(puts).toHaveLength(0);
    key({ key: "s", ctrlKey: true });
    await waitFor(() => expect(puts).toHaveLength(1));
  });
});

describe("editor header meta line (D6, UX-1-3)", () => {
  it("says Unsaved changes for edits, not the old Unsaved · last saved", async () => {
    await renderSaved();
    fireEvent.change(nameField(), { target: { value: "Weather Page 2" } });
    expect(saveState()).toHaveTextContent(/^Unsaved changes$/);
  });

  it("says Draft saved with a relative time while a display shows the page", async () => {
    await renderSaved({ saveDraft: vi.fn(), draftSavedAt: new Date(Date.now() - 2 * 60_000).toISOString() });
    expect(saveState()).toHaveTextContent(/^Draft saved 2 min ago$/);
    expect(saveState()).toHaveAttribute("title", expect.stringMatching(/\d{4}/));
  });

  it("says Saving draft… while the draft is written", async () => {
    await renderSaved({ saveDraft: vi.fn(), savingDraft: true });
    expect(saveState()).toHaveTextContent(/^Saving draft…$/);
    expect(screen.getByRole("button", { name: "Save draft" })).toBeDisabled();
  });

  it("puts a day on a save that wasn't today", async () => {
    await renderSaved();
    // The mock page was created on 2024-01-01: a date, not a bare clock time.
    expect(saveState()).toHaveTextContent(/^Saved Jan 1, 2024/);
  });

  it("offers Undo after Discard drops a restored draft, and Undo brings the whole draft back (UX-1-7)", async () => {
    const ref = createRef<PageBuilderHandle>();
    const onDiscard = vi.fn(async () => ref.current!.discardContent());
    render(
      <PageBuilder ref={ref} pageId="page-1" onClose={vi.fn()} draftState={{ label: "Draft restored", onDiscard }} />,
      { wrapper: TestWrapper },
    );
    await waitFor(() => expect(nameField()).toHaveValue("Weather Page"));
    // The restored draft: other text and a non-text field (duration).
    act(() =>
      ref.current!.applyContent({
        ...ref.current!.getCurrentPage()!,
        name: "From the draft",
        duration_seconds: 60,
      } as never),
    );
    expect(nameField()).toHaveValue("From the draft");
    fireEvent.click(screen.getByRole("button", { name: "Discard" }));
    await waitFor(() => expect(toastMock).toHaveBeenCalled());
    expect(onDiscard).toHaveBeenCalledOnce();
    expect(nameField()).toHaveValue("Weather Page");
    expect(ref.current!.getCurrentPage()?.duration_seconds).toBe(300);
    const [message, options] = toastMock.mock.lastCall as [string, { action: { label: string; onClick: () => void } }];
    expect(message).toBe("Draft discarded");
    expect(options.action.label).toBe("Undo");
    act(() => options.action.onClick());
    expect(nameField()).toHaveValue("From the draft");
    expect(ref.current!.getCurrentPage()?.duration_seconds).toBe(60);
  });
});

describe("new page and rename (UX-8-1, UX-1-5)", () => {
  it("names a new page Untitled page and saves it without typing a title", async () => {
    render(<PageBuilder onClose={vi.fn()} />, { wrapper: TestWrapper });
    await waitFor(() => expect(nameField()).toHaveValue("Untitled page"));
    expect(screen.getByTestId("page-editor-meta")).toHaveTextContent(/^New Page · .*Unsaved$/);
    fireEvent.click(screen.getByRole("button", { name: /^Save page$/i }));
    await waitFor(() => expect(requestStore.lastPageCreate?.name).toBe("Untitled page"));
  });

  it("starts a new page clean: Untitled page alone is not an unsaved change", async () => {
    const ref = createRef<PageBuilderHandle>();
    render(<PageBuilder ref={ref} onClose={vi.fn()} />, { wrapper: TestWrapper });
    await waitFor(() => expect(nameField()).toHaveValue("Untitled page"));
    expect(ref.current!.hasUnsavedChanges()).toBe(false);
    fireEvent.change(nameField(), { target: { value: "Kitchen morning" } });
    await waitFor(() => expect(ref.current!.hasUnsavedChanges()).toBe(true));
  });

  it("restores the name on Esc and keeps it on Enter", async () => {
    await renderSaved();
    const field = nameField();
    fireEvent.focus(field);
    fireEvent.change(field, { target: { value: "Oops" } });
    fireEvent.keyDown(field, { key: "Escape" });
    expect(field).toHaveValue("Weather Page");
    fireEvent.focus(field);
    fireEvent.change(field, { target: { value: "Morning" } });
    fireEvent.keyDown(field, { key: "Enter" });
    expect(field).toHaveValue("Morning");
  });
});

describe("Export and Delete (UX-1-4, UX-8-4)", () => {
  it("exports the editor's current content, unsaved edits included", async () => {
    await renderSaved();
    fireEvent.change(nameField(), { target: { value: "Not saved yet" } });
    const exportButton = screen.getByRole("button", { name: /export page/i });
    expect(exportButton).toBeEnabled();
    fireEvent.click(exportButton);
    const dialog = await screen.findByRole("dialog");
    const share = (within(dialog).getAllByRole("textbox")[0] as HTMLTextAreaElement).value;
    const json = JSON.parse(atob(share.replace(/-/g, "+").replace(/_/g, "/")));
    expect(json).toMatchObject({ v: 1, page: { name: "Not saved yet" } });
    expect(json.page).not.toHaveProperty("id");
  });

  it("names the page in the Delete dialog", async () => {
    const { ref } = await renderSaved();
    act(() => ref.current!.requestDelete());
    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText("Delete “Weather Page”?")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Delete page" })).toBeInTheDocument();
  });
});
