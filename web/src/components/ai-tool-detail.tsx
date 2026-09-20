"use client";

import { Box, Collapsible, CollapsibleContent, CollapsibleTrigger, Flex, Stack, Text } from "@fiestaboard/ui";
import { ChevronRight } from "lucide-react";

import type { TranslateFn } from "@/components/ai-tool-labels";
import { useTargetCaches } from "@/hooks/use-target-caches";
import { useTranslations } from "@/i18n/translations";
import type { CreatePageArgs, CreateScheduleArgs, ToolCallDisplay } from "@/lib/ai-chat-types";
import { type TargetCaches } from "@/lib/ai-target-names";

// What a tool call did, for people rather than for a parser.
//
// The card used to print the raw argument JSON in a sideways-scrolling box
// and collapse the result to "{3}", which says nothing about what happened
// to the board. Arguments are now the fields that matter for the tool, in
// the user's vocabulary, and the result is the server's own sentence — the
// `message` every ops envelope carries (src/ops/results.py). The raw
// payload is still one disclosure away, and wraps instead of scrolling.

/** One row of the field list: a label the user knows, and a value. */
export interface ToolField {
  label: string;
  value: string;
  /** Machine data (a time, an id, a template line) is set in the mono face. */
  mono?: boolean;
}

function text(value: unknown): string | undefined {
  if (typeof value === "string") return value || undefined;
  if (typeof value === "number") return String(value);
  return undefined;
}

function nameOrId(rows: { id: string; name: string }[] | undefined, id: unknown): string | undefined {
  if (typeof id !== "string" || !id) return undefined;
  return rows?.find((row) => row.id === id)?.name || id;
}

function scheduleFields(
  parts: { pageId: unknown; start?: string; end?: string | null; pattern?: string; boardId?: unknown },
  caches: TargetCaches,
  t: TranslateFn,
): ToolField[] {
  const fields: ToolField[] = [];
  const page = nameOrId(caches.pages?.pages, parts.pageId);
  if (page) fields.push({ label: t("argLabel.page"), value: page });
  if (parts.start) {
    fields.push({
      label: t("argLabel.time"),
      value: parts.end ? `${parts.start}–${parts.end}` : parts.start,
      mono: true,
    });
  }
  if (parts.pattern) {
    const pattern = t(`dayPattern.${parts.pattern}`);
    if (pattern !== `dayPattern.${parts.pattern}`) fields.push({ label: t("argLabel.days"), value: pattern });
  }
  const board = text(parts.boardId);
  if (board) fields.push({ label: t("argLabel.board"), value: board });
  return fields;
}

/**
 * The fields worth showing for this call, in reading order.
 *
 * A tool this function does not know falls back to its own arguments, one
 * row per primitive value, keyed by the argument name: still readable, and
 * never a lie about what was sent.
 */
export function fieldsForCall(
  call: Pick<ToolCallDisplay, "name" | "args">,
  caches: TargetCaches,
  t: TranslateFn,
): ToolField[] {
  const args = call.args as Record<string, unknown>;

  switch (call.name) {
    case "create_schedule":
    case "update_schedule": {
      const a = args as unknown as Partial<CreateScheduleArgs> & { board_id?: unknown };
      const entry =
        call.name === "update_schedule"
          ? caches.schedules?.schedules?.find((s) => s.id === args.schedule_id)
          : undefined;
      return scheduleFields(
        {
          pageId: a.page_id ?? entry?.page_id,
          start: a.start_time ?? entry?.start_time,
          end: a.end_time ?? entry?.end_time,
          pattern: a.day_pattern ?? entry?.day_pattern,
          boardId: a.board_id,
        },
        caches,
        t,
      );
    }
    case "delete_schedule": {
      const entry = caches.schedules?.schedules?.find((s) => s.id === args.schedule_id);
      // The delete removed its own target from the cache, so there are no
      // fields left to describe. Better nothing than a row labelled "Name"
      // holding a uuid — the header still carries the remembered name, and
      // the raw payload is one disclosure away.
      if (!entry) return [];
      return scheduleFields(
        { pageId: entry.page_id, start: entry.start_time, end: entry.end_time, pattern: entry.day_pattern },
        caches,
        t,
      );
    }
    case "create_page":
    case "update_page": {
      const a = args as unknown as Partial<CreatePageArgs>;
      const fields: ToolField[] = [];
      const name = text(a.name) ?? nameOrId(caches.pages?.pages, args.page_id);
      if (name) fields.push({ label: t("argLabel.name"), value: name });
      if (Array.isArray(a.template_lines)) {
        fields.push({ label: t("argLabel.lines"), value: t("argValue.lineCount", { count: a.template_lines.length }) });
      }
      if (typeof a.duration_seconds === "number") {
        fields.push({
          label: t("argLabel.duration"),
          value: t("argValue.durationSeconds", { count: a.duration_seconds }),
        });
      }
      return fields;
    }
    case "delete_page":
    case "set_active_page":
    case "get_page":
    case "preview_saved_page": {
      const page = nameOrId(caches.pages?.pages, args.page_id);
      return page ? [{ label: t("argLabel.page"), value: page }] : [];
    }
    case "create_collection":
    case "update_collection":
    case "delete_collection": {
      const name = text(args.name) ?? nameOrId(caches.collections?.collections, args.collection_id);
      return name ? [{ label: t("argLabel.collection"), value: name }] : [];
    }
    case "install_plugin":
    case "enable_plugin":
    case "disable_plugin":
    case "uninstall_plugin":
    case "configure_plugin":
    case "update_plugin":
    case "get_plugin_data": {
      const plugin = nameOrId(caches.plugins?.plugins, args.plugin_id);
      return plugin ? [{ label: t("argLabel.plugin"), value: plugin }] : [];
    }
    case "set_schedule_mode": {
      const fields: ToolField[] = [
        { label: t("argLabel.scheduleMode"), value: args.enabled ? t("argValue.on") : t("argValue.off") },
      ];
      const board = text(args.board_id);
      if (board) fields.push({ label: t("argLabel.board"), value: board });
      return fields;
    }
    case "send_message": {
      const message = text(args.text);
      return message ? [{ label: t("argLabel.message"), value: message, mono: true }] : [];
    }
    case "update_setting": {
      const category = text(args.category);
      return category ? [{ label: t("argLabel.setting"), value: category }] : [];
    }
    default:
      return Object.entries(args)
        .filter(([, value]) => value !== null && value !== undefined && typeof value !== "object")
        .map(([key, value]) => ({ label: key, value: String(value), mono: true }));
  }
}

