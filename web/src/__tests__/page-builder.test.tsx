import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

import { server } from "./mocks/server";

const API_BASE = "/api";
import { PageBuilder } from "@/components/page-builder";

vi.mock("@/components/preview-target-popover", () => import("./mocks/preview-target-popover-inline"));

vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
  }),
}));

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

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

// PageBuilder renders the TipTap editor — which owns the toolbar and its Sync
// from Board button — behind lazy() + Suspense. Resolving that chunk at first
// render costs ~450ms locally, which the assertions below would otherwise have
// to absorb inside waitFor's 1s default; on a loaded CI runner that overruns
// and the suite fails for a reason that has nothing to do with the behavior
// under test. Warm the chunk once so the waits below measure rendering, not
// module resolution.
beforeAll(async () => {
  await import("@/components/tiptap-template-editor/TipTapTemplateEditor");
});

// Import from board… (DD-W167, FABLE-2652 §5): a dialog step on new and saved
// pages; Replace template is one ordinary, undoable edit that saves nothing.
describe("PageBuilder — Import from board", () => {
  const IMPORT = "Import from board…";
  // "{red}" is a spelling the editor writes back as "{{red}}": undo must hand back this one.
  const ORIGINAL = ["{red}HELLO", "WORLD", "", "", "", ""];
  const TEMPLATE_PAGE = {
    id: "tpl-1",
    name: "Greeting",
    type: "template",
    device_type: "flagship",
    template: ORIGINAL,
    line_metadata: [
      { alignment: "center", wrap: false },
      { alignment: "right", wrap: true },
      { alignment: "left", wrap: false },
      { alignment: "left", wrap: false },
      { alignment: "left", wrap: false },
      { alignment: "left", wrap: false },
    ],
    duration_seconds: 300,
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-01-01T00:00:00Z",
  };
  // What the board shows: two rows and their own metadata.
  const SHOWING = {
    page_id: "src-1",
    page_name: "Weather Page",
    page_type: "template",
    device_type: "flagship",
    notes_wide: 1,
    notes_tall: 1,
    grid_rows: null,
    grid_cols: null,
    template: ["SUNNY", "HUMID"],
    line_metadata: [
      { alignment: "right", wrap: false },
      { alignment: "left", wrap: false },
    ],
  };
  let writes: { method: string; body: unknown }[];
  let currentDisplayUrls: string[];

  beforeEach(() => {
    vi.clearAllMocks();
    writes = [];
    currentDisplayUrls = [];
    server.use(
      http.get(`${API_BASE}/v1/pages/tpl-1`, () => HttpResponse.json(TEMPLATE_PAGE)),
      http.get(`${API_BASE}/pages/current-display`, ({ request }) => {
        currentDisplayUrls.push(request.url);
        return HttpResponse.json(SHOWING);
      }),
      http.put(`${API_BASE}/v1/pages/:id`, async ({ request }) => {
        const body = await request.json();
        writes.push({ method: "PUT", body });
        return HttpResponse.json({ ...TEMPLATE_PAGE, ...(body as object) });
      }),
      http.post(`${API_BASE}/v1/pages`, async ({ request }) => {
        writes.push({ method: "POST", body: await request.json() });
        return HttpResponse.json({ ...TEMPLATE_PAGE, id: "new-1" }, { status: 201 });
      }),
    );
  });

  const editorText = () => screen.getByRole("textbox", { name: "Template editor", hidden: true }).textContent ?? "";

  async function openSavedTemplate() {
    const user = userEvent.setup();
    render(<PageBuilder pageId="tpl-1" onClose={vi.fn()} />, { wrapper: TestWrapper });
    await waitFor(() => expect(editorText()).toContain("HELLO"), { timeout: 5000 });
    return user;
  }

  async function replaceFromBoard(user: ReturnType<typeof userEvent.setup>) {
    await user.click(await screen.findByRole("button", { name: IMPORT }));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent("Replace this template with what Flagship shows now?");
    const replace = await screen.findByRole("button", { name: "Replace template" });
    await waitFor(() => expect(replace).toBeEnabled());
    await user.click(replace);
    await waitFor(() => expect(editorText()).toContain("SUNNY"));
  }

  it("offers Import from board… on a new page and on a saved page", async () => {
    const { unmount } = render(<PageBuilder onClose={vi.fn()} />, { wrapper: TestWrapper });
    expect(await screen.findByRole("button", { name: IMPORT })).toBeInTheDocument();
    unmount();
    render(<PageBuilder pageId="tpl-1" onClose={vi.fn()} />, { wrapper: TestWrapper });
    expect(await screen.findByRole("button", { name: IMPORT })).toBeInTheDocument();
  });

  it("asks first: the click opens a dialog and leaves the template alone", async () => {
    const user = await openSavedTemplate();
    await user.click(await screen.findByRole("button", { name: IMPORT }));
    expect(await screen.findByRole("alertdialog")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(editorText()).toContain("HELLO");
    expect(editorText()).not.toContain("SUNNY");
  });

  it("reads the page's own board", async () => {
    const user = await openSavedTemplate();
    await user.click(await screen.findByRole("button", { name: IMPORT }));
    await waitFor(() => expect(currentDisplayUrls).toHaveLength(1));
    expect(new URL(currentDisplayUrls[0]).searchParams.get("board_id")).toBe("default");
  });

  it("replaces the rows as an unsaved edit: nothing is saved and no toast", async () => {
    const success = vi.spyOn((await import("sonner")).toast, "success");
    const user = await openSavedTemplate();
    await replaceFromBoard(user);
    expect(editorText()).not.toContain("HELLO");
    expect(await screen.findByText("Unsaved changes")).toBeInTheDocument();
    expect(writes).toEqual([]);
    expect(success).not.toHaveBeenCalled();
    // Saved, it is the board's rows and metadata on this page's geometry.
    await user.click(screen.getByRole("button", { name: /^Save/ }));
    await waitFor(() => expect(writes).toHaveLength(1));
    const body = writes[0].body as { template: string[]; line_metadata: unknown[]; device_type: string };
    expect(body.template.slice(0, 2)).toEqual(["SUNNY", "HUMID"]);
    expect(body.line_metadata.slice(0, 2)).toEqual([
      { alignment: "right", wrap: false },
      { alignment: "left", wrap: false },
    ]);
    expect(body.device_type).toBe("flagship");
  });

  it("one undo restores the previous rows, alignment and wrap exactly", async () => {
    const user = await openSavedTemplate();
    await replaceFromBoard(user);
    await user.click(screen.getByRole("button", { name: "Undo" }));
    await waitFor(() => expect(editorText()).toContain("HELLO"));
    expect(editorText()).not.toContain("SUNNY");
    // Back to the saved page: nothing left to save.
    await waitFor(() => expect(screen.queryByText("Unsaved changes")).not.toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /^Save/ }));
    await waitFor(() => expect(writes).toHaveLength(1));
    const body = writes[0].body as { template: string[]; line_metadata: unknown[] };
    expect(body.template).toEqual(ORIGINAL);
    expect(body.line_metadata).toEqual(TEMPLATE_PAGE.line_metadata);
  });

  it("redo puts the board's rows and metadata back", async () => {
    const user = await openSavedTemplate();
    await replaceFromBoard(user);
    await user.click(screen.getByRole("button", { name: "Undo" }));
    await waitFor(() => expect(editorText()).toContain("HELLO"));
    await user.click(screen.getByRole("button", { name: "Redo" }));
    await waitFor(() => expect(editorText()).toContain("SUNNY"));
    await user.click(screen.getByRole("button", { name: /^Save/ }));
    await waitFor(() => expect(writes).toHaveLength(1));
    const body = writes[0].body as { line_metadata: unknown[] };
    expect(body.line_metadata.slice(0, 2)).toEqual(SHOWING.line_metadata);
  });

  it("says so when the board shows nothing, with Close only", async () => {
    server.use(
      http.get(`${API_BASE}/pages/current-display`, () =>
        HttpResponse.json({ detail: "No active page set" }, { status: 404 }),
      ),
    );
    const user = await openSavedTemplate();
    await user.click(await screen.findByRole("button", { name: IMPORT }));
    expect(await screen.findByText("Flagship is showing nothing")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Close" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Replace template" })).not.toBeInTheDocument();
    expect(editorText()).toContain("HELLO");
  });

  it("never changes the page's size: a board showing another size only explains", async () => {
    server.use(
      http.get(`${API_BASE}/pages/current-display`, () =>
        HttpResponse.json({ ...SHOWING, device_type: "note", template: ["NOTE"] }),
      ),
    );
    const user = await openSavedTemplate();
    await user.click(await screen.findByRole("button", { name: IMPORT }));
    expect(await screen.findByText("Flagship shows a page of another size")).toBeInTheDocument();
    expect(screen.getByRole("alertdialog")).toHaveTextContent("make a copy sized for it from Inspector › Shows on");
    expect(screen.queryByRole("button", { name: "Replace template" })).not.toBeInTheDocument();
    expect(editorText()).toContain("HELLO");
  });
});

