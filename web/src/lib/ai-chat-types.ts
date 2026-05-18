// Types for the streaming AI chat feature.
//
// Mirrors src/ai/chat_ops.py — keep these in sync when changing
// either side of the wire.

import type { LineMetadata, DeviceType } from "./api";

export type Alignment = "left" | "center" | "right";

export interface ReplaceLineOpArg {
  type: "replace_line";
  index: number;
  text: string;
  alignment?: Alignment;
  wrap?: boolean;
}

export interface InsertLineOpArg {
  type: "insert_line";
  index: number;
  text: string;
  alignment?: Alignment;
  wrap?: boolean;
}

export interface DeleteLineOpArg {
  type: "delete_line";
  index: number;
}

export interface UpdateLineMetadataOpArg {
  type: "update_line_metadata";
  index: number;
  alignment?: Alignment;
  wrap?: boolean;
}

export type LineOp =
  | ReplaceLineOpArg
  | InsertLineOpArg
  | DeleteLineOpArg
  | UpdateLineMetadataOpArg;

export interface ReplacePageArgs {
  name: string;
  template: string[];
  line_metadata: LineMetadata[];
  duration_seconds: number;
}

export interface ApplyPatchArgs {
  changes: LineOp[];
  rename?: string | null;
}

export interface VariableSuggestion {
  ref: string;
  description?: string | null;
  example?: string | null;
}

export interface SuggestVariablesArgs {
  suggestions: VariableSuggestion[];
}

export interface NavigateToPageArgs {
  page_id: string;
  device_type?: string | null;
}

export interface InstallPluginArgs {
  plugin_id: string;
  source: "registry";
  auto_enable?: boolean;
  initial_config?: Record<string, unknown> | null;
}

export interface UpdatePluginConfigArgs {
  plugin_id: string;
  config: Record<string, unknown>;
}

export type SettingCategory =
  | "display"
  | "transitions"
  | "output"
  | "polling"
  | "location"
  | "silence_schedule"
  | "active_page";

export interface UpdateSettingArgs {
  category: SettingCategory;
  values: Record<string, unknown>;
}

export type DayPattern = "all" | "weekdays" | "weekends" | "custom";

export interface CreateCarouselArgs {
  name: string;
  page_ids: string[];
  interval_seconds: number;
}

export interface UpdateCarouselArgs {
  carousel_id: string;
  name?: string | null;
  page_ids?: string[] | null;
  interval_seconds?: number | null;
}

export interface CreateScheduleArgs {
  page_id: string;
  start_time: string;
  end_time?: string | null;
  day_pattern: DayPattern;
  custom_days?: string[] | null;
  enabled: boolean;
}

export interface UpdateScheduleArgs {
  schedule_id: string;
  page_id?: string | null;
  start_time?: string | null;
  end_time?: string | null;
  day_pattern?: DayPattern | null;
  custom_days?: string[] | null;
  enabled?: boolean | null;
}

export interface DeleteScheduleArgs {
  schedule_id: string;
}

export interface NavigateToScheduleArgs {
  prefill?: {
    page_id?: string;
    start_time?: string;
    end_time?: string | null;
    day_pattern?: DayPattern;
    custom_days?: string[];
  };
}

export interface UpdatePluginArgs {
  plugin_id: string;
}

export type ToolCall =
  | { id: string; op: "replace_page"; args: ReplacePageArgs }
  | { id: string; op: "apply_patch"; args: ApplyPatchArgs }
  | { id: string; op: "suggest_variables"; args: SuggestVariablesArgs }
  | { id: string; op: "navigate_to_page"; args: NavigateToPageArgs }
  | { id: string; op: "navigate_to_schedule"; args: NavigateToScheduleArgs }
  | { id: string; op: "install_plugin"; args: InstallPluginArgs }
  | { id: string; op: "update_plugin_config"; args: UpdatePluginConfigArgs }
  | { id: string; op: "update_setting"; args: UpdateSettingArgs }
  | { id: string; op: "create_carousel"; args: CreateCarouselArgs }
  | { id: string; op: "update_carousel"; args: UpdateCarouselArgs }
  | { id: string; op: "create_schedule"; args: CreateScheduleArgs }
  | { id: string; op: "update_schedule"; args: UpdateScheduleArgs }
  | { id: string; op: "delete_schedule"; args: DeleteScheduleArgs }
  | { id: string; op: "update_plugin"; args: UpdatePluginArgs }
  | { id: string; op: "trigger_system_update"; args: Record<string, never> };

