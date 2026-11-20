import { describe, expect, it, vi } from "vitest";

import type { ActiveScheduleResponse, BoardInstance, Collection, ScheduleEntry } from "@/lib/api";
import { drawnDifferently } from "@/lib/charset-issues";
import { deriveEditState, derivePreviewDisplay, offersDraft } from "@/lib/ide/edit-state";
import { ideDataSources, inspectorTabIds, isIdeTabId, resolveInspectorTab } from "@/lib/ide/inspector-tabs";
import { jumpToTemplateLine, lineStartPosition, textOffsetOfLine } from "@/lib/ide/jump-to-line";
import { problemsFromValidation, substitutionSummary, warningsFromCharset } from "@/lib/ide/problems";
import { changedRows, changeRegions } from "@/lib/ide/revision-diff";
import { sendLogModel } from "@/lib/ide/sends";
import { showsOnModel, windowHolds } from "@/lib/ide/shows-on";

describe("inspector tabs (Jev desktop_console_two_option)", () => {
  it("draws five tabs on desktop with Problems docked in the console", () => {
    expect(inspectorTabIds(true)).toEqual(["data", "logic", "page", "shows-on", "history"]);
  });
  it("adds Problems as the sixth tab below 1024 px", () => {
    expect(inspectorTabIds(false)).toEqual(["data", "logic", "page", "shows-on", "problems", "history"]);
  });
  it("falls back to Page when Problems disappears at desktop width", () => {
    expect(resolveInspectorTab("problems", true)).toBe("page");
    expect(resolveInspectorTab("problems", false)).toBe("problems");
    expect(resolveInspectorTab("history", true)).toBe("history");
  });
  it("offers Live and Sample on desktop and brings Missing back below 1024 px", () => {
    expect(ideDataSources(true)).toEqual(["live", "sample"]);
    expect(ideDataSources(false)).toEqual(["live", "sample", "missing"]);
  });
  it("recognises tab ids", () => {
    expect(isIdeTabId("shows-on")).toBe(true);
    expect(isIdeTabId("console")).toBe(false);
    expect(isIdeTabId(3)).toBe(false);
  });
});

describe("edit state chip derivation", () => {
  it("is Testing while edits are mirrored to a board", () => {
    expect(deriveEditState({ unsaved: true, hasDraft: true, mirroring: true })).toBe("testing");
  });
  it("is Unsaved for edits nowhere else", () => {
    expect(deriveEditState({ unsaved: true, hasDraft: true, mirroring: false })).toBe("unsaved");
  });
  it("is Draft when the hub holds a draft and nothing is unsaved", () => {
    expect(deriveEditState({ unsaved: false, hasDraft: true, mirroring: false })).toBe("draft");
  });
  it("is Saved otherwise", () => {
    expect(deriveEditState({ unsaved: false, hasDraft: false, mirroring: false })).toBe("saved");
  });
  it("derives the display state and when to offer Save draft", () => {
    expect(derivePreviewDisplay(true, false)).toBe("live");
    expect(derivePreviewDisplay(false, true)).toBe("scheduled");
    expect(derivePreviewDisplay(false, false)).toBe("not-scheduled");
    expect(offersDraft("live")).toBe(true);
    expect(offersDraft("scheduled")).toBe(true);
    expect(offersDraft("not-scheduled")).toBe(false);
  });
});

function fakeEditor(nodes: { name: string; pos: number }[]) {
  const run = vi.fn(() => true);
  const setTextSelection = vi.fn(() => ({ scrollIntoView: () => ({ run }) }));
  return {
    run,
    setTextSelection,
    editor: {
      state: {
        doc: {
          content: { size: 100 },
          descendants: (visit: (node: { type: { name: string } }, pos: number) => boolean | void) => {
            for (const node of nodes) if (visit({ type: { name: node.name } }, node.pos) === false) return;
          },
        },
      },
      chain: () => ({ focus: () => ({ setTextSelection }) }),
    },
  };
}

