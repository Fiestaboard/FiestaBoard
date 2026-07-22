/**
 * Tests for the note-array settings UI in DisplaySettings:
 *  - Grouped device/preset Select (replaces the old flagship/note pills)
 *  - Custom W×H inputs with 1..MAX_NOTES_PER_AXIS validation
 *  - note_array_token field (masked-secret round trip)
 *  - Auto-detect from board (success → flagship/note/array, errors inline)
 *
 * The per-board controls live inside a collapsed Radix Collapsible, so each
 * test expands the card first by clicking its trigger. Radix Select / detect
 * interactions rely on the pointer-capture + scrollIntoView mocks in setup.ts.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DisplaySettings } from "@/components/settings/display-settings";

import { server } from "./mocks/server";

const API_BASE = "/api";

type BoardOverride = Record<string, unknown>;
type BoardRecord = Record<string, unknown>;

/**
 * Stateful board fixture. GET returns the current board; PUT persists the
 * incoming boards and records the request body — mirroring the real backend
 * so the component's invalidate→refetch cycle reflects each save (the
 * controlled Select reads from the refetched query data, not local state).
 *
 * `put.body` is `null` until a PUT fires; reset it between assertions.
 */
function setupBoard(board: BoardOverride) {
  const state: { boards: BoardRecord[] } = {
    boards: [
      {
        id: "default",
        name: "My Board",
        board_color: "black",
        api_mode: "cloud",
        cloud_key: "***",
        ...board,
      },
    ],
  };
  const put: { body: { boards?: BoardRecord[] } | null } = { body: null };

  server.use(
    http.get(`${API_BASE}/settings/board`, () =>
      HttpResponse.json({
        board_type: "black",
        boards: state.boards,
        devices: state.boards.map((b) => b.device_type),
      }),
    ),
    http.put(`${API_BASE}/settings/board`, async ({ request }) => {
      const body = (await request.json()) as { boards?: BoardRecord[] };
      put.body = body;
      if (body.boards) {
        // Persist, masking the token like the real backend would on read-back.
        state.boards = body.boards.map((b) => ({
          ...b,
          note_array_token: b.note_array_token ? "***" : b.note_array_token,
        }));
      }
      return HttpResponse.json({
        status: "success",
        settings: { board_type: "black", boards: state.boards, devices: state.boards.map((b) => b.device_type) },
      });
    }),
  );

  return put;
}

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

/** Render, wait for the board card, expand it, and return the card element. */
async function renderAndExpand(user: ReturnType<typeof userEvent.setup>) {
  render(<DisplaySettings />, { wrapper: TestWrapper });
  const trigger = await screen.findByText("My Board");
  await user.click(trigger);
  const card = await screen.findByTestId("board-card");
  return card;
}

