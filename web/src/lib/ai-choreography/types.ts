// The step language the walkthrough speaks.
//
// A choreography script turns one tool call into a short sequence of
// steps — go to the screen, point at the control, show the value arriving,
// then show it landed — and the engine (engine.ts) plays them in order at
// a human pace, fast-forwarding when the server has already answered and
// skipping motion entirely for users who asked for less of it.

import type { SpotlightTone } from "@fiestaboard/ui";

import type { ToolCall, ToolResult } from "@/lib/ai-chat-types";

/** A field the page editor can stage without a real form submit. */
export type PageEditorField = { field: "name" } | { field: "line"; index: number } | { field: "device_type" };

/** A field the schedule form can stage. */
export type ScheduleFormField =
  | "page_id"
  | "start_time"
  | "end_time"
  | "day_pattern"
  | "custom_days"
  | "enabled"
  | "recurrence_type"
  | "start_type"
  | "start_sun_offset"
  | "end_type"
  | "end_sun_offset";

export type TypeTarget =
  ({ bridge: "page-editor" } & PageEditorField) | { bridge: "schedule-form"; field: ScheduleFormField };

export type SpotlightControls = "none" | "stop" | "approval";

/** `auto` picks replica for text inputs and badge for everything else. */
export type GhostVariant = "replica" | "badge" | "auto";

export type Step =
  /** Change route; the engine waits for the navigation to settle. */
  | { kind: "navigate"; href: string }
  /** Wait for an anchor to exist on screen (a route or sheet mounting). */
  | { kind: "waitFor"; anchor: string; timeoutMs?: number }
  /** Wait for a bridge surface (the page editor, the schedule form) to be ready. */
  | { kind: "waitBridge"; bridge: TypeTarget["bridge"]; timeoutMs?: number }
  /** Point at an anchor with a caption. A missing anchor shows the caption alone. */
  | { kind: "spotlight"; anchor: string; caption: string; tone?: SpotlightTone; controls?: SpotlightControls }
  /** Change only the caption/tone of the current spotlight. */
  | { kind: "caption"; caption: string; tone?: SpotlightTone }
  /** Show a value arriving over a control without touching React state. */
  | { kind: "ghost"; anchor: string; value: string; variant?: GhostVariant }
  /** Type a value into a mounted surface for real, character by character. */
  | { kind: "type"; target: TypeTarget; value: string }
  /** Set a value on a mounted surface at once. */
  | { kind: "set"; target: TypeTarget; value: unknown }
  /** Let the eye catch up. */
  | { kind: "pause"; ms: number }
  /** Flash the landed ring on an anchor. */
  | { kind: "pulse"; anchor: string }
  /** Remove every ghost value. */
  | { kind: "clearGhosts" }
  /** Hide the spotlight. */
  | { kind: "hide" }
  /** Anything else, in code. */
  | { kind: "run"; run: (ctx: ChoreographyContext) => void | Promise<void> };

/** What the client can read of a tool block the model is still writing. */
export interface ToolDraft {
  name: string | null;
  /** Complete top-level string arguments read so far. */
  strings: Record<string, string>;
  /** Complete items of top-level string-array arguments read so far. */
  lists: Record<string, string[]>;
  /** The string being written right now, if the reader is inside one. */
  partial?: { key: string; index?: number; value: string };
}

/** The surfaces a script may drive. Each may be absent (not mounted). */
export interface PageEditorStaging {
  /** True while a page editor is mounted and registered. */
  isMounted(): boolean;
  /** The id of the page the editor holds, if it is a saved page. */
  pageId(): string | undefined;
  /** True while the editor holds edits the user has not saved. */
  hasUnsavedChanges(): boolean;
  /** Start a staged reveal: one undo snapshot, no draft autosave, save locked. */
  begin(): void;
  setName(value: string): void;
  setLine(index: number, value: string): void;
  setDeviceType(value: string): void;
  /** Throw the staged values away (Stop, or a failed call). */
  discard(): void;
  /** Reload from the server after a successful write; ends staging. */
  reload(): Promise<void>;
  /** Wait for the editor to mount (after a navigation). */
  waitFor(timeoutMs?: number): Promise<boolean>;
}

export interface ScheduleStaging {
  isMounted(): boolean;
  /** Open an empty entry form (a fresh instance, nothing prefilled). */
  openEmpty(): void;
  /** Open the form on an existing entry. */
  openEntry(scheduleId: string): void;
  setField(field: ScheduleFormField, value: unknown): void;
  /** Close the form without submitting. */
  close(): void;
  waitFor(timeoutMs?: number): Promise<boolean>;
  waitForForm(timeoutMs?: number): Promise<boolean>;
}

export interface SpotlightApi {
  show(opts: { anchor: string; caption: string; tone?: SpotlightTone; controls?: SpotlightControls }): void;
  caption(caption: string, tone?: SpotlightTone): void;
  pulse(anchor: string): void;
  hide(): void;
  ghost(anchor: string, value: string, progress: number, variant: GhostVariant): void;
  clearGhosts(): void;
}

export type TranslateFn = (key: string, params?: Record<string, unknown>) => string;

export interface ChoreographyContext {
  navigate(href: string): void;
  pathname(): string;
  spotlight: SpotlightApi;
  pageEditor: PageEditorStaging;
  schedule: ScheduleStaging;
  t: TranslateFn;
  /** The human label of a call, as the chat panel shows it. */
  label(call: ToolCall): string;
  /** The user asked for less motion: reveals are instant, pauses are short. */
  reducedMotion: boolean;
}

/**
 * What one tool's walkthrough looks like. Every method is pure: it returns
 * steps, the engine plays them. `narrate` runs when the call is announced
 * (before or while the server runs it), `settle` after an ok result,
 * `fail` after an error/blocked result, `stop` when the user ends the
 * turn mid-walkthrough, `draft` while the model is still writing the call.
 */
export interface ChoreographyScript {
  /**
   * Called on every draft frame with the same `progress` object for the
   * whole call, so a script can return only the steps for what is new.
   */
  draft?(draft: ToolDraft, ctx: ChoreographyContext, progress: Record<string, unknown>): Step[];
  /** `progress` is the draft's object when a draft preceded the call. */
  narrate(call: ToolCall, ctx: ChoreographyContext, progress?: Record<string, unknown>): Step[];
  settle(call: ToolCall, result: ToolResult, ctx: ChoreographyContext): Step[];
  fail?(call: ToolCall, result: ToolResult, ctx: ChoreographyContext): Step[];
  stop?(call: ToolCall, ctx: ChoreographyContext): Step[];
  /** Where Approve/Deny are shown for a destructive call. */
  approvalAnchor?(call: ToolCall, ctx: ChoreographyContext): string | undefined;
}