function FieldList({ fields }: { fields: ToolField[] }) {
  return (
    <Stack gap="1">
      {fields.map((field) => (
        <Flex key={field.label} align="baseline" gap="2" className="min-w-0">
          <Text as="span" size="xs" tone="muted" className="w-20 shrink-0 truncate">
            {field.label}
          </Text>
          <Text as="span" size="xs" className={`min-w-0 flex-1 break-words ${field.mono ? "font-mono" : ""}`}>
            {field.value}
          </Text>
        </Flex>
      ))}
    </Stack>
  );
}

/**
 * The raw payload, behind a disclosure. Wraps (`break-all`) rather than
 * scrolling sideways: a horizontal scrollbar inside a 384px drawer inside a
 * collapsible card is three nested scroll contexts to hit a 40-character
 * uuid, and every one of them is a trap on a touch screen.
 */
function JsonDisclosure({ data, label }: { data: unknown; label: string }) {
  return (
    <Collapsible>
      <CollapsibleTrigger className="group/json inline-flex items-center gap-1 rounded-md text-xs text-muted-foreground hover:text-foreground focus-ring">
        <ChevronRight
          className="size-3 transition-transform duration-control group-data-[open]/json:rotate-90 [[data-open]_&]:rotate-90"
          aria-hidden="true"
        />
        {label}
      </CollapsibleTrigger>
      <CollapsibleContent>
        <Box
          className="mt-1 max-h-48 overflow-y-auto whitespace-pre-wrap break-all rounded-md bg-muted p-2 font-mono text-xs leading-relaxed"
          data-testid="ai-tool-json"
        >
          {JSON.stringify(data, null, 2)}
        </Box>
      </CollapsibleContent>
    </Collapsible>
  );
}

/** The call's arguments: the fields that matter, then the payload on request. */
export function AiToolArguments({ call }: { call: ToolCallDisplay }) {
  const t = useTranslations("aiChatPanel");
  const caches = useTargetCaches();
  const fields = fieldsForCall(call, caches, t);
  const hasArgs = Object.keys(call.args ?? {}).length > 0;
  if (!hasArgs) return null;

  return (
    <Stack gap="1.5" data-testid="ai-tool-arguments">
      <Text as="span" size="xs" weight="medium" tone="muted">
        {t("toolInput")}
      </Text>
      {fields.length > 0 ? <FieldList fields={fields} /> : null}
      <JsonDisclosure data={call.args} label={t("showJson")} />
    </Stack>
  );
}

/**
 * What came back. The server's own sentence when the envelope carries one
 * (`{"status": "success", "message": "Schedule deleted successfully."}`),
 * a field count when it does not, and the payload behind the disclosure.
 */
export function AiToolResultSummary({ result }: { result: unknown }) {
  const t = useTranslations("aiChatPanel");
  const envelope = typeof result === "object" && result !== null ? (result as Record<string, unknown>) : undefined;
  const sentence = envelope ? (text(envelope.message) ?? text(envelope.detail)) : text(result);
  const summary = sentence ?? (envelope ? t("resultFields", { count: Object.keys(envelope).length }) : String(result));

  return (
    <Stack gap="1.5" data-testid="ai-tool-result">
      <Text size="xs" className="break-words">
        {summary}
      </Text>
      <JsonDisclosure data={result} label={t("showJson")} />
    </Stack>
  );
}
