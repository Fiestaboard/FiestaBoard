/**
 * Tests for the board cards in DisplaySettings (Settings → Hardware):
 *  - Grouped device/preset Select (replaces the old flagship/note pills)
 *  - Custom W×H inputs with 1..MAX_NOTES_PER_AXIS validation
 *  - The Vestaboard's settings screen, drawn from its plugin manifest (plan
 *    D13): local / cloud / note-array cloud / local tiles, scan, Get API Key
 *    from Board, identify, secrets masked and restored — saved in the
 *    settings-v4 shape (`output_config`, no flat connection fields)
 *  - Auto-detect from board (the detect action: success → flagship/note/array, errors inline)
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

/** Mirrors BoardInstance.__post_init__ (src/devices.py): strip, cap, default. */
const MAX_BOARD_NAME_LENGTH = 64;
function normalizeBoardName(name: unknown): string {
  const trimmed = typeof name === "string" ? name.trim().slice(0, MAX_BOARD_NAME_LENGTH) : "";
  return trimmed || "My Board";
}

/**
 * Stateful board fixture. GET returns the current board; PUT persists the
 * incoming boards and records the request body — mirroring the real backend
 * so the component's invalidate→refetch cycle reflects each save (the
 * controlled Select and the name input read from the refetched query data,
 * not local state).
 *
 * The PUT handler applies the backend's own name normalization, so saving
 * "" (or whitespace) reads back as "My Board" and the clear→reset round-trip
 * is actually exercised rather than echoed verbatim (issue #1792).
 *
 * `put.body` is `null` until a PUT fires and `put.count` counts them; both are
 * only meaningful after awaiting the request, since the handler is async.
 */
const FLAT = ["api_mode", "host", "port", "local_api_key", "cloud_key", "note_array_token", "tiles"] as const;
const SECRETS = ["local_api_key", "cloud_key", "note_array_token"] as const;

function maskConfig(config: BoardRecord): BoardRecord {
  const masked: BoardRecord = { ...config };
  for (const key of SECRETS) if (masked[key]) masked[key] = "***";
  if (Array.isArray(masked.tiles)) {
    masked.tiles = (masked.tiles as BoardRecord[]).map((tile) => ({
      ...tile,
      ...(tile.local_api_key ? { local_api_key: "***" } : {}),
    }));
  }
  return masked;
}

/** A stored board as `GET /settings/board` answers it (settings v4): `output_config` plus the flat view of it. */
function boardView(stored: BoardRecord): BoardRecord {
  const output = stored.output ?? (stored.api_mode === "virtual" ? "fiestapanel" : "vestaboard");
  if (output !== "vestaboard") return { ...stored, output };
  const config = maskConfig((stored.output_config ?? {}) as BoardRecord);
  return { ...stored, ...config, output, output_config: config };
}

/** A settings-v4 write merged with what was stored: echoed `"***"` secrets restored (tiles by address). */
function storeWrite(incoming: BoardRecord, before: BoardRecord | undefined): BoardRecord {
  const stored: BoardRecord = { ...incoming };
  const config = { ...((incoming.output_config ?? {}) as BoardRecord) };
  const previous = (before?.output_config ?? {}) as BoardRecord;
  for (const key of SECRETS) if (config[key] === "***") config[key] = previous[key];
  if (Array.isArray(config.tiles)) {
    const old = (previous.tiles ?? []) as BoardRecord[];
    config.tiles = (config.tiles as BoardRecord[]).map((tile) =>
      tile.local_api_key === "***"
        ? { ...tile, local_api_key: old.find((o) => o.host === tile.host)?.local_api_key }
        : tile,
    );
  }
  stored.output_config = config;
  return stored;
}

/**
 * Stateful board fixture, a stand-in for the settings-v4 backend. GET returns
 * the current board (its connection in `output_config`, secrets masked, plus
 * the flat compatibility view); PUT stores the incoming boards (echoed `"***"`
 * secrets restored) and records the request body — so the component's
 * invalidate→refetch cycle reflects each save (the controlled Select and the
 * name input read from the refetched query data, not local state).
 *
 * The PUT handler applies the backend's own name normalization, so saving
 * "" (or whitespace) reads back as "My Board" and the clear→reset round-trip
 * is actually exercised rather than echoed verbatim (issue #1792).
 *
 * `board` may give the connection in the flat shape (as a v3 file held it):
 * it is moved into `output_config`, as the v4 migration does.
 *
 * `put.body` is `null` until a PUT fires and `put.count` counts them; both are
 * only meaningful after awaiting the request, since the handler is async.
 */
