/**
 * The TV and output-plugin wizard paths create a board of their own; the
 * fresh install's untouched "My Board" placeholder must not linger as the
 * primary board — and nothing a user set up may ever be removed with it.
 */
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { isUntouchedPlaceholder, removeUntouchedPlaceholder } from "@/components/wizard/default-board";
import type { BoardInstance } from "@/lib/api";
import { upgradeWizardProgress } from "@/lib/setup-detection";

import { server } from "./mocks/server";

const PLACEHOLDER = {
  id: "placeholder",
  name: "My Board",
  device_type: "flagship",
  board_color: "black",
  enabled: true,
  api_mode: "local",
  host: "",
  local_api_key: "",
  cloud_key: "",
} as BoardInstance;

function boards(list: Partial<BoardInstance>[]) {
  const removed: string[] = [];
  server.use(
    http.get("/api/settings/board", () => HttpResponse.json({ board_type: "black", boards: list, devices: [] })),
    http.delete("/api/settings/board/:boardId", ({ params }) => {
      removed.push(String(params.boardId));
      return HttpResponse.json({ board_type: "black", boards: [], devices: [] });
    }),
  );
  return removed;
}

describe("isUntouchedPlaceholder", () => {
  it("is a Vestaboard with no connection detail at all", () => {
    expect(isUntouchedPlaceholder(PLACEHOLDER)).toBe(true);
  });

  it.each([
    ["a host", { host: "192.0.2.1" }],
    ["a Local API key", { local_api_key: "***" }],
    ["a cloud key", { cloud_key: "***" }],
    ["a note-array token", { note_array_token: "***" }],
    ["tiles", { tiles: [{ host: "192.0.2.2" }] as BoardInstance["tiles"] }],
    ["another output", { output: "recording_sign" }],
    ["a panel", { api_mode: "virtual" as const, device_type: "panel" as const }],
  ])("is not a board with %s", (_what, change) => {
    expect(isUntouchedPlaceholder({ ...PLACEHOLDER, ...change })).toBe(false);
  });
});

describe("removeUntouchedPlaceholder", () => {
  it("removes the placeholder when it is the one other board", async () => {
    const removed = boards([PLACEHOLDER, { id: "new", device_type: "panel", api_mode: "virtual" }]);
    await removeUntouchedPlaceholder("new");
    expect(removed).toEqual(["placeholder"]);
  });

  it("leaves boards alone when there is more than one other", async () => {
    const removed = boards([PLACEHOLDER, { ...PLACEHOLDER, id: "second" }, { id: "new" }]);
    await removeUntouchedPlaceholder("new");
    expect(removed).toEqual([]);
  });

  it("leaves a configured board alone", async () => {
    const removed = boards([{ ...PLACEHOLDER, host: "192.0.2.1" }, { id: "new" }]);
    await removeUntouchedPlaceholder("new");
    expect(removed).toEqual([]);
  });
});

describe("upgradeWizardProgress", () => {
  it("resumes a Vestaboard-only wizard's later step as the Vestaboard path, one step on", () => {
    expect(upgradeWizardProgress({ currentStep: 2 })).toEqual({ currentStep: 3, outputId: "vestaboard" });
  });

  it("leaves a first-step progress and new-format progress as they are", () => {
    expect(upgradeWizardProgress({ currentStep: 1 })).toEqual({ currentStep: 1 });
    expect(upgradeWizardProgress({ currentStep: 2, outputId: "fiestapanel" })).toEqual({
      currentStep: 2,
      outputId: "fiestapanel",
    });
  });
});