describe("DisplaySettings — note-array selector", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders grouped device + preset options", async () => {
    const user = userEvent.setup();
    setupBoard({ device_type: "flagship" });
    await renderAndExpand(user);

    const combo = screen.getByLabelText("Board type and size");
    await user.click(combo);

    await waitFor(() => {
      expect(screen.getByRole("listbox")).toBeInTheDocument();
    });
    const listbox = screen.getByRole("listbox");
    // Group labels
    expect(within(listbox).getByText("Devices")).toBeInTheDocument();
    expect(within(listbox).getByText("Note arrays")).toBeInTheDocument();
    // Options
    expect(within(listbox).getByRole("option", { name: "Flagship" })).toBeInTheDocument();
    expect(within(listbox).getByRole("option", { name: "Note" })).toBeInTheDocument();
    expect(within(listbox).getByRole("option", { name: "2 side-by-side" })).toBeInTheDocument();
    expect(within(listbox).getByRole("option", { name: "4 side-by-side" })).toBeInTheDocument();
    expect(within(listbox).getByRole("option", { name: "2 stacked" })).toBeInTheDocument();
    expect(within(listbox).getByRole("option", { name: "4 stacked" })).toBeInTheDocument();
    expect(within(listbox).getByRole("option", { name: "2×2 grid" })).toBeInTheDocument();
    expect(within(listbox).getByRole("option", { name: "Custom…" })).toBeInTheDocument();
  });

  it("selecting a preset saves note_array dimensions", async () => {
    const user = userEvent.setup();
    const put = setupBoard({ device_type: "flagship" });
    await renderAndExpand(user);

    const combo = screen.getByLabelText("Board type and size");
    await user.click(combo);
    await waitFor(() => expect(screen.getByRole("listbox")).toBeInTheDocument());
    await user.click(screen.getByRole("option", { name: "2×2 grid" }));

    await waitFor(() => expect(put.body).not.toBeNull());
    const b = put.body!.boards![0];
    expect(b.device_type).toBe("note_array");
    expect(b.notes_wide).toBe(2);
    expect(b.notes_tall).toBe(2);
  });

  it("converting a local-mode single board to an array lands in cloud mode", async () => {
    const user = userEvent.setup();
    const put = setupBoard({ device_type: "flagship", api_mode: "local", host: "192.168.0.9", local_api_key: "***" });
    await renderAndExpand(user);

    const combo = screen.getByLabelText("Board type and size");
    await user.click(combo);
    await waitFor(() => expect(screen.getByRole("listbox")).toBeInTheDocument());
    await user.click(screen.getByRole("option", { name: "4 side-by-side" }));

    // Cloud is the array default — the stored "local" must not leak through
    // and swap the token field for an empty tile grid mid-conversion.
    await waitFor(() => expect(put.body).not.toBeNull());
    expect(put.body!.boards![0].api_mode).toBe("cloud");
    expect(await screen.findByText("Cloud API Token")).toBeInTheDocument();
  });

  it("resizing an existing local-mode array keeps local mode", async () => {
    const user = userEvent.setup();
    const put = setupBoard({
      device_type: "note_array",
      api_mode: "local",
      notes_wide: 2,
      notes_tall: 1,
      tiles: [{ row: 0, col: 0, host: "192.168.0.20", port: 7000, local_api_key: "***", enabled: true }],
    });
    await renderAndExpand(user);

    const combo = screen.getByLabelText("Board type and size");
    await user.click(combo);
    await waitFor(() => expect(screen.getByRole("listbox")).toBeInTheDocument());
    await user.click(screen.getByRole("option", { name: "2×2 grid" }));

    await waitFor(() => expect(put.body).not.toBeNull());
    const saved = put.body!.boards![0];
    expect(saved.api_mode).toBe("local");
    expect(saved.notes_wide).toBe(2);
    expect(saved.notes_tall).toBe(2);
  });

  it("selecting Flagship from a note array saves device_type", async () => {
    const user = userEvent.setup();
    const put = setupBoard({ device_type: "note_array", notes_wide: 2, notes_tall: 2 });
    await renderAndExpand(user);

    const combo = screen.getByLabelText("Board type and size");
    await user.click(combo);
    await waitFor(() => expect(screen.getByRole("listbox")).toBeInTheDocument());
    await user.click(screen.getByRole("option", { name: "Flagship" }));

    await waitFor(() => expect(put.body).not.toBeNull());
    expect(put.body!.boards![0].device_type).toBe("flagship");
  });
});