function setupBoard(board: BoardOverride) {
  const seed: BoardRecord = {
    id: "default",
    name: "My Board",
    board_color: "black",
    api_mode: "cloud",
    cloud_key: "***",
    ...board,
  };
  const virtual = seed.api_mode === "virtual";
  const config: BoardRecord = {};
  const rest: BoardRecord = {};
  for (const [key, value] of Object.entries(seed)) {
    if ((FLAT as readonly string[]).includes(key)) config[key] = value;
    else rest[key] = value;
  }
  const state: { boards: BoardRecord[] } = {
    boards: [
      virtual
        ? { ...rest, output: "fiestapanel", output_config: {}, name: normalizeBoardName(rest.name) }
        : { ...rest, output: "vestaboard", output_config: config, name: normalizeBoardName(rest.name) },
    ],
  };
  const put: { body: { boards?: BoardRecord[] } | null; count: number } = { body: null, count: 0 };

  const settings = () => ({
    board_type: "black",
    boards: state.boards.map(boardView),
    devices: state.boards.map((b) => b.device_type),
  });
  server.use(
    http.get(`${API_BASE}/settings/board`, () => HttpResponse.json(settings())),
    http.put(`${API_BASE}/settings/board`, async ({ request }) => {
      const body = (await request.json()) as { boards?: BoardRecord[] };
      put.body = body;
      put.count += 1;
      if (body.boards) {
        state.boards = body.boards.map((b) => ({
          ...storeWrite(
            b,
            state.boards.find((old) => old.id === b.id),
          ),
          name: normalizeBoardName(b.name),
        }));
      }
      return HttpResponse.json({ status: "success", settings: settings() });
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

/**
 * Assert no PUT lands beyond `expected`. The MSW handler is async, so a
 * synchronous count check would pass even when a request is in flight; this
 * waits long enough for one to arrive and fails if it does.
 */
async function expectNoFurtherPuts(put: { count: number }, expected: number) {
  await expect(waitFor(() => expect(put.count).toBeGreaterThan(expected), { timeout: 300 })).rejects.toThrow();
  expect(put.count).toBe(expected);
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
    const saved = put.body!.boards![0];
    expect(saved.output_config).toMatchObject({ api_mode: "cloud", host: "192.168.0.9", local_api_key: "***" });
    expect(saved).not.toHaveProperty("api_mode");
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
    expect((saved.output_config as BoardRecord).api_mode).toBe("local");
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

describe("DisplaySettings — board name field (#1792)", () => {
  it("shows the current name and saves an edited, trimmed name on blur", async () => {
    const user = userEvent.setup();
    const put = setupBoard({ device_type: "flagship" });
    const card = await renderAndExpand(user);

    const nameInput = (await within(card).findByLabelText("Name")) as HTMLInputElement;
    expect(nameInput.value).toBe("My Board");

    fireEvent.change(nameInput, { target: { value: "  Kitchen Board  " } });
    fireEvent.blur(nameInput);

    await waitFor(() => expect(put.count).toBe(1));
    const saved = put.body!.boards![0];
    // Trimmed before saving; the rest of the board rides along unchanged in
    // the boards[] round-trip.
    expect(saved.name).toBe("Kitchen Board");
    expect(saved.device_type).toBe("flagship");
    // The card header picks up the new name after the refetch.
    expect(await screen.findByText("Kitchen Board")).toBeInTheDocument();
  });

  it("blurring without changing the name fires no PUT", async () => {
    const user = userEvent.setup();
    const put = setupBoard({ device_type: "flagship" });
    const card = await renderAndExpand(user);

    const nameInput = (await within(card).findByLabelText("Name")) as HTMLInputElement;
    fireEvent.focus(nameInput);
    fireEvent.blur(nameInput);
    // Whitespace-only padding around the same name is also not a change.
    fireEvent.change(nameInput, { target: { value: " My Board " } });
    fireEvent.blur(nameInput);

    // The PUT handler is async, so a synchronous assertion here passes whether
    // or not a request fired. Give any request that WAS made time to land, and
    // pin the request count rather than only the recorded body.
    await expectNoFurtherPuts(put, 0);
    expect(put.body).toBeNull();
  });

  it("clearing the name saves an empty string and shows the restored default", async () => {
    const user = userEvent.setup();
    const put = setupBoard({ device_type: "flagship", name: "Kitchen Board" });
    render(<DisplaySettings />, { wrapper: TestWrapper });
    await user.click(await screen.findByText("Kitchen Board"));
    const card = await screen.findByTestId("board-card");

    const nameInput = (await within(card).findByLabelText("Name")) as HTMLInputElement;
    fireEvent.change(nameInput, { target: { value: "   " } });
    fireEvent.blur(nameInput);

    await waitFor(() => expect(put.count).toBe(1));
    expect(put.body!.boards![0].name).toBe("");
    // The backend restores its default, and the field must show what is
    // actually stored — not the empty string the user left behind.
    expect(await screen.findByText("My Board")).toBeInTheDocument();
    await waitFor(() => expect(nameInput.value).toBe("My Board"));
  });

  it("re-blurring after a clear does not fire a second identical PUT", async () => {
    const user = userEvent.setup();
    const put = setupBoard({ device_type: "flagship", name: "Kitchen Board" });
    render(<DisplaySettings />, { wrapper: TestWrapper });
    await user.click(await screen.findByText("Kitchen Board"));
    const card = await screen.findByTestId("board-card");

    const nameInput = (await within(card).findByLabelText("Name")) as HTMLInputElement;
    fireEvent.change(nameInput, { target: { value: "" } });
    fireEvent.blur(nameInput);

    await waitFor(() => expect(put.count).toBe(1));
    await screen.findByText("My Board");

    // A field left showing "" while the server holds "My Board" reads as
    // changed on every blur. Each PUT re-runs _reinitialize_board_clients()
    // and rewrites config.json, so the repeat is not merely cosmetic.
    fireEvent.focus(nameInput);
    fireEvent.blur(nameInput);
    await expectNoFurtherPuts(put, 1);
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

    const tokenInput = (await within(card).findByLabelText(/Cloud API Token/)) as HTMLInputElement;
    // Masked: empty value with the "(set)" placeholder.
    expect(tokenInput.value).toBe("");
    expect(tokenInput.placeholder).toBe("••••••••••• (set)");

    // Untouched, there is nothing to save.
    expect(within(card).getByRole("button", { name: "Save settings" })).toBeDisabled();

    // Typing a new value and saving persists it, in output_config.
    await user.type(tokenInput, "new-secret-token");
    await user.click(within(card).getByRole("button", { name: "Save settings" }));
    await waitFor(() => expect(put.body).not.toBeNull());
    expect((put.body!.boards![0].output_config as BoardRecord).note_array_token).toBe("new-secret-token");
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
    expect(post.body!.output).toBe("vestaboard");
    expect(post.body!.output_config).toEqual({ api_mode: "cloud" });
    expect(post.body).not.toHaveProperty("api_mode");
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

/** Click the screen's "Save settings" and wait for the PUT it fires. */
async function saveSettings(user: ReturnType<typeof userEvent.setup>, card: HTMLElement, put: { count: number }) {
  const before = put.count;
  await user.click(within(card).getByRole("button", { name: "Save settings" }));
  await waitFor(() => expect(put.count).toBe(before + 1));
}

/** The settings-v4 write of the first board: its connection in output_config, no flat fields. */
function savedConfig(put: { body: { boards?: BoardRecord[] } | null }): Record<string, unknown> {
  const board = put.body!.boards![0];
  for (const field of FLAT) expect(board, `flat ${field} written`).not.toHaveProperty(field);
  return board.output_config as Record<string, unknown>;
}

function result(overrides: Record<string, unknown> = {}) {
  return { status: "ok", message: "", guidance: [], fields: null, geometry: null, devices: null, ...overrides };
}

/** Record every saved-board action call (`POST /boards/default/actions/{action}`). */
function recordActions(answer: (action: string, body: Record<string, unknown>) => Record<string, unknown>) {
  const calls: { action: string; body: Record<string, unknown> }[] = [];
  server.use(
    http.post(`${API_BASE}/boards/default/actions/:action`, async ({ request, params }) => {
      const body = (await request.json()) as Record<string, unknown>;
      calls.push({ action: String(params.action), body });
      return HttpResponse.json(answer(String(params.action), body));
    }),
  );
  return calls;
}

describe("DisplaySettings — a Vestaboard's settings screen (from its manifest)", () => {
  it("a local Flagship shows its address, key and port, and saves them in output_config", async () => {
    const user = userEvent.setup();
    const put = setupBoard({ device_type: "flagship", api_mode: "local", host: "", local_api_key: "" });
    const card = await renderAndExpand(user);

    expect(within(card).getByRole("radio", { name: /Local API/ })).toHaveAttribute("aria-checked", "true");
    expect(within(card).queryByLabelText(/Read\/Write API Key/)).not.toBeInTheDocument();
    expect(within(card).getByText("Still needed: Board IP Address, Local API Key")).toBeInTheDocument();
    await user.type(within(card).getByLabelText(/Board IP Address/), "192.168.0.40");
    await user.type(within(card).getByLabelText(/Local API Key/), "test-local-key");
    await saveSettings(user, card, put);

    expect(savedConfig(put)).toMatchObject({
      api_mode: "local",
      host: "192.168.0.40",
      local_api_key: "test-local-key",
    });
    expect(put.body!.boards![0].output).toBe("vestaboard");
  });

  it("a cloud Flagship shows only the Read/Write key", async () => {
    const user = userEvent.setup();
    const put = setupBoard({ device_type: "flagship", api_mode: "local", host: "192.168.0.40", local_api_key: "***" });
    const card = await renderAndExpand(user);

    await user.click(within(card).getByRole("radio", { name: /Cloud API/ }));
    expect(within(card).queryByLabelText(/Board IP Address/)).not.toBeInTheDocument();
    expect(within(card).queryByLabelText(/Local API Key/)).not.toBeInTheDocument();
    await user.type(within(card).getByLabelText(/Read\/Write API Key/), "test-cloud-key");
    await saveSettings(user, card, put);

    expect(savedConfig(put)).toMatchObject({ api_mode: "cloud", cloud_key: "test-cloud-key" });
  });

  it("a cloud note array shows only its Cloud API token", async () => {
    const user = userEvent.setup();
    setupBoard({ device_type: "note_array", notes_wide: 2, notes_tall: 1, api_mode: "cloud", note_array_token: "" });
    const card = await renderAndExpand(user);

    expect(within(card).getByLabelText(/Cloud API Token/)).toBeInTheDocument();
    expect(within(card).queryByLabelText(/Read\/Write API Key/)).not.toBeInTheDocument();
    expect(within(card).queryByTestId("tile-grid-assignment")).not.toBeInTheDocument();
    expect(within(card).getByText("Still needed: Cloud API Token")).toBeInTheDocument();
  });

  it("a saved secret reads as set, cannot be revealed, and stays masked when untouched", async () => {
    const user = userEvent.setup();
    const put = setupBoard({ device_type: "flagship", api_mode: "local", host: "192.168.0.40", local_api_key: "***" });
    const card = await renderAndExpand(user);

    const key = within(card).getByLabelText(/Local API Key/) as HTMLInputElement;
    expect(key.value).toBe("");
    expect(key.placeholder).toBe("••••••••••• (set)");
    expect(within(card).queryByText(/Still needed/)).not.toBeInTheDocument();
    // Editing another field and saving echoes the mask: the server restores it.
    await user.type(within(card).getByLabelText(/Board IP Address/), "1");
    await saveSettings(user, card, put);
    expect(savedConfig(put)).toMatchObject({ host: "192.168.0.401", local_api_key: "***" });
  });

  it("typing over a saved secret replaces it; clearing what was typed restores it", async () => {
    const user = userEvent.setup();
    const put = setupBoard({ device_type: "flagship", api_mode: "local", host: "192.168.0.40", local_api_key: "***" });
    const card = await renderAndExpand(user);

    const key = within(card).getByLabelText(/Local API Key/) as HTMLInputElement;
    await user.type(key, "x");
    await user.clear(key);
    expect(within(card).getByRole("button", { name: "Save settings" })).toBeDisabled();
    await user.type(key, "test-new-key");
    await saveSettings(user, card, put);
    expect(savedConfig(put).local_api_key).toBe("test-new-key");
  });

  it("scanning the network fills the address from the board picked", async () => {
    const user = userEvent.setup();
    const put = setupBoard({ device_type: "flagship", api_mode: "local", host: "", local_api_key: "***" });
    const calls = recordActions(() =>
      result({
        message: "Found 1 board(s).",
        devices: [{ ip: "192.168.0.77", port: 7000, hostname: "vestaboard.local", source: "mdns", label: null }],
      }),
    );
    const card = await renderAndExpand(user);

    // Discover is the address field's own button, not a separate action.
    expect(within(card).queryByRole("button", { name: "Scan network for boards" })).not.toBeInTheDocument();
    await user.click(within(card).getByRole("button", { name: "Find devices" }));
    await user.click(await within(card).findByRole("radio", { name: /vestaboard\.local/ }));
    expect(calls.map((c) => c.action)).toEqual(["discover"]);
    await saveSettings(user, card, put);
    expect(savedConfig(put).host).toBe("192.168.0.77");
  });

  it("Get API Key from Board asks for the token and fills the key as a secret", async () => {
    const user = userEvent.setup();
    const put = setupBoard({ device_type: "flagship", api_mode: "local", host: "192.168.0.40", local_api_key: "" });
    const calls = recordActions(() =>
      result({
        message: "Local API enabled.",
        fields: { api_key: { value: "test-issued-key", secret: true, fills: "local_api_key" } },
      }),
    );
    const card = await renderAndExpand(user);

    await user.click(within(card).getByRole("button", { name: "Get API Key from Board" }));
    const dialog = await screen.findByRole("dialog");
    // The address comes from the form; the token is asked for.
    expect(within(dialog).getByLabelText(/Board IP Address/)).toHaveValue("192.168.0.40");
    const next = within(dialog).getByRole("button", { name: "Next" });
    expect(next).toBeDisabled();
    await user.type(within(dialog).getByLabelText(/Enablement Token/), "test-enablement-token");
    await user.click(next);

    expect(await within(card).findByText("Local API enabled.")).toBeInTheDocument();
    expect(calls[0]).toEqual({
      action: "enable_local_api",
      body: {
        input: { host: "192.168.0.40", enablement_token: "test-enablement-token" },
        output_config: expect.objectContaining({ api_mode: "local", host: "192.168.0.40" }),
      },
    });
    const key = within(card).getByLabelText(/Local API Key/);
    expect(key).toHaveAttribute("type", "password");
    expect(key).toHaveValue("test-issued-key");
    expect(within(card).getByText("Filled in: Local API Key")).toBeInTheDocument();
    await saveSettings(user, card, put);
    expect(savedConfig(put).local_api_key).toBe("test-issued-key");
  });

  it("Test Connection runs on the saved board with the edited settings, secrets still masked", async () => {
    const user = userEvent.setup();
    setupBoard({ device_type: "flagship", api_mode: "local", host: "192.168.0.40", local_api_key: "***" });
    const calls = recordActions(() =>
      result({ status: "error", message: "Could not connect to the board.", guidance: ["Check the IP."] }),
    );
    const card = await renderAndExpand(user);

    await user.click(within(card).getByRole("button", { name: "Test Connection" }));
    const panel = await within(card).findByTestId("action-result");
    expect(panel).toHaveAttribute("data-status", "error");
    expect(within(panel).getByText("Check the IP.")).toBeInTheDocument();
    expect(calls[0].body.output_config).toMatchObject({ host: "192.168.0.40", local_api_key: "***" });
  });
});

describe("DisplaySettings — note array connection (cloud token vs local tiles)", () => {
  it("switching a note array to Local API shows the tile grid and saves the mode", async () => {
    const user = userEvent.setup();
    const put = setupBoard({
      device_type: "note_array",
      notes_wide: 2,
      notes_tall: 1,
      api_mode: "cloud",
      note_array_token: "***",
    });
    const card = await renderAndExpand(user);

    expect(within(card).getByText("Cloud API Token")).toBeInTheDocument();
    expect(within(card).queryByTestId("tile-grid-assignment")).not.toBeInTheDocument();

    await user.click(within(card).getByRole("radio", { name: /Local API/ }));
    expect(await within(card).findByTestId("tile-grid-assignment")).toBeInTheDocument();
    expect(within(card).getByTestId("tile-slot-0-0")).toBeInTheDocument();
    expect(within(card).getByTestId("tile-slot-0-1")).toBeInTheDocument();
    expect(within(card).getByText("0/2 tiles assigned")).toBeInTheDocument();
    expect(within(card).queryByText("Cloud API Token")).not.toBeInTheDocument();

    await saveSettings(user, card, put);
    expect(savedConfig(put).api_mode).toBe("local");
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

    expect(within(card).getByTestId("tile-grid-assignment")).toBeInTheDocument();
    expect(within(card).getByText("1/2 tiles assigned")).toBeInTheDocument();
    // Assigned slot shows its address; the empty slot invites assignment.
    expect(within(card).getByTestId("tile-slot-0-0")).toHaveTextContent("192.168.0.20");
    expect(within(card).getByTestId("tile-slot-0-0")).toHaveAttribute("data-assigned", "true");
    expect(within(card).getByTestId("tile-slot-0-1")).toHaveTextContent("Assign");
  });

  it("a token-only array switched to local mode stays Connected via the cloud fallback", async () => {
    const user = userEvent.setup();
    // api_mode "local" but no tiles saved yet — the backend still drives this
    // board through its Cloud token (uses_local_tiles requires saved tiles),
    // so the card must not flip it to "Not configured".
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

  it("two tiles on one address are flagged", async () => {
    const user = userEvent.setup();
    setupBoard({
      device_type: "note_array",
      notes_wide: 2,
      notes_tall: 1,
      api_mode: "local",
      tiles: [
        { row: 0, col: 0, host: "192.168.0.20", port: 7000, local_api_key: "***", enabled: true },
        { row: 0, col: 1, host: "192.168.0.20", port: 7000, local_api_key: "***", enabled: true },
      ],
    });
    const card = await renderAndExpand(user);

    expect(within(card).getByRole("alert")).toHaveTextContent("192.168.0.20:7000");
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
    // The grid gets keys and identifies per tile: neither is repeated as a button.
    expect(within(card).queryByRole("button", { name: "Get API Key from Board" })).not.toBeInTheDocument();
    expect(within(card).queryByRole("button", { name: "Identify" })).not.toBeInTheDocument();
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
    await saveSettings(user, card, put);

    const tiles = savedConfig(put).tiles as Array<{ row: number; col: number; host: string; local_api_key: string }>;
    const byHost = Object.fromEntries(tiles.map((tile) => [tile.host, [tile.row, tile.col]]));
    expect(byHost["192.168.0.20"]).toEqual([0, 1]);
    expect(byHost["192.168.0.21"]).toEqual([0, 0]);
    // Keys travel masked; the server matches them to their Notes by address.
    expect(tiles.every((tile) => tile.local_api_key === "***")).toBe(true);
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
    await saveSettings(user, card, put);

    const tiles = savedConfig(put).tiles as Array<{ row: number; col: number }>;
    expect(tiles).toHaveLength(1);
    expect([tiles[0].row, tiles[0].col]).toEqual([0, 1]);
  });

  it("assigning a tile from its slot's dialog saves it in output_config.tiles", async () => {
    const user = userEvent.setup();
    const put = setupBoard({ device_type: "note_array", notes_wide: 2, notes_tall: 1, api_mode: "local", tiles: [] });
    const card = await renderAndExpand(user);

    await user.click(within(card).getByTestId("tile-slot-0-1"));
    const dialog = await screen.findByRole("dialog");
    const saveTile = within(dialog).getByRole("button", { name: "Save tile" });
    expect(saveTile).toBeDisabled();
    await user.type(within(dialog).getByLabelText(/Board IP Address/), "192.168.0.31");
    await user.type(within(dialog).getByLabelText(/Local API Key/), "tile-key-b");
    await user.click(saveTile);
    expect(within(card).getByText("1/2 tiles assigned")).toBeInTheDocument();
    await saveSettings(user, card, put);

    const tiles = savedConfig(put).tiles as Array<Record<string, unknown>>;
    expect(tiles).toHaveLength(1);
    expect(tiles[0]).toMatchObject({ row: 0, col: 1, host: "192.168.0.31", local_api_key: "tile-key-b" });
  });

  it("identifies a saved tile by its position, never with its masked key", async () => {
    const user = userEvent.setup();
    setupBoard({
      device_type: "note_array",
      notes_wide: 2,
      notes_tall: 1,
      api_mode: "local",
      tiles: [{ row: 0, col: 1, host: "192.168.0.21", port: 7000, local_api_key: "***", enabled: true }],
    });
    const calls = recordActions(() => result({ message: "Identified 1 tile(s)." }));
    const card = await renderAndExpand(user);

    await user.click(within(card).getByTestId("tile-slot-0-1"));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Identify" }));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].action).toBe("identify");
    expect(calls[0].body.input).toEqual({ row: 0, col: 1 });
  });

  it("identifies an unsaved tile with the address and key typed into it", async () => {
    const user = userEvent.setup();
    setupBoard({ device_type: "note_array", notes_wide: 2, notes_tall: 1, api_mode: "local", tiles: [] });
    const calls = recordActions(() => result({ message: "Identified 1 tile(s)." }));
    const card = await renderAndExpand(user);

    await user.click(within(card).getByTestId("tile-slot-0-0"));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText(/Board IP Address/), "192.168.0.30");
    await user.type(within(dialog).getByLabelText(/Local API Key/), "test-tile-key");
    await user.click(within(dialog).getByRole("button", { name: "Identify" }));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body.input).toEqual({ row: 0, col: 0, host: "192.168.0.30", local_api_key: "test-tile-key" });
  });

  it("Identify all flashes every tile", async () => {
    const user = userEvent.setup();
    setupBoard({
      device_type: "note_array",
      notes_wide: 2,
      notes_tall: 1,
      api_mode: "local",
      tiles: [{ row: 0, col: 0, host: "192.168.0.20", port: 7000, local_api_key: "***", enabled: true }],
    });
    const calls = recordActions(() => result({ message: "Identified 1 tile(s)." }));
    const card = await renderAndExpand(user);

    await user.click(within(card).getByRole("button", { name: "Identify all" }));
    expect(await within(card).findByText("Identified 1 tile(s).")).toBeInTheDocument();
    expect(calls[0]).toMatchObject({ action: "identify", body: { input: { target: "all" } } });
  });

  it("gets a tile's key from its Note into that tile, not the board", async () => {
    const user = userEvent.setup();
    const put = setupBoard({ device_type: "note_array", notes_wide: 2, notes_tall: 1, api_mode: "local", tiles: [] });
    const calls = recordActions(() =>
      result({
        message: "Local API enabled.",
        fields: { api_key: { value: "test-tile-issued", secret: true, fills: "local_api_key" } },
      }),
    );
    const card = await renderAndExpand(user);

    await user.click(within(card).getByTestId("tile-slot-0-1"));
    const tileDialog = await screen.findByRole("dialog");
    await user.type(within(tileDialog).getByLabelText(/Board IP Address/), "192.168.0.31");
    await user.click(within(tileDialog).getByRole("button", { name: "Get API Key from Board" }));
    // The token is asked for in the tile's own dialog; the address is the tile's.
    const asked = within(tileDialog).getByRole("group", { name: "Get API Key from Board" });
    expect(within(asked).queryByLabelText(/Board IP Address/)).not.toBeInTheDocument();
    await user.type(within(asked).getByLabelText(/Enablement Token/), "test-enablement-token");
    await user.click(within(asked).getByRole("button", { name: "Next" }));

    const dialog = tileDialog;
    await waitFor(() => expect(within(dialog).getByLabelText(/Local API Key/)).toHaveValue("test-tile-issued"));
    expect(calls[0].body.input).toEqual({ host: "192.168.0.31", enablement_token: "test-enablement-token" });
    await user.click(within(dialog).getByRole("button", { name: "Save tile" }));
    await saveSettings(user, card, put);

    const config = savedConfig(put);
    expect(config.tiles).toEqual([{ row: 0, col: 1, host: "192.168.0.31", local_api_key: "test-tile-issued" }]);
    expect(config.local_api_key ?? "").toBe("");
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

describe("DisplaySettings — virtual boards (FiestaPanel)", () => {
  /** A panel's backing virtual board, as created by POST /panels. */
  const VIRTUAL_BOARD: BoardOverride = {
    device_type: "note_array",
    api_mode: "virtual",
    notes_wide: 4,
    notes_tall: 3,
    name: "My Board",
    local_api_key: "",
    cloud_key: "",
    note_array_token: "",
    host: "",
  };

  function setupPanels(panels: Array<Record<string, unknown>>) {
    server.use(http.get(`${API_BASE}/panels`, () => HttpResponse.json({ panels, total: panels.length })));
  }

  it("shows the FiestaPanel badge instead of Not configured", async () => {
    setupBoard(VIRTUAL_BOARD);
    render(<DisplaySettings />, { wrapper: TestWrapper });
    await screen.findByText("My Board");

    expect(screen.queryByText("Not configured")).not.toBeInTheDocument();
    expect(screen.getByText("FiestaPanel")).toBeInTheDocument();
  });

  it("hides the connection credentials form and explains the virtual board", async () => {
    const user = userEvent.setup();
    setupBoard(VIRTUAL_BOARD);
    const card = await renderAndExpand(user);

    // No API-mode toggle: clicking Local/Cloud would flip the board out of
    // virtual mode and silently break the panel.
    expect(within(card).queryByRole("radio", { name: /Local API/ })).not.toBeInTheDocument();
    expect(within(card).queryByRole("radio", { name: /Cloud API/ })).not.toBeInTheDocument();
    // "Cloud API Token" / "Board Host" are deliberately NOT asserted here:
    // neither renders for a note_array board on main either, so they would
    // pass with this change reverted. The radios and the hint below are what
    // actually discriminate.
    expect(within(card).getByTestId("virtual-board-hint")).toBeInTheDocument();
  });

  it("hides the type selector and auto-detect (grid is owned by the panel's TV size)", async () => {
    const user = userEvent.setup();
    setupBoard(VIRTUAL_BOARD);
    const card = await renderAndExpand(user);

    expect(within(card).queryByLabelText("Board type and size")).not.toBeInTheDocument();
    expect(within(card).queryByRole("button", { name: "Auto-detect from board" })).not.toBeInTheDocument();
  });

  /** Two-board fixture (physical + virtual) so the last-board guard doesn't
   *  mask the panel guard; returns the expanded virtual board's card. */
  async function renderTwoBoardsAndExpandVirtual(user: ReturnType<typeof userEvent.setup>) {
    const boards = [
      { id: "b1", name: "Physical", device_type: "flagship", api_mode: "cloud", cloud_key: "***" },
      { ...VIRTUAL_BOARD, id: "b2", name: "Living Room (Panel)" },
    ];
    server.use(
      http.get(`${API_BASE}/settings/board`, () =>
        HttpResponse.json({
          board_type: "black",
          boards,
          devices: boards.map((b) => b.device_type),
        }),
      ),
    );
    render(<DisplaySettings />, { wrapper: TestWrapper });
    const trigger = await screen.findByText("Living Room (Panel)");
    await user.click(trigger);
    const cards = await screen.findAllByTestId("board-card");
    const card = cards.find((c) => within(c).queryByText("Living Room (Panel)") !== null);
    expect(card).toBeDefined();
    return card!;
  }

  it("disables Remove Board while a panel still references the virtual board", async () => {
    const user = userEvent.setup();
    setupPanels([{ id: "p1", short_code: 1, name: "Living Room", board_id: "b2" }]);

    const card = await renderTwoBoardsAndExpandVirtual(user);
    await waitFor(() => expect(within(card).getByRole("button", { name: "Remove Board" })).toBeDisabled());
  });

  it("keeps Remove Board enabled for an orphaned virtual board (its panel is gone)", async () => {
    const user = userEvent.setup();
    setupPanels([]);

    const card = await renderTwoBoardsAndExpandVirtual(user);
    expect(within(card).getByRole("button", { name: "Remove Board" })).toBeEnabled();
  });
});

describe("DisplaySettings — auto-detect (the Vestaboard's detect action)", () => {
  /** Answer the saved board's detect action with *geometry*, or fail it with *status* and *detail*. */
  function detect(answer: { geometry?: Record<string, unknown>; status?: number; detail?: string }) {
    server.use(
      http.post(`${API_BASE}/boards/default/actions/detect_geometry`, () =>
        answer.status
          ? HttpResponse.json({ detail: answer.detail }, { status: answer.status })
          : HttpResponse.json({
              status: "ok",
              message: "Size detected.",
              guidance: [],
              fields: null,
              devices: null,
              geometry: { notes_wide: null, notes_tall: null, matched_preset: null, ...answer.geometry },
            }),
      ),
    );
  }

  it("success → note array resolves the matching preset and persists", async () => {
    const user = userEvent.setup();
    const put = setupBoard({ device_type: "flagship" });
    detect({
      geometry: {
        device_type: "note_array",
        rows: 6,
        cols: 30,
        notes_wide: 2,
        notes_tall: 2,
        matched_preset: "2×2 grid",
      },
    });
    const card = await renderAndExpand(user);

    await user.click(within(card).getByRole("button", { name: "Auto-detect from board" }));

    // Applied without asking (the action is auto_apply): no "Apply size" step.
    await waitFor(() => expect(put.body).not.toBeNull());
    const b = put.body!.boards![0];
    expect(b.device_type).toBe("note_array");
    expect(b.notes_wide).toBe(2);
    expect(b.notes_tall).toBe(2);
    expect(within(card).queryByRole("button", { name: "Apply size" })).not.toBeInTheDocument();
  });

  it("success → flagship hides the token field", async () => {
    const user = userEvent.setup();
    const put = setupBoard({ device_type: "note_array", notes_wide: 2, notes_tall: 2 });
    detect({ geometry: { device_type: "flagship", rows: 6, cols: 22 } });
    const card = await renderAndExpand(user);

    // Token field visible for the note array.
    expect(within(card).getByText("Cloud API Token")).toBeInTheDocument();

    await user.click(within(card).getByRole("button", { name: "Auto-detect from board" }));

    await waitFor(() => expect(put.body).not.toBeNull());
    expect(put.body!.boards![0].device_type).toBe("flagship");
    await waitFor(() => expect(within(card).queryByText("Cloud API Token")).not.toBeInTheDocument());
  });

  it("success → custom (no preset) opens the W×H inputs", async () => {
    const user = userEvent.setup();
    const put = setupBoard({ device_type: "flagship" });
    detect({ geometry: { device_type: "note_array", rows: 3, cols: 45, notes_wide: 3, notes_tall: 1 } });
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
    detect({ status: 422, detail: "Board returned no layout — board may be blank or unreachable" });
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
    detect({ status: 404, detail: "Board not found" });
    const card = await renderAndExpand(user);

    await user.click(within(card).getByRole("button", { name: "Auto-detect from board" }));
    expect(await within(card).findByText("Board not found")).toBeInTheDocument();
  });

  it("error (400) surfaces the detail string", async () => {
    const user = userEvent.setup();
    setupBoard({ device_type: "flagship" });
    detect({ status: 400, detail: "Board is not configured" });
    const card = await renderAndExpand(user);

    await user.click(within(card).getByRole("button", { name: "Auto-detect from board" }));
    expect(await within(card).findByText("Board is not configured")).toBeInTheDocument();
  });
});
