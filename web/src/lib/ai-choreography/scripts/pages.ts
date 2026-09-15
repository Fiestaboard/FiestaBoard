// Pages: the editor is driven for real.
//
// create_page walks to the Pages list, opens a fresh editor and types the
// name and every line while the server creates the page — starting as
// soon as the model's block names the tool, so the editor is already open
// and filling when the call completes. On success the staged draft is
// discarded and the saved page is opened. update_page types into the open
// editor when it holds that page and is clean; otherwise it opens the page
// first. Both leave nothing behind on Stop.

import type { CreatePageArgs, UpdatePageArgs } from "@/lib/ai-chat-types";

import { homeFor } from "../home";
import type { ChoreographyContext, ChoreographyScript, PageEditorField, Step, ToolDraft } from "../types";
import { failed, landed } from "./fallback";

interface PageProgress {
  started?: boolean;
  name?: string;
  lines?: string[];
  deviceType?: string;
}

const NAME_FIELD: PageEditorField = { field: "name" };

function typeName(value: string): Step {
  return { kind: "type", target: { bridge: "page-editor", ...NAME_FIELD }, value };
}

function typeLine(index: number, value: string): Step {
  return { kind: "type", target: { bridge: "page-editor", field: "line", index }, value };
}

/** Open a fresh editor for a new page (from wherever we are). */
function openNewEditor(ctx: ChoreographyContext, deviceType: string): Step[] {
  const onNew = ctx.pathname() === "/pages/new" && ctx.pageEditor.isMounted() && !ctx.pageEditor.hasUnsavedChanges();
  if (onNew) return [{ kind: "run", run: (c) => c.pageEditor.begin() }];
  return [
    { kind: "navigate", href: "/pages" },
    { kind: "waitFor", anchor: "pages.new", timeoutMs: 1500 },
    { kind: "spotlight", anchor: "pages.new", caption: ctx.t("openingNewPage"), controls: "stop" },
    { kind: "pause", ms: 450 },
    { kind: "navigate", href: `/pages/new?device=${encodeURIComponent(deviceType)}&fresh=1` },
    { kind: "waitBridge", bridge: "page-editor", timeoutMs: 4000 },
    { kind: "run", run: (c) => c.pageEditor.begin() },
  ];
}

/** Type whatever is new since the last reveal. */
function revealProgress(
  progress: PageProgress,
  name: string | undefined,
  lines: string[] | undefined,
  partial: string | undefined,
  ctx: ChoreographyContext,
): Step[] {
  const steps: Step[] = [];
  if (name !== undefined && name !== progress.name) {
    steps.push({ kind: "spotlight", anchor: "page-editor.name", caption: ctx.t("typingName"), controls: "stop" });
    steps.push(typeName(name));
    progress.name = name;
  }
  const typed = progress.lines ?? [];
  if (lines) {
    for (let i = 0; i < lines.length; i++) {
      if (typed[i] === lines[i]) continue;
      if (i === 0 || typed.length === 0) {
        steps.push({
          kind: "spotlight",
          anchor: "page-editor.template",
          caption: ctx.t("typingLines"),
          controls: "stop",
        });
      }
      steps.push(typeLine(i, lines[i]));
      typed[i] = lines[i];
    }
    progress.lines = typed;
  }
  // The line the model is writing right now follows its pen, instantly.
  if (partial !== undefined && lines) {
    const index = lines.length;
    if (typed[index] !== partial) {
      steps.push({ kind: "set", target: { bridge: "page-editor", field: "line", index }, value: partial });
    }
  }
  return steps;
}

const createPage: ChoreographyScript = {
  draft(draft: ToolDraft, ctx, progress: PageProgress) {
    const steps: Step[] = [];
    if (!progress.started) {
      progress.started = true;
      steps.push(...openNewEditor(ctx, draft.strings.device_type ?? "flagship"));
    }
    const partial = draft.partial?.key === "template_lines" ? draft.partial.value : undefined;
    steps.push(...revealProgress(progress, draft.strings.name, draft.lists.template_lines, partial, ctx));
    return steps;
  },
  narrate(call, ctx, progress: PageProgress = {}) {
    const a = call.args as unknown as CreatePageArgs;
    const steps: Step[] = [];
    if (!progress.started) {
      progress.started = true;
      steps.push(...openNewEditor(ctx, a.device_type ?? "flagship"));
    }
    steps.push(...revealProgress(progress, a.name, a.template_lines, undefined, ctx));
    steps.push({ kind: "caption", caption: ctx.t("creatingPage", { name: a.name ?? "" }) });
    return steps;
  },
  settle(call, result, ctx) {
    const pageId = (result.result as { page_id?: unknown } | null)?.page_id;
    const open: Step[] =
      typeof pageId === "string"
        ? [
            { kind: "run", run: (c) => c.pageEditor.discard() },
            { kind: "navigate", href: `/pages/edit/${pageId}` },
            { kind: "waitBridge", bridge: "page-editor", timeoutMs: 4000 },
          ]
        : [{ kind: "run", run: (c) => c.pageEditor.discard() }];
    return [...open, ...landed("page-editor.name", ctx.t("pageCreated"))];
  },
  fail(_call, result, ctx) {
    return [{ kind: "run", run: (c) => c.pageEditor.discard() }, ...failed(result.error ?? ctx.t("pageFailed"))];
  },
  stop() {
    return [{ kind: "run", run: (c) => c.pageEditor.discard() }, { kind: "clearGhosts" }, { kind: "hide" }];
  },
};

