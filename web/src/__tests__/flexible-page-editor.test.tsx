import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import { type FlexibleEditorPage, FlexiblePageEditor } from "@/components/flexible-page-editor";
import { api, ApiError, type BoardInstance } from "@/lib/api";
import { resolveBoardModel } from "@/lib/device-preview";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, api: { ...actual.api, updatePage: vi.fn(), createPage: vi.fn(), previewFlexiblePage: vi.fn() } };
});

const initial = {
  id: "p",
  revision: "rev-one",
  name: "Morning",
  type: "flexible" as const,
  duration_seconds: 30,
  created_at: "2026-01-01T00:00:00Z",
  blocks: [
    { id: "title", kind: "text", text: "Hello", style: { color: "#123456", future: 7 }, future: { keep: true } },
  ],
  layout: { kind: "stack", future: true },
  style: { size: "small", future: "preserve" },
};

function mount(document: FlexibleEditorPage = initial) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <FlexiblePageEditor initialPage={document} boards={[]} onClose={vi.fn()} onSave={vi.fn()} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.updatePage).mockResolvedValue({
    page: { ...initial, revision: "rev-two" },
    incompatible_references: [],
  });
});

it("edits target restrictions while retaining unresolved board IDs and opaque fields", async () => {
  mount({ ...initial, targets: { boards: ["another-install"], future: true } });
  const user = userEvent.setup();
  await user.click(screen.getByText("Display restrictions"));
  await user.click(screen.getByRole("checkbox", { name: "LED displays" }));
  expect(screen.getByRole("checkbox", { name: "LED displays" })).toBeChecked();
  expect(screen.getByText("Unavailable display: another-install")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Save page" }));
  await waitFor(() => expect(api.updatePage).toHaveBeenCalled());
  expect(vi.mocked(api.updatePage).mock.calls[0][1]).toMatchObject({
    targets: { boards: ["another-install"], technology: ["led_matrix"], future: true },
  });
});

it("edits a semantic block and saves with revision and opaque fields intact", async () => {
  mount();
  fireEvent.change(screen.getByLabelText("Block 1 text"), { target: { value: "Good morning" } });
  fireEvent.click(screen.getByRole("button", { name: "Save page" }));
  await waitFor(() => expect(api.updatePage).toHaveBeenCalled());
  expect(vi.mocked(api.updatePage).mock.calls[0]).toEqual([
    "p",
    expect.objectContaining({
      expected_revision: "rev-one",
      blocks: [
        expect.objectContaining({
          id: "title",
          text: "Good morning",
          future: { keep: true },
          style: { color: "#123456", future: 7 },
        }),
      ],
      layout: { kind: "stack", future: true },
      style: { size: "small", future: "preserve" },
    }),
  ]);
});

it("adds, reorders, removes and undoes blocks with stable identities", () => {
  mount();
  fireEvent.click(screen.getByRole("button", { name: "Add spacer" }));
  fireEvent.click(screen.getByRole("button", { name: "Move block 2 up" }));
  expect(screen.getByLabelText("Block 2 text")).toHaveValue("Hello");
  fireEvent.click(screen.getByRole("button", { name: "Remove block 1" }));
  expect(screen.getByLabelText("Block 1 text")).toHaveValue("Hello");
  fireEvent.click(screen.getByRole("button", { name: "Undo" }));
  expect(screen.getByLabelText("Block 2 text")).toHaveValue("Hello");
});

it("keeps the draft visible when another editor has changed the page", async () => {
  vi.mocked(api.updatePage).mockRejectedValue(new ApiError("Page changed; reload", 409));
  mount();
  fireEvent.change(screen.getByLabelText("Block 1 text"), { target: { value: "Keep my edit" } });
  fireEvent.click(screen.getByRole("button", { name: "Save page" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Page changed; reload");
  expect(screen.getByLabelText("Block 1 text")).toHaveValue("Keep my edit");
});

it("keeps the draft's base revision when a query refresh brings a newer page", async () => {
  const client = new QueryClient();
  const editor = (document: typeof initial) => (
    <QueryClientProvider client={client}>
      <FlexiblePageEditor initialPage={document} boards={[]} onClose={vi.fn()} onSave={vi.fn()} />
    </QueryClientProvider>
  );
  const view = render(editor(initial));
  fireEvent.change(screen.getByLabelText("Block 1 text"), { target: { value: "My draft" } });
  view.rerender(editor({ ...initial, revision: "someone-elses-revision" }));
  fireEvent.click(screen.getByRole("button", { name: "Save page" }));
  await waitFor(() =>
    expect(api.updatePage).toHaveBeenCalledWith("p", expect.objectContaining({ expected_revision: "rev-one" })),
  );
});

it("updates the detail cache from the saved server document", async () => {
  const client = new QueryClient();
  client.setQueryData(["page", "p"], initial);
  render(
    <QueryClientProvider client={client}>
      <FlexiblePageEditor initialPage={initial} boards={[]} onClose={vi.fn()} onSave={vi.fn()} />
    </QueryClientProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Save page" }));
  await waitFor(() => expect(client.getQueryData(["page", "p"])).toMatchObject({ revision: "rev-two" }));
});

it("blocks saving and retains an invalid Canvas JSON draft across tabs", async () => {
  const client = new QueryClient();
  const dirty = vi.fn();
  render(
    <QueryClientProvider client={client}>
      <FlexiblePageEditor
        initialPage={{
          ...initial,
          blocks: [{ id: "drawing", kind: "canvas", canvas: { content: { size: [8, 8], shapes: [] } } }],
        }}
        boards={[]}
        onClose={vi.fn()}
        onSave={vi.fn()}
        onDirtyChange={dirty}
      />
    </QueryClientProvider>,
  );
  const user = userEvent.setup();
  await user.click(screen.getByRole("tab", { name: "Shapes" }));
  await user.click(screen.getByRole("switch", { name: "Edit as JSON" }));
  fireEvent.change(screen.getByLabelText("Shapes JSON"), { target: { value: "[{" } });
  expect(screen.getByRole("button", { name: "Save page" })).toBeDisabled();
  await waitFor(() => expect(dirty).toHaveBeenLastCalledWith(true));
  await user.click(screen.getByRole("tab", { name: "Draw" }));
  await user.click(screen.getByRole("tab", { name: "Shapes" }));
  expect(screen.getByLabelText("Shapes JSON")).toHaveValue("[{");
  fireEvent.change(screen.getByLabelText("Shapes JSON"), { target: { value: "[]" } });
  expect(screen.getByRole("button", { name: "Save page" })).toBeEnabled();
  fireEvent.change(screen.getByLabelText("Shapes JSON"), { target: { value: "[{" } });
  await user.click(screen.getByRole("button", { name: "Remove block 1" }));
  await user.click(screen.getByRole("button", { name: "Undo" }));
  expect(screen.getByRole("button", { name: "Save page" })).toBeEnabled();
});

it("previews the unsaved document on the selected board without saving or sending it", async () => {
  const boards = [
    { id: "a", name: "Hall", device_type: "flagship" },
    { id: "b", name: "Desk", device_type: "note" },
  ] as BoardInstance[];
  vi.mocked(api.previewFlexiblePage).mockImplementation(async (_page, boardId) => ({
    page_id: "unsaved",
    message: boardId === "a" ? "HALL" : "DESK",
    lines: [boardId === "a" ? "HALL" : "DESK"],
    display_type: "page:flexible",
    raw: {},
    layout_issues: [{ path: ["blocks", "title"], code: "truncated", severity: "warning", message: "One line fits" }],
  }));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <FlexiblePageEditor initialPage={initial} boards={boards} onClose={vi.fn()} onSave={vi.fn()} />
    </QueryClientProvider>,
  );
  expect(await screen.findByLabelText("Hall character preview")).toHaveTextContent("HALL");
  const user = userEvent.setup();
  await user.click(screen.getByRole("combobox", { name: "Preview display" }));
  await user.click(await screen.findByRole("option", { name: "Desk" }));
  expect(await screen.findByLabelText("Desk character preview")).toHaveTextContent("DESK");
  expect(screen.getByLabelText("Layout issues")).toHaveTextContent("One line fits");
  expect(api.previewFlexiblePage).toHaveBeenLastCalledWith(
    expect.objectContaining({ type: "flexible", blocks: initial.blocks }),
    "b",
  );
  expect(api.updatePage).not.toHaveBeenCalled();
  expect(api.createPage).not.toHaveBeenCalled();
});

it("labels computed pixel geometry and distinguishes the alternate character layout", async () => {
  const base = resolveBoardModel({ device_model: "divoom_pixoo64" })!;
  const board = {
    id: "pixels",
    name: "Matrix",
    device_type: "panel",
    grid_rows: 3,
    grid_cols: 13,
    device_model_spec: { ...base, geometry: { kind: "pixels", width: 52, height: 17 } },
  } as BoardInstance;
  vi.mocked(api.previewFlexiblePage).mockResolvedValue({
    page_id: "unsaved",
    message: "FALLBACK",
    lines: ["FALLBACK"],
    display_type: "page:flexible",
    raw: { text_representation: "cell_projection", surface: { kind: "pixels", width: 52, height: 16 } },
    layers: [{ physical_frame_version: 1, x: 0, y: 0, width: 52, height: 16, rgba: btoa("\0".repeat(52 * 16 * 4)) }],
  });
  render(
    <QueryClientProvider client={new QueryClient()}>
      <FlexiblePageEditor initialPage={initial} boards={[board]} onClose={vi.fn()} onSave={vi.fn()} />
    </QueryClientProvider>,
  );
  expect(
    await screen.findByText("Computed preview · 52 × 16 pixels. This does not send to a display."),
  ).toBeInTheDocument();
  expect(screen.getByText(/The character fallback is a separate layout/)).toBeInTheDocument();
  expect(screen.getByRole("img")).toHaveAttribute("data-matrix-width", "52");
  expect(screen.getByRole("img")).toHaveAttribute("data-matrix-height", "16");
});

it("distinguishes a new unpersisted document from a saved page", () => {
  mount({ name: "New page", type: "flexible", blocks: [] });
  expect(screen.queryByText("Saved", { exact: true })).not.toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("Not saved yet");
});

it("takes the user back to a hidden invalid JSON draft without discarding it", async () => {
  mount({ ...initial, blocks: [{ id: "drawing", kind: "canvas", canvas: { content: { size: [8, 8], shapes: [] } } }] });
  const user = userEvent.setup();
  await user.click(screen.getByRole("tab", { name: "Shapes" }));
  await user.click(screen.getByRole("switch", { name: "Edit as JSON" }));
  fireEvent.change(screen.getByLabelText("Shapes JSON"), { target: { value: "[" } });
  await user.click(screen.getByRole("tab", { name: "Draw" }));
  await user.click(screen.getByRole("button", { name: "Fix Block 1" }));
  expect(screen.getByLabelText("Shapes JSON")).toBeVisible();
  expect(screen.getByLabelText("Shapes JSON")).toHaveFocus();
  expect(screen.getByLabelText("Shapes JSON")).toHaveValue("[");
});

it("links layout warnings to the affected block after reordering", async () => {
  vi.mocked(api.previewFlexiblePage).mockResolvedValue({
    page_id: "unsaved",
    message: "HI",
    lines: ["HI"],
    display_type: "page:flexible",
    raw: {},
    layout_issues: [{ path: ["blocks", "title"], code: "truncated", severity: "warning", message: "One line fits" }],
  });
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <FlexiblePageEditor
        initialPage={{ ...initial, blocks: [{ id: "first", kind: "spacer" }, ...initial.blocks] }}
        boards={[{ id: "a", name: "Hall", device_type: "flagship" } as BoardInstance]}
        onClose={vi.fn()}
        onSave={vi.fn()}
      />
    </QueryClientProvider>,
  );
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "Go to Block 2 (text)" }));
  expect(screen.getByRole("region", { name: "Block 2 (text)" })).toHaveFocus();
  await user.click(screen.getByRole("button", { name: "Move block 2 up" }));
  await user.click(await screen.findByRole("button", { name: "Go to Block 1 (text)" }));
  expect(screen.getByRole("region", { name: "Block 1 (text)" })).toHaveFocus();
});