describe("DisplaySettings — custom W×H inputs", () => {
  it("selecting Custom reveals the W×H inputs", async () => {
    const user = userEvent.setup();
    setupBoard({ device_type: "flagship" });
    const card = await renderAndExpand(user);

    const combo = screen.getByLabelText("Board type and size");
    await user.click(combo);
    await waitFor(() => expect(screen.getByRole("listbox")).toBeInTheDocument());
    await user.click(screen.getByRole("option", { name: "Custom…" }));

    // Two number inputs render once Custom is chosen (local customOpen state).
    expect(await within(card).findByLabelText("Notes wide")).toBeInTheDocument();
    expect(within(card).getByLabelText("Notes tall")).toBeInTheDocument();
  });

  it("custom inputs validate the range (block out-of-range, persist valid)", async () => {
    const user = userEvent.setup();
    // 3×1 is a note array that matches no preset → renders as "Custom" with inputs.
    const put = setupBoard({ device_type: "note_array", notes_wide: 3, notes_tall: 1 });
    const card = await renderAndExpand(user);

    const wide = (await within(card).findByLabelText("Notes wide")) as HTMLInputElement;
    expect(within(card).getByLabelText("Notes tall")).toBeInTheDocument();
    put.body = null;

    // Out-of-range value → inline error, no PUT. fireEvent.change sets the exact
    // value in one shot (controlled number inputs drift under clear()+type()).
    fireEvent.change(wide, { target: { value: "9" } });
    expect(await within(card).findByText("Each dimension must be between 1 and 8.")).toBeInTheDocument();
    expect(put.body).toBeNull();

    // Valid value → error clears, PUT carries the new dim.
    fireEvent.change(wide, { target: { value: "5" } });
    await waitFor(() => expect(put.body).not.toBeNull());
    expect(put.body!.boards![0].notes_wide).toBe(5);
    expect(within(card).queryByText("Each dimension must be between 1 and 8.")).not.toBeInTheDocument();
  });

  it("custom inputs block zero values", async () => {
    const user = userEvent.setup();
    const put = setupBoard({ device_type: "note_array", notes_wide: 3, notes_tall: 1 });
    const card = await renderAndExpand(user);

    const wide = (await within(card).findByLabelText("Notes wide")) as HTMLInputElement;
    put.body = null;

    fireEvent.change(wide, { target: { value: "0" } });
    expect(await within(card).findByText("Each dimension must be between 1 and 8.")).toBeInTheDocument();
    expect(put.body).toBeNull();

    // Empty value is likewise blocked (NaN guard).
    fireEvent.change(wide, { target: { value: "" } });
    expect(within(card).getByText("Each dimension must be between 1 and 8.")).toBeInTheDocument();
    expect(put.body).toBeNull();
  });
});

describe("DisplaySettings — note_array_token field", () => {
  it("hides the token field for flagship and shows it for a note array", async () => {
    const user = userEvent.setup();
    setupBoard({ device_type: "flagship" });
    const card = await renderAndExpand(user);

    expect(within(card).queryByText("Cloud API Token")).not.toBeInTheDocument();

    const combo = screen.getByLabelText("Board type and size");
    await user.click(combo);
    await waitFor(() => expect(screen.getByRole("listbox")).toBeInTheDocument());
    await user.click(screen.getByRole("option", { name: "2×2 grid" }));

    expect(await within(card).findByText("Cloud API Token")).toBeInTheDocument();
  });

  it("token field is masked and saves a freshly typed value", async () => {
    const user = userEvent.setup();
    const put = setupBoard({ device_type: "note_array", notes_wide: 2, notes_tall: 2, note_array_token: "***" });
    const card = await renderAndExpand(user);

    const label = await within(card).findByText("Cloud API Token");
    const tokenInput = label.parentElement!.querySelector("input") as HTMLInputElement;
    // Masked: empty value with the "(set)" placeholder.
    expect(tokenInput.value).toBe("");
    expect(tokenInput.placeholder).toBe("••••••••••• (set)");

    // Leaving it untouched fires no token change.
    tokenInput.focus();
    tokenInput.blur();
    expect(put.body).toBeNull();

    // Typing a new value + blur persists it.
    await user.type(tokenInput, "new-secret-token");
    tokenInput.blur();
    await waitFor(() => expect(put.body).not.toBeNull());
    expect(put.body!.boards![0].note_array_token).toBe("new-secret-token");
  });
});

