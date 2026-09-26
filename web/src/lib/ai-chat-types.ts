// Types for the streaming AI chat feature.
//
// The chat is a server-side agent loop over the in-process MCP server
// (src/ai/agent.py). The browser no longer executes tools: it renders what
// the stream says is happening (`tool_call` before a tool runs,
// `tool_result` after), answers the two questions only a person can
// (approve a destructive tool, reply to `ask_user`), and replays the
// structured transcript on every request.
//
// Mirrors the ChatStream*Data models registered in CHAT_STREAM_EVENTS
// (src/ai/page_routes.py) and the request models beside them.
// tests/test_ai_stream_contract.py holds the two sides together.

import type { DeviceType, LineMetadata } from "./api";

// ---------------------------------------------------------------------------
// Editor-local ops. These never cross the wire any more: the page editor's
// own undo/apply plumbing still speaks them (src/lib/line-ops.ts,
// page-builder.tsx), which is why they live on.
// ---------------------------------------------------------------------------

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

export type LineOp = ReplaceLineOpArg | InsertLineOpArg | DeleteLineOpArg | UpdateLineMetadataOpArg;

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

/** An edit the page editor applies to its own draft. */
export type EditorToolCall =
  { id: string; op: "replace_page"; args: ReplacePageArgs } | { id: string; op: "apply_patch"; args: ApplyPatchArgs };

// ---------------------------------------------------------------------------
// Tools — the MCP tool names, plus the two chat-only extensions.
// ---------------------------------------------------------------------------

/**
 * The tools the choreography and the labels know by name. The server may
 * emit any tool the MCP server registers; an unknown one still renders,
 * with a generic label. tests/test_ai_stream_contract.py asserts every name
 * here is a real MCP tool (or a chat extension).
 */
export const KNOWN_TOOL_NAMES = [
  "create_page",
  "update_page",
  "delete_page",
  "create_schedule",
  "update_schedule",
  "delete_schedule",
  "create_collection",
  "update_collection",
  "delete_collection",
  "install_plugin",
  "enable_plugin",
  "disable_plugin",
  "uninstall_plugin",
  "configure_plugin",
  "update_plugin",
  "set_active_page",
  "set_schedule_mode",
  "send_message",
  "update_setting",
  "trigger_system_update",
  "ask_user",
  "list_pages",
  "get_page",
  "list_schedules",
  "list_collections",
  "list_installed_plugins",
  "list_registry_plugins",
  "get_template_variables",
  "get_plugin_data",
  "render_page_preview",
  "preview_saved_page",
  "validate_template",
  "get_system_status",
  "get_settings_summary",
  "get_active_page",
  "get_board_content",
] as const;

export type KnownToolName = (typeof KNOWN_TOOL_NAMES)[number];
// `string & {}` keeps autocomplete for the known names while accepting any string.
export type ToolName = KnownToolName | (string & {});

export type ToolSource = "mcp" | "chat";

/** One `tool_call` frame: a validated call, emitted BEFORE it runs. */
export interface ToolCall {
  id: string;
  name: ToolName;
  args: Record<string, unknown>;
  title: string;
  read_only: boolean;
  destructive: boolean;
  requires_approval: boolean;
  source: ToolSource;
  /**
   * The system tier (restart / shutdown / update): pauses for approval in
   * every mode, so the card never offers "don't ask again" for it. Decided
   * by the server (`SYSTEM_GATED`); the client keeps no list of its own.
   */
  system_gated?: boolean;
  /** True when a destructive call ran without a pause (Auto mode, or "don't ask again"). */
  auto_approved?: boolean;
}

export type ToolResultStatus = "ok" | "blocked" | "error" | "denied";

/** One `tool_result` frame: what the call did. */
export interface ToolResult {
  id: string;
  name: ToolName;
  status: ToolResultStatus;
  summary: string;
  result: unknown;
  error: string | null;
}

/** One `elicitation` frame: the assistant asked the user something. */
export interface Elicitation {
  id: string;
  name: ToolName;
  message: string;
  requested_schema: {
    type: "object";
    properties: Record<string, ElicitationProperty>;
    required?: string[];
  };
  allow_free_text: boolean;
}

