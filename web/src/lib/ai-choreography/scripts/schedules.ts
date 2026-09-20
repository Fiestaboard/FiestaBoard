// Schedules: the entry form is opened and filled field by field.

import type { CreateScheduleArgs, UpdateScheduleArgs } from "@/lib/ai-chat-types";

import { homeFor } from "../home";
import type { ChoreographyContext, ChoreographyScript, ScheduleFormField, Step } from "../types";
import { failed, landed } from "./fallback";

/** The order the form shows its fields, so the reveal reads top to bottom. */
const FIELD_ORDER: ScheduleFormField[] = [
  "page_id",
  "start_type",
  "start_time",
  "start_sun_offset",
  "end_type",
  "end_time",
  "end_sun_offset",
  "recurrence_type",
  "day_pattern",
  "custom_days",
  "enabled",
];

/** The control each field lives in (see anchors.ts for the legacy ids). */
const FIELD_ANCHOR: Record<ScheduleFormField, string> = {
  page_id: "schedule.form.page",
  start_type: "schedule.form.start-type",
  start_time: "schedule.form.start-time",
  start_sun_offset: "schedule.form.start-sun-offset",
  end_type: "schedule.form.end-type",
  end_time: "schedule.form.end-time",
  end_sun_offset: "schedule.form.end-sun-offset",
  recurrence_type: "schedule.form.recurrence",
  day_pattern: "schedule.form.day-pattern",
  custom_days: "schedule.form.day-pattern",
  enabled: "schedule.form.enabled",
};

function fillSteps(args: Record<string, unknown>, ctx: ChoreographyContext): Step[] {
  const steps: Step[] = [];
  for (const field of FIELD_ORDER) {
    if (!(field in args) || args[field] === undefined) continue;
    steps.push({ kind: "spotlight", anchor: FIELD_ANCHOR[field], caption: ctx.t("fillingSchedule"), controls: "stop" });
    steps.push({ kind: "set", target: { bridge: "schedule-form", field }, value: args[field] });
    steps.push({ kind: "pause", ms: 320 });
  }
  return steps;
}

function openForm(ctx: ChoreographyContext, scheduleId?: string): Step[] {
  const steps: Step[] = [];
  if (ctx.pathname() !== "/schedule") steps.push({ kind: "navigate", href: "/schedule" });
  if (scheduleId) {
    steps.push({ kind: "waitFor", anchor: `schedule.row.${scheduleId}`, timeoutMs: 2500 });
    steps.push({
      kind: "spotlight",
      anchor: `schedule.row.${scheduleId}`,
      caption: ctx.t("openingScheduleForm"),
      controls: "stop",
    });
    steps.push({ kind: "pause", ms: 350 });
    steps.push({ kind: "run", run: (c) => c.schedule.openEntry(scheduleId) });
  } else {
    steps.push({ kind: "waitFor", anchor: "schedule.add", timeoutMs: 2500 });
    steps.push({ kind: "spotlight", anchor: "schedule.add", caption: ctx.t("openingScheduleForm"), controls: "stop" });
    steps.push({ kind: "pause", ms: 350 });
    steps.push({ kind: "run", run: (c) => c.schedule.openEmpty() });
  }
  steps.push({ kind: "waitBridge", bridge: "schedule-form", timeoutMs: 3000 });
  return steps;
}

const createSchedule: ChoreographyScript = {
  narrate(call, ctx) {
    const a = call.args as unknown as CreateScheduleArgs;
    return [
      ...openForm(ctx),
      ...fillSteps(a as unknown as Record<string, unknown>, ctx),
      { kind: "caption", caption: ctx.t("savingSchedule") },
    ];
  },
  settle(_call, result, ctx) {
    const id = (result.result as { schedule_id?: unknown } | null)?.schedule_id;
    const row = typeof id === "string" ? `schedule.row.${id}` : "schedule.root";
    return [
      { kind: "run", run: (c) => c.schedule.close() },
      { kind: "waitFor", anchor: row, timeoutMs: 3000 },
      ...landed(row, ctx.t("scheduleCreated")),
    ];
  },
  fail(_call, result, ctx) {
    return [{ kind: "run", run: (c) => c.schedule.close() }, ...failed(result.error ?? ctx.t("scheduleFailed"))];
  },
  stop() {
    return [{ kind: "run", run: (c) => c.schedule.close() }, { kind: "clearGhosts" }, { kind: "hide" }];
  },
};

const updateSchedule: ChoreographyScript = {
  narrate(call, ctx) {
    const a = call.args as unknown as UpdateScheduleArgs;
    const { schedule_id: id, ...rest } = a;
    return [
      ...openForm(ctx, id),
      ...fillSteps(rest as Record<string, unknown>, ctx),
      { kind: "caption", caption: ctx.t("savingSchedule") },
    ];
  },
  settle(call, _result, ctx) {
    const row = homeFor(call).anchor;
    return [{ kind: "run", run: (c) => c.schedule.close() }, ...landed(row, ctx.t("scheduleUpdated"))];
  },
  fail(_call, result, ctx) {
    return [{ kind: "run", run: (c) => c.schedule.close() }, ...failed(result.error ?? ctx.t("scheduleFailed"))];
  },
  stop() {
    return [{ kind: "run", run: (c) => c.schedule.close() }, { kind: "clearGhosts" }, { kind: "hide" }];
  },
};

const deleteSchedule: ChoreographyScript = {
  narrate(call, ctx) {
    const { href, anchor } = homeFor(call);
    return [
      { kind: "navigate", href },
      { kind: "waitFor", anchor, timeoutMs: 2500 },
      { kind: "spotlight", anchor, caption: ctx.t("aboutToDeleteSchedule"), controls: "stop" },
    ];
  },
  settle(call, _result, ctx) {
    return landed(homeFor(call).anchor, ctx.t("scheduleDeleted"));
  },
  approvalAnchor(call) {
    return homeFor(call).anchor;
  },
};

export const SCHEDULE_SCRIPTS: Record<string, ChoreographyScript> = {
  create_schedule: createSchedule,
  update_schedule: updateSchedule,
  delete_schedule: deleteSchedule,
};