describe("DisplaySettings — add board picker", () => {
  /** Register a POST /settings/board/add recorder alongside the board fixture. */
  function setupAdd(board: BoardOverride) {
    setupBoard(board);
    const post: { body: BoardRecord | null } = { body: null };
    server.use(
      http.post(`${API_BASE}/settings/board/add`, async ({ request }) => {
        post.body = (await request.json()) as BoardRecord;
        return HttpResponse.json({
          status: "success",
          settings: { board_type: "black", boards: [], devices: [] },
        });
      }),
    );
    return post;
  }

  it("offers Note Array alongside Flagship and Note", async () => {
    const user = userEvent.setup();
    setupAdd({ device_type: "flagship" });
    render(<DisplaySettings />, { wrapper: TestWrapper });
    await screen.findByText("My Board");

    await user.click(screen.getByRole("button", { name: "Add Board" }));

    expect(screen.getByRole("button", { name: "Flagship" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Note" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Note Array" })).toBeInTheDocument();
  });

  it("adding a Note Array posts a 2×1 cloud-mode array", async () => {
    const user = userEvent.setup();
    const post = setupAdd({ device_type: "flagship" });
    render(<DisplaySettings />, { wrapper: TestWrapper });
    await screen.findByText("My Board");

    await user.click(screen.getByRole("button", { name: "Add Board" }));
    await user.click(screen.getByRole("button", { name: "Note Array" }));

    await waitFor(() => expect(post.body).not.toBeNull());
    expect(post.body!.device_type).toBe("note_array");
    // Smallest real array (the "2 side-by-side" preset) is the starting point.
    expect(post.body!.notes_wide).toBe(2);
    expect(post.body!.notes_tall).toBe(1);
    // Note arrays are cloud-driven today, so don't start them in local mode.
    expect(post.body!.api_mode).toBe("cloud");
  });

  it("adding a Flagship posts only the device type", async () => {
    const user = userEvent.setup();
    const post = setupAdd({ device_type: "flagship" });
    render(<DisplaySettings />, { wrapper: TestWrapper });
    await screen.findByText("My Board");

    await user.click(screen.getByRole("button", { name: "Add Board" }));
    await user.click(screen.getByRole("button", { name: "Flagship" }));

    await waitFor(() => expect(post.body).not.toBeNull());
    expect(post.body!.device_type).toBe("flagship");
    expect(post.body!.notes_wide).toBeUndefined();
  });
});