export interface ElicitationProperty {
  type: "string" | "number" | "integer" | "boolean";
  title?: string;
  description?: string;
  enum?: string[];
}

export type ElicitationAnswer =
  | { action: "accept"; content: Record<string, string | number | boolean> }
  | { action: "decline" }
  | { action: "cancel" };

export type ApprovalDecision = "approve" | "deny";

export type ResumePayload =
  | { tool_call_id: string; decision: ApprovalDecision }
  | { tool_call_id: string; decision: "answer"; answer: ElicitationAnswer };

export type DoneReason = "complete" | "awaiting_approval" | "awaiting_input" | "step_limit";

// Typed views of the arguments the choreography and labels read. Narrowing
// helpers, not a union — an unknown tool's args are still a plain object.
export type DayPattern = "all" | "weekdays" | "weekends" | "custom";
export type SettingCategory =
  "display" | "transitions" | "output" | "polling" | "location" | "silence_schedule" | "active_page";

export interface CreatePageArgs {
  name: string;
  template_lines: string[];
  device_type?: DeviceType;
  duration_seconds?: number;
  notes_wide?: number;
  notes_tall?: number;
  line_metadata?: LineMetadata[];
  transition_strategy?: string | null;
}

export interface UpdatePageArgs {
  page_id: string;
  name?: string | null;
  template_lines?: string[] | null;
  duration_seconds?: number | null;
  device_type?: DeviceType | null;
  notes_wide?: number | null;
  notes_tall?: number | null;
  line_metadata?: LineMetadata[] | null;
  transition_strategy?: string | null;
}

export interface CreateScheduleArgs {
  page_id: string;
  start_time: string;
  end_time?: string | null;
  day_pattern?: DayPattern;
  custom_days?: string[] | null;
  enabled?: boolean;
}

export interface UpdateScheduleArgs extends Partial<CreateScheduleArgs> {
  schedule_id: string;
}

export interface UpdateSettingArgs {
  category: SettingCategory;
  values: Record<string, unknown>;
}

export interface ConfigurePluginArgs {
  plugin_id: string;
  config: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// What the panel renders
// ---------------------------------------------------------------------------

/**
 * Where a call is in its life, as the panel shows it. `running` is the
 * gap between `tool_call` and `tool_result`; `awaiting_approval` is a
 * destructive tool waiting on the user; `stopped` is a call that was
 * running when the user ended the turn (it may still have completed).
 */
export type ToolPhase = "running" | "awaiting_approval" | "ok" | "blocked" | "error" | "denied" | "stopped";

export type ToolCallDisplay = ToolCall & {
  phase: ToolPhase;
  result?: ToolResult;
  /**
   * The page as it would render after this call, computed locally from the
   * call's arguments so a `create_page` / `update_page` card can show a
   * board preview before the result arrives.
   */
  appliedSnapshot?: CurrentPageSnapshot;
  deviceType?: DeviceType;
};

/** The server's last `status` frame for a segment, rendered with t() by phase. */
export interface TurnStatus {
  phase: SSEStatusData["phase"];
  toolCallId: string | null;
}

/**
 * One transcript entry as the panel holds it.
 *
 * An assistant turn is one entry per model call. A resume (Approve, Deny,
 * an answer) starts a new assistant entry, exactly as the server appends a
 * new assistant message after the `tool` outcome — so the replayed
 * transcript reads the same as the live one, and a question (`ask_user`
 * pauses the loop, so at most one per model call) belongs to the entry
 * that asked it. The panel groups consecutive assistant entries into one
 * visible turn.
 */
export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  /** Tool calls the assistant made in this entry, in order. */
  toolCalls?: ToolCallDisplay[];
  /** The last `status` frame the server sent while this entry was live. */
  status?: TurnStatus;
  /** The tool block being written right now (cleared when it becomes a call). */
  draft?: SSEToolStreamingData;
  /** The question this entry asked, with the answer once given. */
  elicitation?: Elicitation & { answer?: ElicitationAnswer };
  warnings?: string[];
  /** True while the server is still working on this entry. */
  pending?: boolean;
  /**
   * When this entry began, ISO 8601 — what the turn's byline reads as a
   * relative time. Set on assistant entries as the panel creates them;
   * absent on user turns (their bubble carries no byline) and on entries
   * saved before the field existed, which simply show no time.
   */
  at?: string;
}