describe("jump to source", () => {
  it("finds the position after the (line-1)th hard break", () => {
    const { editor } = fakeEditor([
      { name: "text", pos: 1 },
      { name: "hardBreak", pos: 6 },
      { name: "text", pos: 7 },
      { name: "hardBreak", pos: 12 },
    ]);
    expect(lineStartPosition(editor, 1)).toBe(1);
    expect(lineStartPosition(editor, 2)).toBe(7);
    expect(lineStartPosition(editor, 3)).toBe(13);
    expect(lineStartPosition(editor, 4)).toBeNull();
    expect(lineStartPosition(editor, 0)).toBeNull();
  });
  it("finds a textarea offset per line", () => {
    expect(textOffsetOfLine("AB\nCD\nEF", 1)).toBe(0);
    expect(textOffsetOfLine("AB\nCD\nEF", 3)).toBe(6);
    expect(textOffsetOfLine("AB", 2)).toBeNull();
    expect(textOffsetOfLine("AB", 0)).toBeNull();
  });
  it("moves the rich editor caret to the line", () => {
    const { editor, setTextSelection, run } = fakeEditor([{ name: "hardBreak", pos: 4 }]);
    const root = document.createElement("div");
    const dom = Object.assign(document.createElement("div"), { editor });
    dom.setAttribute("aria-label", "Template editor");
    root.append(dom);
    expect(jumpToTemplateLine(2, root)).toBe(true);
    expect(setTextSelection).toHaveBeenCalledWith(5);
    expect(run).toHaveBeenCalled();
    expect(jumpToTemplateLine(9, root)).toBe(false);
  });
  it("selects the line start in the plain editor", () => {
    const root = document.createElement("div");
    const area = document.createElement("textarea");
    area.id = "page-template-plain";
    area.value = "ONE\nTWO";
    root.append(area);
    document.body.append(root);
    expect(jumpToTemplateLine(2, root)).toBe(true);
    expect(area.selectionStart).toBe(4);
    expect(document.activeElement).toBe(area);
    expect(jumpToTemplateLine(5, root)).toBe(false);
    root.remove();
  });
  it("reports false when no editor is mounted", () => {
    expect(jumpToTemplateLine(1, document.createElement("div"))).toBe(false);
  });
});

describe("problems", () => {
  it("maps every board-width validation error to an error with its line", () => {
    const problems = problemsFromValidation([
      { line: 12, column: 4, message: "muni.next doesn't exist", code: "unknown_field" },
      { line: 7, column: 29, message: "needs 31 of 29 columns", code: "line_too_long", max_length: 31 },
    ]);
    expect(problems.map((p) => [p.severity, p.kind, p.line])).toEqual([
      ["error", "unknown_field", 12],
      ["error", "line_too_long", 7],
    ]);
    expect(new Set(problems.map((p) => p.id)).size).toBe(2);
  });
  it("turns charset substitutions into one warning per distinct row substitution", () => {
    const issue = (row: number, from: string, to: string) => ({
      row,
      col: 0,
      reason: "char" as const,
      token: { type: "char" as const, value: from },
      fallback: { type: "char" as const, value: to },
    });
    const warnings = warningsFromCharset([issue(0, "é", "E"), issue(0, "é", "E"), issue(2, "é", "E")]);
    expect(warnings).toHaveLength(2);
    expect(warnings[1]).toMatchObject({ severity: "warning", kind: "substitution", line: 3, message: "é → E" });
    expect(substitutionSummary(warnings)).toEqual(["é → E"]);
    expect(warningsFromCharset(null)).toEqual([]);
  });
  it("drops lowercase the board just shows in capitals (BB-B-7)", () => {
    const fold = (col: number, from: string) => ({
      row: 3,
      col,
      reason: "case" as const,
      token: { type: "char" as const, value: from },
      fallback: { type: "char" as const, value: from.toUpperCase() },
    });
    const issues = [...[..."aunch"].map((c, i) => fold(i + 4, c))];
    expect(warningsFromCharset(issues)).toEqual([]);
    expect(drawnDifferently(issues)).toEqual([]);
    const accent = { ...fold(1, "é"), reason: "char" as const, fallback: { type: "char" as const, value: "E" } };
    expect(drawnDifferently([...issues, accent])).toEqual([accent]);
  });
  it("names color substitutions by code", () => {
    const [warning] = warningsFromCharset([
      {
        row: 1,
        col: 0,
        reason: "colorSpan",
        token: { type: "color", code: "63" },
        fallback: { type: "char", value: " " },
      },
    ]);
    expect(warning.message).toBe("{63} →  ");
  });
});