describe("DisplaySettings — note array connection (cloud token vs local tiles)", () => {
  it("switching a note array to Local API saves the mode and shows the tile grid", async () => {
    const user = userEvent.setup();
    const put = setupBoard({
      device_type: "note_array",
      notes_wide: 2,
      notes_tall: 1,
      api_mode: "cloud",
      note_array_token: "***",
    });
    const card = await renderAndExpand(user);

    // Cloud mode active: token field visible, no tile grid yet.
    expect(within(card).getByText("Cloud API Token")).toBeInTheDocument();
    expect(within(card).queryByTestId("tile-grid-assignment")).not.toBeInTheDocument();

    await user.click(within(card).getByRole("button", { name: /Local API/ }));

    await waitFor(() => expect(put.body).not.toBeNull());
    expect(put.body!.boards![0].api_mode).toBe("local");
    // After the refetch, the tile grid replaces the cloud token field.
    expect(await within(card).findByTestId("tile-grid-assignment")).toBeInTheDocument();
    expect(within(card).queryByText("Cloud API Token")).not.toBeInTheDocument();
  });

  it("a stored local-mode array renders one slot per Note with assignment status", async () => {
    const user = userEvent.setup();
    setupBoard({
      device_type: "note_array",
      notes_wide: 2,
      notes_tall: 1,
      api_mode: "local",
      tiles: [{ row: 0, col: 0, host: "192.168.0.20", port: 7000, local_api_key: "***", enabled: true }],
    });
    const card = await renderAndExpand(user);

    const grid = within(card).getByTestId("tile-grid-assignment");
    expect(grid).toBeInTheDocument();
    expect(within(card).getByText("1/2 tiles assigned")).toBeInTheDocument();
    // Assigned slot shows its host; the empty slot invites assignment.
    expect(within(card).getByTestId("tile-slot-0-0")).toHaveTextContent("192.168.0.20");
    expect(within(card).getByTestId("tile-slot-0-1")).toHaveTextContent("Assign");
  });

  it("a token-only array switched to local mode stays Connected via the cloud fallback", async () => {
    const user = userEvent.setup();
    // api_mode "local" but no tiles saved yet — the backend still drives this
    // board through its Cloud token (uses_local_tiles requires saved tiles),
    // so the UI must not flip it to "Not configured".
    setupBoard({
      device_type: "note_array",
      notes_wide: 2,
      notes_tall: 1,
      api_mode: "local",
      tiles: [],
      note_array_token: "***",
    });
    const card = await renderAndExpand(user);

    expect(within(card).getByTestId("tile-grid-assignment")).toBeInTheDocument();
    expect(within(card).getAllByText("Connected").length).toBeGreaterThan(0);
    expect(within(card).queryByText("Assign at least one tile", { exact: false })).not.toBeInTheDocument();
  });

  it("disabled tiles do not count as assigned", async () => {
    const user = userEvent.setup();
    setupBoard({
      device_type: "note_array",
      notes_wide: 2,
      notes_tall: 1,
      api_mode: "local",
      tiles: [
        { row: 0, col: 0, host: "192.168.0.20", port: 7000, local_api_key: "***", enabled: true },
        { row: 0, col: 1, host: "192.168.0.21", port: 7000, local_api_key: "***", enabled: false },
      ],
    });
    const card = await renderAndExpand(user);

    expect(within(card).getByText("1/2 tiles assigned")).toBeInTheDocument();
  });

  it("hides Auto-detect for local-mode arrays (shape is defined by tiles, not detected)", async () => {
    const user = userEvent.setup();
    setupBoard({
      device_type: "note_array",
      notes_wide: 2,
      notes_tall: 1,
      api_mode: "local",
      tiles: [{ row: 0, col: 0, host: "192.168.0.20", port: 7000, local_api_key: "***", enabled: true }],
    });
    const card = await renderAndExpand(user);

    expect(within(card).getByTestId("tile-grid-assignment")).toBeInTheDocument();
    expect(within(card).queryByRole("button", { name: "Auto-detect from board" })).not.toBeInTheDocument();
  });

  it("keeps Auto-detect for cloud arrays and single boards", async () => {
    const user = userEvent.setup();
    setupBoard({
      device_type: "note_array",
      notes_wide: 2,
      notes_tall: 1,
      api_mode: "cloud",
      note_array_token: "***",
    });
    const card = await renderAndExpand(user);

    expect(within(card).getByRole("button", { name: "Auto-detect from board" })).toBeInTheDocument();
  });

  it("moving a tile onto an occupied slot swaps the two tiles", async () => {
    const user = userEvent.setup();
    const put = setupBoard({
      device_type: "note_array",
      notes_wide: 2,
      notes_tall: 1,
      api_mode: "local",
      tiles: [
        { row: 0, col: 0, host: "192.168.0.20", port: 7000, local_api_key: "***", enabled: true },
        { row: 0, col: 1, host: "192.168.0.21", port: 7000, local_api_key: "***", enabled: true },
      ],
    });
    const card = await renderAndExpand(user);

    await user.click(within(card).getByTestId("tile-slot-0-0"));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("combobox", { name: "Move to position" }));
    await waitFor(() => expect(screen.getByRole("listbox")).toBeInTheDocument());
    await user.click(screen.getByRole("option", { name: /swap with 192\.168\.0\.21/ }));

    await waitFor(() => expect(put.body).not.toBeNull());
    const tiles = put.body!.boards![0].tiles as Array<{ row: number; col: number; host: string }>;
    const byHost = Object.fromEntries(tiles.map((tile) => [tile.host, [tile.row, tile.col]]));
    expect(byHost["192.168.0.20"]).toEqual([0, 1]);
    expect(byHost["192.168.0.21"]).toEqual([0, 0]);
  });

  it("moving a tile to an empty slot just relocates it", async () => {
    const user = userEvent.setup();
    const put = setupBoard({
      device_type: "note_array",
      notes_wide: 2,
      notes_tall: 1,
      api_mode: "local",
      tiles: [{ row: 0, col: 0, host: "192.168.0.20", port: 7000, local_api_key: "***", enabled: true }],
    });
    const card = await renderAndExpand(user);

    await user.click(within(card).getByTestId("tile-slot-0-0"));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("combobox", { name: "Move to position" }));
    await waitFor(() => expect(screen.getByRole("listbox")).toBeInTheDocument());
    await user.click(screen.getByRole("option", { name: /Slot 2 — empty/ }));

    await waitFor(() => expect(put.body).not.toBeNull());
    const tiles = put.body!.boards![0].tiles as Array<{ row: number; col: number; host: string }>;
    expect(tiles).toHaveLength(1);
    expect([tiles[0].row, tiles[0].col]).toEqual([0, 1]);
  });

  it("saving a tile from the slot dialog persists the tiles array", async () => {
    const user = userEvent.setup();
    const put = setupBoard({
      device_type: "note_array",
      notes_wide: 2,
      notes_tall: 1,
      api_mode: "local",
      tiles: [],
    });
    const card = await renderAndExpand(user);

    await user.click(within(card).getByTestId("tile-slot-0-1"));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText(/Board Host/), "192.168.0.31");
    await user.type(within(dialog).getByLabelText(/Local API Key/), "tile-key-b");
    await user.click(within(dialog).getByRole("button", { name: "Save tile" }));

    await waitFor(() => expect(put.body).not.toBeNull());
    const tiles = put.body!.boards![0].tiles as Array<Record<string, unknown>>;
    expect(tiles).toHaveLength(1);
    expect(tiles[0]).toMatchObject({
      row: 0,
      col: 1,
      host: "192.168.0.31",
      port: 7000,
      local_api_key: "tile-key-b",
      enabled: true,
    });
  });

  it("Connected badge follows the note array token, not the cloud key", async () => {
    const user = userEvent.setup();
    // Cloud key set but no array token → the array cannot actually be driven.
    setupBoard({
      device_type: "note_array",
      notes_wide: 2,
      notes_tall: 1,
      api_mode: "cloud",
      cloud_key: "***",
      note_array_token: "",
    });
    const card = await renderAndExpand(user);

    expect(within(card).queryByText("Connected")).not.toBeInTheDocument();
    expect(within(card).getAllByText("Not configured").length).toBeGreaterThan(0);
  });

  it("Connected badge shows when the note array token is set", async () => {
    const user = userEvent.setup();
    setupBoard({
      device_type: "note_array",
      notes_wide: 2,
      notes_tall: 1,
      api_mode: "cloud",
      cloud_key: "",
      note_array_token: "***",
    });
    const card = await renderAndExpand(user);

    expect(within(card).getAllByText("Connected").length).toBeGreaterThan(0);
  });
});