it("saves a valid dimension with a single click immediately after typing", async () => {
  mount({ ...initial, blocks: [{ id: "drawing", kind: "canvas", canvas: { content: { size: [8, 8] } } }] });
  const user = userEvent.setup();
  await user.clear(screen.getByLabelText("Block 1 canvas width"));
  await user.type(screen.getByLabelText("Block 1 canvas width"), "16");
  await user.click(screen.getByRole("button", { name: "Save page" }));
  await waitFor(() =>
    expect(api.updatePage).toHaveBeenCalledWith(
      "p",
      expect.objectContaining({ blocks: [expect.objectContaining({ canvas: { content: { size: [16, 8] } } })] }),
    ),
  );
});

it("repairs the same invalid block after it is moved", async () => {
  mount({
    ...initial,
    blocks: [...initial.blocks, { id: "drawing", kind: "canvas", canvas: { content: { size: [8, 8], shapes: [] } } }],
  });
  const user = userEvent.setup();
  await user.click(screen.getByRole("tab", { name: "Shapes" }));
  await user.click(screen.getByRole("switch", { name: "Edit as JSON" }));
  fireEvent.change(screen.getByLabelText("Shapes JSON"), { target: { value: "[" } });
  await user.click(screen.getByRole("tab", { name: "Draw" }));
  await user.click(screen.getByRole("button", { name: "Move block 2 up" }));
  await user.click(screen.getByRole("button", { name: "Fix Block 1" }));
  expect(screen.getByLabelText("Shapes JSON")).toHaveFocus();
  expect(screen.getByLabelText("Shapes JSON")).toHaveValue("[");
});