describe("PageBuilder — note-array dimensions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // A 4×1 note array → 4*15 = 60 cols, 1*3 = 3 rows. The BoardSizeIndicator
  // renders cols × rows (slice 2.4), so a real note-array preview shows
  // "60 × 3". A 1×1 (flagship/note default) note array would only ever show
  // "15 × 3", so asserting "60 × 3" proves the real dims were threaded through.
  function configureNoteArrayBoard(notesWide: number, notesTall: number) {
    server.use(
      http.get(`${API_BASE}/settings/board`, () => {
        return HttpResponse.json({
          board_type: "black",
          boards: [
            {
              id: "na-1",
              name: "Note Array",
              device_type: "note_array",
              board_color: "black",
              notes_wide: notesWide,
              notes_tall: notesTall,
            },
          ],
          devices: ["note_array"],
        });
      }),
    );
  }

  it("previews a NEW note_array page at the configured board's real size", async () => {
    // Configured note array is 4 wide × 1 tall → 60 × 3.
    configureNoteArrayBoard(4, 1);

    render(<PageBuilder deviceType="note_array" onClose={vi.fn()} />, { wrapper: TestWrapper });

    // The size indicator reflects the seeded grid dims (rows × cols), not 1×1.
    await waitFor(() => {
      expect(screen.getByRole("img", { name: /60 columns by 3 rows/i })).toBeInTheDocument();
    });
    const indicator = screen.getByRole("img", { name: /60 columns by 3 rows/i });
    expect(indicator).toHaveTextContent("60 × 3");
  });

  it("seeds dims from an EDITED note_array page", async () => {
    // Editing a 2×2 note array page (persisted notes_wide/notes_tall) →
    // 2*15 = 30 cols × 2*3 = 6 rows → "30 × 6".
    server.use(
      http.get(`${API_BASE}/v1/pages/:id`, () => {
        return HttpResponse.json({
          id: "na-page",
          name: "My Note Array Page",
          type: "template",
          device_type: "note_array",
          template: ["", "", "", "", "", ""],
          notes_wide: 2,
          notes_tall: 2,
          duration_seconds: 300,
          created_at: "2024-01-01T00:00:00Z",
        });
      }),
    );

    render(<PageBuilder pageId="na-page" onClose={vi.fn()} />, { wrapper: TestWrapper });

    // A saved page states its size in the preview's plain-text meta (D3, DD-W159).
    const meta = await screen.findByTestId("preview-target-meta");
    await waitFor(() => expect(meta).toHaveTextContent(/30 × 6$/));
  });

  it("leaves a flagship page at its fixed 22 × 6 size", async () => {
    render(<PageBuilder deviceType="flagship" onClose={vi.fn()} />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("img", { name: /22 columns by 6 rows/i })).toBeInTheDocument();
    });
    const indicator = screen.getByRole("img", { name: /22 columns by 6 rows/i });
    expect(indicator).toHaveTextContent("22 × 6");
  });
});