describe("DisplaySettings — auto-detect", () => {
  it("success → note array resolves the matching preset and persists", async () => {
    const user = userEvent.setup();
    const put = setupBoard({ device_type: "flagship" });
    server.use(
      http.post(`${API_BASE}/settings/board/:boardId/detect-size`, () =>
        HttpResponse.json({
          device_type: "note_array",
          rows: 6,
          cols: 30,
          notes_wide: 2,
          notes_tall: 2,
          matched_preset: "2×2 grid",
        }),
      ),
    );
    const card = await renderAndExpand(user);

    await user.click(within(card).getByRole("button", { name: "Auto-detect from board" }));

    await waitFor(() => expect(put.body).not.toBeNull());
    const b = put.body!.boards![0];
    expect(b.device_type).toBe("note_array");
    expect(b.notes_wide).toBe(2);
    expect(b.notes_tall).toBe(2);
  });

  it("success → flagship hides the token field", async () => {
    const user = userEvent.setup();
    const put = setupBoard({ device_type: "note_array", notes_wide: 2, notes_tall: 2 });
    server.use(
      http.post(`${API_BASE}/settings/board/:boardId/detect-size`, () =>
        HttpResponse.json({ device_type: "flagship", rows: 6, cols: 22 }),
      ),
    );
    const card = await renderAndExpand(user);

    // Token field visible for the note array.
    expect(within(card).getByText("Cloud API Token")).toBeInTheDocument();

    await user.click(within(card).getByRole("button", { name: "Auto-detect from board" }));

    await waitFor(() => expect(put.body).not.toBeNull());
    expect(put.body!.boards![0].device_type).toBe("flagship");
  });

  it("success → custom (no preset) opens the W×H inputs", async () => {
    const user = userEvent.setup();
    const put = setupBoard({ device_type: "flagship" });
    server.use(
      http.post(`${API_BASE}/settings/board/:boardId/detect-size`, () =>
        HttpResponse.json({
          device_type: "note_array",
          rows: 3,
          cols: 45,
          notes_wide: 3,
          notes_tall: 1,
          matched_preset: null,
        }),
      ),
    );
    const card = await renderAndExpand(user);

    await user.click(within(card).getByRole("button", { name: "Auto-detect from board" }));

    await waitFor(() => expect(put.body).not.toBeNull());
    expect(put.body!.boards![0].notes_wide).toBe(3);
    // Custom inputs reveal because 3×1 matches no preset.
    expect(await within(card).findByLabelText("Notes wide")).toBeInTheDocument();
    expect(within(card).getByLabelText("Notes tall")).toBeInTheDocument();
  });

  it("error (422) shows the FastAPI detail inline and fires no board PUT", async () => {
    const user = userEvent.setup();
    const put = setupBoard({ device_type: "flagship" });
    server.use(
      http.post(`${API_BASE}/settings/board/:boardId/detect-size`, () =>
        HttpResponse.json({ detail: "Board returned no layout — board may be blank or unreachable" }, { status: 422 }),
      ),
    );
    const card = await renderAndExpand(user);

    await user.click(within(card).getByRole("button", { name: "Auto-detect from board" }));

    expect(
      await within(card).findByText("Board returned no layout — board may be blank or unreachable"),
    ).toBeInTheDocument();
    expect(put.body).toBeNull();
  });

  it("error (404) surfaces the detail string", async () => {
    const user = userEvent.setup();
    setupBoard({ device_type: "flagship" });
    server.use(
      http.post(`${API_BASE}/settings/board/:boardId/detect-size`, () =>
        HttpResponse.json({ detail: "Board not found" }, { status: 404 }),
      ),
    );
    const card = await renderAndExpand(user);

    await user.click(within(card).getByRole("button", { name: "Auto-detect from board" }));
    expect(await within(card).findByText("Board not found")).toBeInTheDocument();
  });

  it("error (400) surfaces the detail string", async () => {
    const user = userEvent.setup();
    setupBoard({ device_type: "flagship" });
    server.use(
      http.post(`${API_BASE}/settings/board/:boardId/detect-size`, () =>
        HttpResponse.json({ detail: "Board is not configured" }, { status: 400 }),
      ),
    );
    const card = await renderAndExpand(user);

    await user.click(within(card).getByRole("button", { name: "Auto-detect from board" }));
    expect(await within(card).findByText("Board is not configured")).toBeInTheDocument();
  });
});