it("restores committed canvas dimensions through undo and redo", async () => {
  mount({
    ...initial,
    blocks: [{ id: "drawing", kind: "canvas", canvas: { content: { size: [8, 8], palette: { r: "#ff0000" } } } }],
  });
  const user = userEvent.setup();
  const width = screen.getByLabelText("Block 1 canvas width");
  await user.clear(width);
  await user.type(width, "16");
  await user.tab();
  expect(width).toHaveValue(16);
  await user.click(screen.getByRole("button", { name: "Undo" }));
  expect(width).toHaveValue(8);
  await user.click(screen.getByRole("button", { name: "Redo" }));
  expect(width).toHaveValue(16);
  await user.click(screen.getByRole("button", { name: "Save page" }));
  await waitFor(() =>
    expect(api.updatePage).toHaveBeenCalledWith(
      "p",
      expect.objectContaining({
        blocks: [expect.objectContaining({ canvas: { content: { size: [16, 8], palette: { r: "#ff0000" } } } })],
      }),
    ),
  );
});

it("explains and blocks an out-of-range duration before sending the draft", () => {
  mount();
  fireEvent.change(screen.getByLabelText("Duration (seconds)"), { target: { value: "1" } });
  expect(screen.getByRole("button", { name: "Save page" })).toBeDisabled();
  expect(screen.getByRole("alert")).toHaveTextContent("10");
  fireEvent.change(screen.getByLabelText("Duration (seconds)"), { target: { value: "30" } });
  expect(screen.getByRole("button", { name: "Save page" })).toBeEnabled();
});