describe("send history", () => {
  it("logs shown, held and paused and lifts failed and silenced out as warnings", () => {
    const model = sendLogModel(
      [
        {
          at: "2026-11-17T15:41:00Z",
          outcome: "sent",
          via: "auto",
          board_id: "den",
          board_name: "Den TV",
          count: 3,
          last_at: "2026-11-17T15:44:00Z",
        },
        { at: "2026-11-17T14:55:00Z", outcome: "held", via: "show_now", board_id: "den", board_name: "Den TV" },
        { at: "2026-11-17T14:50:00Z", outcome: "failed", via: "auto", board_id: "den", error: "unreachable" },
        { at: "2026-11-17T14:40:00Z", outcome: "silenced", via: "show_now" },
        { at: "2026-11-17T14:30:00Z", outcome: "paused", via: "show_now", board_id: "den" },
      ],
      (iso) => `T${iso.slice(11, 16)}`,
    );
    expect(model.items.map((item) => [item.outcome, item.at, item.count])).toEqual([
      ["shown", "T15:44", 3],
      ["held", "T14:55", 1],
      ["paused", "T14:30", 1],
    ]);
    expect(model.notShown.map((send) => send.outcome)).toEqual(["failed", "silenced"]);
    expect(model.items[0].boardName).toBe("Den TV");
    expect(model.items[2].boardName).toBeNull();
  });
});

describe("revision diff", () => {
  it("lists changed rows and outlines them as full-width fractions", () => {
    const changes = changedRows(["A", "B", "C"], ["A", "X", "C", "D"]);
    expect(changes).toEqual([
      { row: 1, before: "B", after: "X" },
      { row: 3, before: "", after: "D" },
    ]);
    expect(changeRegions(changes, 4)).toEqual([
      { id: "row-1", x: 0, y: 0.25, width: 1, height: 0.25 },
      { id: "row-3", x: 0, y: 0.75, width: 1, height: 0.25 },
    ]);
    expect(changeRegions(changes, 2)).toHaveLength(1);
    expect(changeRegions(changes, 0)).toEqual([]);
  });
});

const board = (id: string, name: string) => ({ id, name }) as BoardInstance;
const entry = (overrides: Partial<ScheduleEntry>): ScheduleEntry => ({
  id: "s1",
  page_id: "commute",
  board_id: "den",
  start_time: "07:30",
  end_time: "08:30",
  day_pattern: "weekdays",
  enabled: true,
  created_at: "",
  ...overrides,
});
const answer = (overrides: Partial<ActiveScheduleResponse>): ActiveScheduleResponse => ({
  page_id: "commute",
  source: "schedule",
  schedule_enabled: true,
  current_time: "07:41",
  current_day: "friday",
  default_page_id: null,
  temporary_override: { active: false } as ActiveScheduleResponse["temporary_override"],
  ...overrides,
});