/**
 * Tool call as displayed in the chat thread. Adds an optional
 * `appliedSnapshot` that the runtime computes locally — the page
 * state *as it would render after this call*. Used to draw a static
 * board preview inline in the assistant's tool-call card.
 *
 * For `replace_page`, the snapshot mirrors `args` exactly. For
 * `apply_patch`, it's the result of replaying the patch against the
 * pre-call page state. For `suggest_variables`, no snapshot.
 */
export type ToolCallDisplay = ToolCall & {
  appliedSnapshot?: CurrentPageSnapshot;
  // Device the call was made against — needed by the inline board
  // preview so it can size itself to flagship vs note.
  deviceType?: DeviceType;
};

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  // Tool calls associated with an assistant message. Rendered inline
  // alongside the prose.
  toolCalls?: ToolCallDisplay[];
  // Surface model warnings/errors next to the message so the user
  // sees them in context.
  warnings?: string[];
  // True while the assistant is still streaming this message.
  pending?: boolean;
}

export interface CurrentPageSnapshot {
  name: string;
  template: string[];
  line_metadata: LineMetadata[];
}

export interface PageRef {
  id: string;
  name: string;
}

export interface InstalledPluginRef {
  id: string;
  name: string;
  enabled: boolean;
}

export interface RegistryPluginRef {
  id: string;
  name: string;
  description: string;
  installed: boolean;
}

export interface ScheduleRef {
  id: string;
  page_id: string;
  start_time: string;
  end_time?: string | null;
  day_pattern: DayPattern;
  enabled: boolean;
}

export interface CarouselRef {
  id: string;
  name: string;
  page_ids: string[];
  interval_seconds: number;
}

/**
 * Latest editor state needed to issue a chat turn. Bundles both the
 * device the user is targeting (which dictates layout constraints in
 * the system prompt) and an optional snapshot of what's already in
 * the editor (for refinement turns).
 *
 * The global AI panel also passes availablePages, installedPlugins,
 * availableSchedules, and availableCarousels so the AI can propose
 * navigation, plugin installs, schedule/carousel management, etc.
 */
export interface ChatTurnContext {
  deviceType: DeviceType;
  currentPage?: CurrentPageSnapshot;
  availablePages?: PageRef[];
  installedPlugins?: InstalledPluginRef[];
  availableSchedules?: ScheduleRef[];
  availableCarousels?: CarouselRef[];
  registryPlugins?: RegistryPluginRef[];
}

export interface ChatRequestBody {
  messages: { role: "user" | "assistant"; content: string }[];
  device_type: DeviceType;
  current_page?: CurrentPageSnapshot;
  available_pages?: PageRef[];
  installed_plugins?: InstalledPluginRef[];
  available_schedules?: ScheduleRef[];
  available_carousels?: CarouselRef[];
  registry_plugins?: RegistryPluginRef[];
  provider_id?: string;
  model?: string;
}

// SSE event payloads from POST /pages/ai/chat. The event name is
// carried by fetchEventSource separately; the data is JSON-decoded.

export interface SSETextData {
  delta: string;
}

export interface SSEToolCallData {
  id: string;
  op: ToolCall["op"];
  args: Record<string, unknown>;
}

export interface SSEWarningData {
  message: string;
}

export interface SSEErrorData {
  message: string;
}

export interface SSEDoneData {
  model_used: string;
  provider_id: string;
  usage: {
    prompt_tokens: number | null;
    completion_tokens: number | null;
    total_tokens: number | null;
  };
}
