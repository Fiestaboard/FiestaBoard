import "fake-indexeddb/auto";

import { QueryClient } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AuthStatusResponse } from "@/lib/api/auth";
import type { BoardCurrentMessageResponse, BoardSettings } from "@/lib/api/boards";
import {
  clearLastKnownBoards,
  establishBoardOwner,
  type LastKnownBoard,
  lastKnownOwner,
  readBoardSessionGeneration,
  readLastKnownBoard,
  saveLastKnownBoard,
} from "@/lib/pwa/last-known-board";
import { ownerFrom, startLastKnownRecorder, UNCHANGED_REWRITE_MS } from "@/lib/pwa/last-known-recorder";
import { clearAccountDataOnDevice } from "@/lib/pwa/sign-out";

import { seedLastKnownBoard } from "./helpers/last-known-board";

const record = (over: Partial<LastKnownBoard> = {}): LastKnownBoard => ({
  boardId: "b1",
  owner: "maya",
  message: "GOOD MORNING",
  rows: 6,
  cols: 22,
  board: null,
  savedAt: 1000,
  ...over,
});

beforeEach(async () => {
  await clearLastKnownBoards();
});

describe("last-known board store (IndexedDB)", () => {
  it("reads back the newest frame", async () => {
    await seedLastKnownBoard(record({ boardId: "b1", savedAt: 1000 }));
    await seedLastKnownBoard(record({ boardId: "b2", savedAt: 2000, message: "NEWER" }));
    expect((await readLastKnownBoard())?.message).toBe("NEWER");
  });

  it("keeps one frame per board", async () => {
    await seedLastKnownBoard(record({ message: "ONE" }));
    await seedLastKnownBoard(record({ message: "TWO", savedAt: 5 }));
    expect((await readLastKnownBoard())?.message).toBe("TWO");
  });

  it("only hands a frame to the account it was recorded for", async () => {
    await seedLastKnownBoard(record({ owner: "maya" }));
    expect(await readLastKnownBoard("rosa")).toBeNull();
    expect((await readLastKnownBoard("maya"))?.owner).toBe("maya");
  });

  it("rejects an old recorder generation after sign-out and a new verified session", async () => {
    await seedLastKnownBoard(record());
    const oldGeneration = await readBoardSessionGeneration();
    await clearAccountDataOnDevice();
    await establishBoardOwner("maya", await readBoardSessionGeneration());
    expect(await saveLastKnownBoard(record({ message: "STALE" }), oldGeneration)).toBe(false);
    expect(await readLastKnownBoard()).toBeNull();
  });

  it("hides frames immediately even when IndexedDB clear cannot open", async () => {
    await seedLastKnownBoard(record());
    const open = vi.spyOn(indexedDB, "open").mockImplementation(() => ({}) as IDBOpenDBRequest);
    try {
      const clearing = clearAccountDataOnDevice();
      expect(await readLastKnownBoard()).toBeNull();
      await clearing;
    } finally {
      open.mockRestore();
    }
  });

  it("isolates frames between two HA ingress scopes on one origin", async () => {
    vi.stubGlobal("window", { __reactRouterContext: { basename: "/ingress/one" } });
    try {
      await seedLastKnownBoard(record({ message: "ONE" }));
      vi.stubGlobal("window", { __reactRouterContext: { basename: "/ingress/two" } });
      expect(await readLastKnownBoard()).toBeNull();
      await seedLastKnownBoard(record({ message: "TWO" }));
      vi.stubGlobal("window", { __reactRouterContext: { basename: "/ingress/one" } });
      expect((await readLastKnownBoard())?.message).toBe("ONE");
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("is empty after clearing", async () => {
    await seedLastKnownBoard(record());
    await clearLastKnownBoards();
    expect(await readLastKnownBoard()).toBeNull();
    expect(await lastKnownOwner()).toBeUndefined();
  });

  it("is empty after sign out clears this device", async () => {
    await seedLastKnownBoard(record());
    await clearAccountDataOnDevice();
    expect(await readLastKnownBoard()).toBeNull();
  });
});

describe("last-known board store without IndexedDB", () => {
  const original = globalThis.indexedDB;
  beforeEach(() => {
    // @ts-expect-error simulate a browser with storage disabled
    delete globalThis.indexedDB;
  });
  afterEach(() => {
    globalThis.indexedDB = original;
  });
  it("does nothing and never throws", async () => {
    expect(await seedLastKnownBoard(record())).toBe(false);
    expect(await readLastKnownBoard()).toBeNull();
    expect(await clearLastKnownBoards()).toBe(false);
  });
});

describe("ownerFrom", () => {
  const status = (over: Partial<AuthStatusResponse>) =>
    ({ enabled: true, authenticated: true, username: "maya", ...over }) as AuthStatusResponse;
  it("is the signed-in username", () => expect(ownerFrom(status({}))).toBe("maya"));
  it("fails closed for authenticated status without a username", () => {
    expect(ownerFrom(status({ username: null }))).toBeUndefined();
  });
  it("is null on an install with sign-in off", () => expect(ownerFrom(status({ enabled: false }))).toBeNull());
  it("is unknown when nobody is signed in or there is no status yet", () => {
    expect(ownerFrom(status({ authenticated: false }))).toBeUndefined();
    expect(ownerFrom(undefined)).toBeUndefined();
  });
});

describe("startLastKnownRecorder", () => {
  const frame = (message: string): BoardCurrentMessageResponse =>
    ({
      message,
      characters: [[0]],
      rows: 6,
      cols: 22,
      cached_at: null,
      api_mode: "local",
      expected_characters: null,
    }) as BoardCurrentMessageResponse;
  const settings = {
    board_type: null,
    devices: [],
    boards: [
      {
        id: "b1",
        name: "Kitchen board",
        device_type: "flagship",
        board_color: "black",
        host: "192.0.2.10",
        api_key: "secret-key",
      },
    ],
  } as unknown as BoardSettings;

  let client: QueryClient;
  let stop: () => void;
  let now = 10_000;
  beforeEach(() => {
    client = new QueryClient();
    now = 10_000;
    stop = startLastKnownRecorder(client, () => now);
  });
  afterEach(() => stop());

  const signIn = (username: string | null, enabled = true) =>
    client.setQueryData(["auth-status"], { enabled, authenticated: username !== null, username } as AuthStatusResponse);

  it("records a polled frame for the signed-in account, with the board's display settings only", async () => {
    signIn("maya");
    client.setQueryData(["boardSettings"], settings);
    client.setQueryData(["board-current-message", "b1"], frame("HELLO"));
    await vi.waitFor(async () => expect(await readLastKnownBoard("maya")).not.toBeNull());
    const saved = (await readLastKnownBoard("maya"))!;
    expect(saved).toMatchObject({ boardId: "b1", owner: "maya", message: "HELLO", savedAt: 10_000 });
    expect(saved.board).toMatchObject({ name: "Kitchen board", device_type: "flagship" });
    expect(JSON.stringify(saved)).not.toContain("secret-key");
    expect(JSON.stringify(saved)).not.toContain("192.0.2.10");
  });

  it("does not let an old tab repopulate the store after sign-out", async () => {
    signIn("maya");
    client.setQueryData(["board-current-message", "b1"], frame("BEFORE"));
    await vi.waitFor(async () => expect(await readLastKnownBoard()).not.toBeNull());
    await clearAccountDataOnDevice();
    client.setQueryData(["board-current-message", "b1"], frame("LATE RESPONSE"));
    await new Promise((r) => setTimeout(r, 50));
    expect(await readLastKnownBoard()).toBeNull();
  });

  it("records a new account's first frame without an asynchronous clear deleting it", async () => {
    await seedLastKnownBoard(record({ owner: "maya" }));
    signIn("rosa");
    client.setQueryData(["board-current-message", "b1"], frame("ROSA"));
    await vi.waitFor(async () => expect((await readLastKnownBoard())?.message).toBe("ROSA"));
    expect((await readLastKnownBoard())?.owner).toBe("rosa");
  });

  it("cannot revive a revoked session from cached auth when a tab mounts", async () => {
    signIn("maya");
    client.setQueryData(["board-current-message", "b1"], frame("BEFORE"));
    await vi.waitFor(async () => expect(await readLastKnownBoard()).not.toBeNull());
    await clearAccountDataOnDevice();
    stop();
    stop = startLastKnownRecorder(client);
    client.setQueryData(["board-current-message", "b1"], frame("STALE"));
    await new Promise((r) => setTimeout(r, 50));
    expect(await readLastKnownBoard()).toBeNull();
  });

  it("records nothing until it knows whose data it is", async () => {
    client.setQueryData(["board-current-message", "b1"], frame("HELLO"));
    await new Promise((r) => setTimeout(r, 20));
    expect(await readLastKnownBoard()).toBeNull();
  });

  it("records for an install with sign-in off under no owner", async () => {
    signIn(null, false);
    client.setQueryData(["board-current-message"], { ...frame("OPEN"), board_id: "b9" });
    await vi.waitFor(async () => expect((await readLastKnownBoard(null))?.boardId).toBe("b9"));
  });

  it("skips a frame with no message", async () => {
    signIn("maya");
    client.setQueryData(["board-current-message", "b1"], { ...frame("x"), message: null });
    await new Promise((r) => setTimeout(r, 20));
    expect(await readLastKnownBoard()).toBeNull();
  });

  it("re-writes an unchanged frame only after a minute, to refresh its time", async () => {
    signIn("maya");
    client.setQueryData(["board-current-message", "b1"], frame("SAME"));
    await vi.waitFor(async () => expect((await readLastKnownBoard())?.savedAt).toBe(10_000));
    now = 10_000 + UNCHANGED_REWRITE_MS - 1;
    client.setQueryData(["board-current-message", "b1"], { ...frame("SAME") });
    await new Promise((r) => setTimeout(r, 20));
    expect((await readLastKnownBoard())?.savedAt).toBe(10_000);
    now = 10_000 + UNCHANGED_REWRITE_MS;
    client.setQueryData(["board-current-message", "b1"], { ...frame("SAME") });
    await vi.waitFor(async () => expect((await readLastKnownBoard())?.savedAt).toBe(now));
  });

  it("wipes the store when the auth status says nobody is signed in", async () => {
    await seedLastKnownBoard(record({ owner: "maya" }));
    signIn(null);
    await vi.waitFor(async () => expect(await readLastKnownBoard()).toBeNull());
  });

  it("wipes stored frames when enabled auth has no username", async () => {
    await seedLastKnownBoard(record({ owner: "maya" }));
    client.setQueryData(["auth-status"], { enabled: true, authenticated: true, username: null });
    await vi.waitFor(async () => expect(await readLastKnownBoard()).toBeNull());
  });

  it("wipes the store when a different account signs in", async () => {
    await seedLastKnownBoard(record({ owner: "maya" }));
    signIn("rosa");
    await vi.waitFor(async () => expect(await readLastKnownBoard()).toBeNull());
  });

  it("keeps the store when the same account is seen again", async () => {
    await seedLastKnownBoard(record({ owner: "maya" }));
    signIn("maya");
    await new Promise((r) => setTimeout(r, 30));
    expect(await readLastKnownBoard("maya")).not.toBeNull();
  });
});