// ---------------------------------------------------------------------------
// The wire
// ---------------------------------------------------------------------------

export type WireToolStatus = "ok" | "blocked" | "error" | "denied" | "interrupted" | "answered";

/** One transcript entry as the server wants it replayed. */
export type WireMessage =
  | { role: "user"; content: string }
  | {
      role: "assistant";
      content: string;
      tool_calls?: Array<{ id: string; name: string; args: Record<string, unknown> }>;
    }
  | { role: "tool"; tool_call_id: string; name: string; status: WireToolStatus; result: unknown };

export interface CurrentPageSnapshot {
  /** The saved page's id; absent for an unsaved draft in /pages/new. */
  id?: string;
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
  settings_schema?: Record<string, unknown>;
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

export interface CollectionRef {
  id: string;
  name: string;
  page_ids: string[];
  selection_mode: "time" | "variable" | "random";
  time: { interval_seconds: number };
  variable: {
    rules: Array<{ expression: string; page_id: string }>;
    default_page_id: string;
    poll_seconds: number;
  } | null;
  random: { interval_seconds: number } | null;
}

/**
 * Which chat surface the user is talking to. The inline page-editor
 * panel ("editor") biases the AI toward in-place edits of the page
 * being edited; the global drawer ("global") biases it toward creating
 * things and letting the app open them.
 */
export type ChatSurface = "editor" | "global";

export interface ChatTurnContext {
  deviceType: DeviceType;
  surface: ChatSurface;
  currentPage?: CurrentPageSnapshot;
  availablePages?: PageRef[];
  installedPlugins?: InstalledPluginRef[];
  availableSchedules?: ScheduleRef[];
  availableCollections?: CollectionRef[];
  registryPlugins?: RegistryPluginRef[];
}

/**
 * Per-conversation approval override. Sent on every request after the user
 * chose "Approve and don't ask again in this chat"; the install's own
 * `approval_mode` setting is read server-side and never travels here.
 */
export interface ChatApprovalOptions {
  auto_approve_destructive: boolean;
}

export interface ChatRequestBody {
  messages: WireMessage[];
  resume?: ResumePayload;
  approval?: ChatApprovalOptions;
  device_type: DeviceType;
  surface?: ChatSurface;
  current_page?: CurrentPageSnapshot;
  available_pages?: PageRef[];
  installed_plugins?: InstalledPluginRef[];
  available_schedules?: ScheduleRef[];
  available_collections?: CollectionRef[];
  registry_plugins?: RegistryPluginRef[];
  provider_id?: string;
  model?: string;
}

// SSE event payloads from POST /pages/ai/chat. The event name is carried by
// fetchEventSource separately; the data is JSON-decoded.

export interface SSETextData {
  delta: string;
}

/** One `tool_streaming` frame: a tool block the model is still writing. */
export interface SSEToolStreamingData {
  op: string | null;
  /** The whole block so far, not a delta. */
  text: string;
}

export interface SSEStatusData {
  phase: "thinking" | "tool_running";
  message: string;
  tool_call_id: string | null;
  step: number;
}

export type SSEToolCallData = ToolCall;

export type SSEToolResultData = ToolResult;

export type SSEElicitationData = Elicitation;

export interface SSEWarningData {
  message: string;
}

export interface SSEErrorData {
  message: string;
}

export interface SSEDoneData {
  model_used: string;
  provider_id: string | null;
  usage: {
    prompt_tokens: number | null;
    completion_tokens: number | null;
    total_tokens: number | null;
  };
  reason: DoneReason;
  pending_tool_call_id: string | null;
  steps: number;
}