const updatePage: ChoreographyScript = {
  narrate(call, ctx) {
    const a = call.args as unknown as UpdatePageArgs;
    const editorHasIt = ctx.pageEditor.isMounted() && ctx.pageEditor.pageId() === a.page_id;
    if (editorHasIt && ctx.pageEditor.hasUnsavedChanges()) {
      // Never type over what the user is editing; point and say so.
      return [
        { kind: "spotlight", anchor: "page-editor.template", caption: ctx.t("updatingBehindEdits"), controls: "stop" },
      ];
    }
    const steps: Step[] = editorHasIt
      ? []
      : [
          { kind: "navigate", href: `/pages/edit/${a.page_id}` },
          { kind: "waitBridge", bridge: "page-editor", timeoutMs: 4000 },
        ];
    steps.push({ kind: "run", run: (c) => c.pageEditor.begin() });
    if (a.device_type) {
      steps.push({
        kind: "spotlight",
        anchor: "page-editor.device",
        caption: ctx.t("changingDevice"),
        controls: "stop",
      });
      steps.push({ kind: "set", target: { bridge: "page-editor", field: "device_type" }, value: a.device_type });
      steps.push({ kind: "pause", ms: 400 });
    }
    if (a.name) {
      steps.push({ kind: "spotlight", anchor: "page-editor.name", caption: ctx.t("typingName"), controls: "stop" });
      steps.push(typeName(a.name));
    }
    if (a.template_lines) {
      steps.push({
        kind: "spotlight",
        anchor: "page-editor.template",
        caption: ctx.t("typingLines"),
        controls: "stop",
      });
      a.template_lines.forEach((line, i) => steps.push(typeLine(i, line)));
    }
    if (steps.length === 1) {
      steps.push({
        kind: "spotlight",
        anchor: "page-editor.name",
        caption: ctx.t("working", { tool: ctx.label(call) }),
        controls: "stop",
      });
    }
    return steps;
  },
  settle(_call, _result, ctx) {
    return [
      { kind: "run", run: (c) => c.pageEditor.reload() },
      ...landed("page-editor.template", ctx.t("pageUpdated")),
    ];
  },
  fail(_call, result, ctx) {
    return [{ kind: "run", run: (c) => c.pageEditor.discard() }, ...failed(result.error ?? ctx.t("pageFailed"))];
  },
  stop() {
    return [{ kind: "run", run: (c) => c.pageEditor.discard() }, { kind: "clearGhosts" }, { kind: "hide" }];
  },
};

const deletePage: ChoreographyScript = {
  narrate(call, ctx) {
    const { href, anchor } = homeFor(call);
    return [
      { kind: "navigate", href },
      { kind: "waitFor", anchor, timeoutMs: 1500 },
      { kind: "spotlight", anchor, caption: ctx.t("aboutToDeletePage"), controls: "stop" },
    ];
  },
  settle(call, _result, ctx) {
    return landed(homeFor(call).anchor, ctx.t("pageDeleted"));
  },
  approvalAnchor(call) {
    return homeFor(call).anchor;
  },
};

/** Imports land in the editor on the new page. */
const importPage: ChoreographyScript = {
  narrate(call, ctx) {
    return [
      { kind: "navigate", href: "/pages" },
      { kind: "waitFor", anchor: "pages.root", timeoutMs: 1500 },
      {
        kind: "spotlight",
        anchor: "pages.root",
        caption: ctx.t("working", { tool: ctx.label(call) }),
        controls: "stop",
      },
    ];
  },
  settle(_call, result, ctx) {
    const pageId = (result.result as { page_id?: unknown } | null)?.page_id;
    const open: Step[] =
      typeof pageId === "string"
        ? [
            { kind: "navigate", href: `/pages/edit/${pageId}` },
            { kind: "waitBridge", bridge: "page-editor", timeoutMs: 4000 },
          ]
        : [];
    return [...open, ...landed("page-editor.name", ctx.t("pageCreated"))];
  },
};

export const PAGE_SCRIPTS: Record<string, ChoreographyScript> = {
  create_page: createPage,
  update_page: updatePage,
  delete_page: deletePage,
  import_page: importPage,
  import_staff_pick: importPage,
};