describe("shows on (H8)", () => {
  it("holds windows including overnight and open-ended ones", () => {
    expect(windowHolds(entry({}), "07:41")).toBe(true);
    expect(windowHolds(entry({}), "08:30")).toBe(false);
    expect(windowHolds(entry({ start_time: "22:00", end_time: "02:00" }), "01:00")).toBe(true);
    expect(windowHolds(entry({ start_time: "22:00", end_time: "02:00" }), "12:00")).toBe(false);
    expect(windowHolds(entry({ end_time: null }), "23:00")).toBe(true);
    expect(windowHolds(entry({ resolved_start_time: "06:50", resolved_end_time: "07:20" }), "07:00")).toBe(true);
    expect(windowHolds(entry({}), null)).toBe(false);
  });

  it("collects direct and collection entries, collection places and the boards showing it now", () => {
    const rotation = { id: "col_den", name: "Den rotation", page_ids: ["brunch", "commute", "a", "b"] } as Collection;
    const model = showsOnModel({
      pageId: "commute",
      schedules: [
        entry({}),
        entry({ id: "s2", page_id: "col_den", board_id: "", start_time: "09:00", end_time: "10:00" }),
        entry({ id: "s3", page_id: "other" }),
      ],
      collections: [rotation, { id: "col_x", name: "X", page_ids: ["z"] } as Collection],
      boards: [board("den", "Den TV"), board("hall", "Hall board")],
      active: { den: answer({}), hall: answer({ page_id: "col_den", resolved_page_id: "commute", source: "manual" }) },
      defaultBoardId: "hall",
    });
    expect(model.entries.map((e) => [e.schedule.id, e.boardName, e.collection?.name ?? null, e.now])).toEqual([
      ["s1", "Den TV", null, true],
      ["s2", "Hall board", "Den rotation", false],
    ]);
    expect(model.collections).toEqual([{ collection: rotation, position: 2, size: 4 }]);
    expect(model.showingNow).toEqual([
      { boardId: "den", boardName: "Den TV", until: "08:30" },
      { boardId: "hall", boardName: "Hall board", until: null },
    ]);
    expect(model.scheduled).toBe(true);
  });

  it("is not showing while silenced and not scheduled when its entries are off", () => {
    const model = showsOnModel({
      pageId: "commute",
      schedules: [entry({ enabled: false, board_id: "gone" })],
      collections: [],
      boards: [],
      active: { den: answer({ silenced: true }), hall: undefined },
    });
    expect(model.showingNow).toEqual([]);
    expect(model.scheduled).toBe(false);
    expect(model.entries[0].boardName).toBe("gone");
  });
});

describe("template references", () => {
  it("lists variables and formulas with their lines and finds DEFAULT fallbacks", async () => {
    const { templateReferences } = await import("@/lib/ide/references");
    const refs = templateReferences([
      'NEXT {{fill_space}} {{= FORMATDATE(NOW(),"h:mm") }}',
      "{{muni.next|pad:3}} {{red}} {{weather.temperature}}",
      '{{= DEFAULT(muni.alert, "OK") }} {{=}}',
    ]);
    expect(refs.variables).toEqual([
      { line: 2, text: "muni.next" },
      { line: 2, text: "weather.temperature" },
      { line: 3, text: "muni.alert" },
    ]);
    expect(refs.formulas.map((f) => f.line)).toEqual([1, 3]);
    expect(refs.fallbacks).toEqual([{ line: 3, text: 'DEFAULT(muni.alert, "OK")' }]);
  });

  it("lists the data a formula reads, not its strings, numbers or loop locals (BB-B-2)", async () => {
    const { templateReferences } = await import("@/lib/ide/references");
    const refs = templateReferences([
      "{{= missing.value }}",
      '{{= IFERROR(nope.x, "FALLBACK") }} {{= "a.b" & 18.5 }}',
      '{{= FOREACH(transit.stops, item.eta & " " & item.name) }} {{= missing.value }}',
    ]);
    expect(refs.variables).toEqual([
      { line: 1, text: "missing.value" },
      { line: 2, text: "nope.x" },
      { line: 3, text: "transit.stops" },
      { line: 3, text: "missing.value" },
    ]);
  });
});
