"use client";

import { Box } from "@fiestaboard/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { AiActionConfirmation } from "@/components/ai-action-confirmation";
import { AiChatPanel } from "@/components/ai-chat-panel";
import { useGlobalAiPanel } from "@/components/global-ai-panel-context";
import { usePageEditorBridge } from "@/components/page-editor-bridge-context";
import { useScheduleEditorBridge } from "@/components/schedule-editor-bridge-context";
import { useRouter } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";
import type {
  ChainingMode,
  ChatTurnContext,
  CreateCollectionArgs,
  CreateScheduleArgs,
  DisablePluginArgs,
  EnablePluginArgs,
  InstallPluginArgs,
  SettingCategory,
  TaskItem,
  ToolCall,
  UninstallPluginArgs,
  UpdatePluginArgs,
  UpdatePluginConfigArgs,
  UpdateSettingArgs,
} from "@/lib/ai-chat-types";
import { type AiOperationResult, type AISettings, api, type ScheduleEntry } from "@/lib/api";
import { isChromelessPath } from "@/lib/chromeless";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Helpers for building tool-result chain messages
// ---------------------------------------------------------------------------

function buildToolResultText(call: ToolCall, success: boolean, errorMsg?: string): string {
  const status = success ? "Success" : `Failed: ${errorMsg ?? "unknown error"}`;
  switch (call.op) {
    case "install_plugin": {
      const a = call.args as InstallPluginArgs;
      return `[Tool result: install_plugin for "${a.plugin_id}" → ${status}.${success ? " Plugin installed and enabled. Continue with any remaining steps." : ""}]`;
    }
    case "update_plugin_config": {
      const a = call.args as UpdatePluginConfigArgs;
      return `[Tool result: update_plugin_config for "${a.plugin_id}" → ${status}.${success ? " Configuration saved. Continue with any remaining steps." : ""}]`;
    }
    case "update_plugin": {
      const a = call.args as UpdatePluginArgs;
      return `[Tool result: update_plugin for "${a.plugin_id}" → ${status}.]`;
    }
    case "enable_plugin": {
      const a = call.args as EnablePluginArgs;
      return `[Tool result: enable_plugin for "${a.plugin_id}" → ${status}.]`;
    }
    case "disable_plugin": {
      const a = call.args as DisablePluginArgs;
      return `[Tool result: disable_plugin for "${a.plugin_id}" → ${status}.]`;
    }
    case "uninstall_plugin": {
      const a = call.args as UninstallPluginArgs;
      return `[Tool result: uninstall_plugin for "${a.plugin_id}" → ${status}.]`;
    }
    case "update_setting": {
      const a = call.args as UpdateSettingArgs;
      return `[Tool result: update_setting (${a.category}) → ${status}.${success ? " Setting applied. Continue with any remaining steps." : ""}]`;
    }
    case "create_collection": {
      const a = call.args as CreateCollectionArgs;
      return `[Tool result: create_collection "${a.name}" → ${status}.${success ? " Collection created. Continue with any remaining steps." : ""}]`;
    }
    case "update_collection":
      return `[Tool result: update_collection → ${status}.]`;
    case "create_schedule": {
      const a = call.args as CreateScheduleArgs;
      return `[Tool result: create_schedule at ${a.start_time} → ${status}.${success ? " Schedule created. Continue with any remaining steps." : ""}]`;
    }
    case "update_schedule":
      return `[Tool result: update_schedule → ${status}.]`;
    case "delete_schedule":
      return `[Tool result: delete_schedule → ${status}.]`;
    case "trigger_system_update":
      return `[Tool result: trigger_system_update → ${status}.]`;
    case "navigate_to_page": {
      if (!success) return `[Tool result: navigate_to_page → ${status}.]`;
      const isNew = call.args.page_id === "new";
      return `[Tool result: navigate_to_page → Success. ${
        isNew
          ? "Blank page editor is now mounted. Surface is 'editor' — use replace_page to ship the template you described, then continue with any remaining steps (schedules, integrations, etc.)."
          : "Page editor is now mounted. Use apply_patch for incremental edits or replace_page to rewrite, then continue with any remaining steps."
      }]`;
    }
    case "navigate_to_schedule":
      return `[Tool result: navigate_to_schedule → ${status}.${success ? " Schedule form is open. Continue with create_schedule (or update_schedule) to commit the change." : ""}]`;
    case "replace_page":
      return `[Tool result: replace_page → ${status}.${success ? " Page template applied. Continue with any remaining steps." : ' Hint: emit navigate_to_page with page_id="new" first if no editor is mounted.'}]`;
    case "apply_patch":
      return `[Tool result: apply_patch → ${status}.${success ? " Patch applied. Continue with any remaining steps." : " Hint: emit navigate_to_page first if no editor is mounted."}]`;
    case "suggest_variables":
      return `[Tool result: suggest_variables → ${status}.${success ? " Suggestions surfaced. Continue with any remaining steps." : ""}]`;
    default:
      return `[Tool result: ${(call as ToolCall).op} → ${status}.]`;
  }
}

// ---------------------------------------------------------------------------
// Server-executed operations (Phase 2 Task 11)
//
// Every op listed here is executed by the server through
// `POST /ai/operations` (src/ai/routes.py -> src/ops/registry.execute), which
// runs the same canonical executor the MCP tools call. The browser's job is
// confirmation UX, cache invalidation and the toast — not a second
// implementation of the operation. Before this, the drawer dispatched each op
// to a different REST endpoint itself, and had drifted from the executors in
// three places (see tests/test_chat_op_http_parity.py).
//
// The ops NOT listed are the six the registry marks `client_side=True`:
// replace_page and apply_patch edit the mounted editor, suggest_variables
// surfaces a list, navigate_to_page / navigate_to_schedule route, and
// update_task_list drives the task panel. They have no server effect and the
// endpoint refuses them with a 400.
//
// tests/test_ops_wiring.py fails the build if this list and the registry
// disagree, or if a server-executed op regrows a browser-side implementation.
// ---------------------------------------------------------------------------

const SERVER_EXECUTED_OPS = [
  "create_collection",
  "create_schedule",
  "delete_schedule",
  "disable_plugin",
  "enable_plugin",
  "install_plugin",
  "trigger_system_update",
  "uninstall_plugin",
  "update_collection",
  "update_plugin",
  "update_plugin_config",
  "update_schedule",
  "update_setting",
] as const;

type ServerExecutedOp = (typeof SERVER_EXECUTED_OPS)[number];
type ServerExecutedCall = ToolCall & { op: ServerExecutedOp };

function isServerExecutedCall(call: ToolCall): call is ServerExecutedCall {
  return (SERVER_EXECUTED_OPS as readonly string[]).includes(call.op);
}

/** Which cached queries each op invalidates — unchanged from the old handlers. */
const OP_QUERY_KEYS: Record<Exclude<ServerExecutedOp, "update_setting">, readonly string[]> = {
  create_collection: ["collections"],
  create_schedule: ["schedules"],
  delete_schedule: ["schedules"],
  disable_plugin: ["plugins"],
  enable_plugin: ["plugins"],
  install_plugin: ["plugins"],
  // A system update recreates the container; nothing local is worth refetching.
  trigger_system_update: [],
  uninstall_plugin: ["plugins"],
  update_collection: ["collections"],
  update_plugin: ["plugins"],
  update_plugin_config: ["plugins"],
  update_schedule: ["schedules"],
};

/** update_setting refreshes only the category it touched. */
const SETTING_QUERY_KEY: Record<SettingCategory, string> = {
  display: "display-settings",
  transitions: "transition-settings",
  output: "output-settings",
  polling: "polling-settings",
  location: "location-settings",
  silence_schedule: "silence-schedule",
  active_page: "active-page",
};

function queryKeysForOp(call: ServerExecutedCall): readonly string[] {
  if (call.op === "update_setting") {
    const key = SETTING_QUERY_KEY[(call.args as UpdateSettingArgs).category];
    return key ? [key] : [];
  }
  return OP_QUERY_KEYS[call.op];
}

export function GlobalAiChatDrawer() {
  const { isOpen, close } = useGlobalAiPanel();
  const t = useTranslations("globalAiChatDrawer");
  const router = useRouter();

  // Focus-management refs for the modal slide-in panel.
  const panelRef = useRef<HTMLDivElement>(null);
  // The element that had focus when the panel opened, so we can restore it on close.
  const openerRef = useRef<HTMLElement | null>(null);
  const queryClient = useQueryClient();
  const { getEditorSnapshot, applyEditorOp, saveEditor, hasEditor, canEditorUndo, editorUndo, waitForEditor } =
    usePageEditorBridge();
  const { hasScheduleEditor, openScheduleForm } = useScheduleEditorBridge();

  // ---------------------------------------------------------------------------
  // AI chaining mode
  // ---------------------------------------------------------------------------
  const [chainingMode, setChainingMode] = useState<ChainingMode>(() => {
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem("fiestaboard:ai-chaining-mode");
      if (stored === "auto-continue" || stored === "autonomous") return stored;
    }
    return "manual";
  });

  useEffect(() => {
    localStorage.setItem("fiestaboard:ai-chaining-mode", chainingMode);
  }, [chainingMode]);

  // Slot ref: AiChatPanel writes its resume() fn here so this component can
  // trigger re-streaming after tool execution without prop-drilling.
  const resumeFnRef = useRef<((text: string) => void) | null>(null);

  // Task list state — updated by update_task_list ops from the AI.
  const [taskList, setTaskList] = useState<TaskItem[]>([]);

  // The FiestaPanel TV viewer must not fire this authenticated query — see
  // CurrentBoardProvider for why this reads window.location, not useLocation().
  const chromeless = typeof window !== "undefined" && isChromelessPath(window.location.pathname);
  const { data: aiSettings } = useQuery<AISettings>({
    queryKey: ["ai-settings"],
    queryFn: () => api.getAiSettings(),
    enabled: !chromeless,
  });

  const { data: pagesData } = useQuery({
    queryKey: ["pages"],
    queryFn: () => api.getPages(),
    enabled: isOpen,
  });

  const { data: pluginsData } = useQuery({
    queryKey: ["plugins"],
    queryFn: () => api.listPlugins(),
    enabled: isOpen,
  });

  const { data: schedulesData } = useQuery({
    queryKey: ["schedules"],
    queryFn: () => api.getSchedules(),
    enabled: isOpen,
  });

  const { data: collectionsData } = useQuery({
    queryKey: ["collections"],
    queryFn: () => api.getCollections(),
    enabled: isOpen,
  });

  const { data: registryData } = useQuery({
    queryKey: ["registry-plugins"],
    queryFn: () => api.listRegistryPlugins(),
    enabled: isOpen,
  });

  // Modal focus management: trap Tab focus inside the panel while open,
  // close on Escape, and restore focus to the opener when it closes.
  useEffect(() => {
    if (!isOpen) return;

    // Remember what had focus so we can restore it on close.
    openerRef.current = document.activeElement as HTMLElement | null;

    const getFocusable = (): HTMLElement[] => {
      const panel = panelRef.current;
      if (!panel) return [];
      return Array.from(
        panel.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((el) => el.offsetParent !== null || el === document.activeElement);
    };

    // Move focus into the panel on open.
    const focusTimer = window.setTimeout(() => {
      const focusable = getFocusable();
      (focusable[0] ?? panelRef.current)?.focus();
    }, 0);

    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        close();
        return;
      }
      if (e.key !== "Tab") return;
      const focusable = getFocusable();
      if (focusable.length === 0) {
        // Nothing focusable yet — keep focus on the panel itself.
        e.preventDefault();
        panelRef.current?.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (e.shiftKey) {
        if (active === first || !panelRef.current?.contains(active)) {
          e.preventDefault();
          last.focus();
        }
      } else if (active === last || !panelRef.current?.contains(active)) {
        e.preventDefault();
        first.focus();
      }
    };

    window.addEventListener("keydown", handler);
    return () => {
      window.clearTimeout(focusTimer);
      window.removeEventListener("keydown", handler);
      // Restore focus to whatever opened the panel.
      openerRef.current?.focus?.();
    };
  }, [isOpen, close]);

  // Auto-close when AI is disabled so the drawer doesn't trap users who
  // navigate to the AI panel and then toggle AI off in Settings (issue #806).
  useEffect(() => {
    if (isOpen && aiSettings && !aiSettings.enabled) {
      close();
    }
  }, [isOpen, aiSettings, close]);

  const getTurnContext = useCallback((): ChatTurnContext => {
    const pages = pagesData?.pages?.map((p) => ({ id: p.id, name: p.name }));
    const plugins = pluginsData?.plugins?.map((p) => ({
      id: p.id,
      name: p.name,
      enabled: p.enabled,
      settings_schema: p.settings_schema,
    }));
    const schedules = schedulesData?.schedules?.map((s) => ({
      id: s.id,
      page_id: s.page_id,
      start_time: s.start_time,
      end_time: s.end_time ?? null,
      day_pattern: s.day_pattern as "all" | "weekdays" | "weekends" | "custom",
      enabled: s.enabled,
    }));
    const collections = collectionsData?.collections?.map((c) => ({
      id: c.id,
      name: c.name,
      page_ids: c.page_ids,
      selection_mode: c.selection_mode,
      time: c.time,
      variable: c.variable,
      random: c.random,
    }));
    const registryPlugins = registryData?.entries?.map((e) => ({
      id: e.id,
      name: e.name,
      description: e.description,
      installed: e.installed,
    }));
    const editorSnapshot = getEditorSnapshot();
    return {
      deviceType: "flagship",
      // "editor" when the user is actively editing a page (so the AI
      // should bias toward in-place edits of that page); "global"
      // otherwise (so the AI biases toward navigation / config).
      surface: editorSnapshot ? "editor" : "global",
      currentPage: editorSnapshot ?? undefined,
      availablePages: pages,
      installedPlugins: plugins,
      availableSchedules: schedules,
      availableCollections: collections,
      registryPlugins,
    };
  }, [pagesData, pluginsData, schedulesData, collectionsData, registryData, getEditorSnapshot]);

  // ---------------------------------------------------------------------------
  // Local UX after a server-executed op: the same toasts (and the same Undo
  // affordances) the per-op handlers showed before execution moved server-side.
  //
  // Undo still goes over the plain REST client rather than the ops endpoint:
  // the chat grammar's create_schedule has no `start_type` / `*_sun_offset`
  // fields, so restoring a deleted sunrise/sunset schedule through it would
  // silently downgrade the entry to a fixed clock time.
  // ---------------------------------------------------------------------------
  const showServerOpToast = useCallback(
    (call: ServerExecutedCall, result: AiOperationResult, previousSchedule?: ScheduleEntry) => {
      const refreshSchedules = () => queryClient.invalidateQueries({ queryKey: ["schedules"] });
      switch (call.op) {
        case "create_schedule": {
          const createdId = result.result.schedule_id;
          toast.success("Schedule created.", {
            action:
              typeof createdId === "string"
                ? {
                    label: "Undo",
                    onClick: () => {
                      void (async () => {
                        await api.deleteSchedule(createdId);
                        await refreshSchedules();
                      })();
                    },
                  }
                : undefined,
            duration: 8000,
          });
          break;
        }
        case "update_schedule":
          toast.success("Schedule updated.", {
            action: previousSchedule
              ? {
                  label: "Undo",
                  onClick: () => {
                    void (async () => {
                      await api.updateSchedule(previousSchedule.id, {
                        page_id: previousSchedule.page_id,
                        start_time: previousSchedule.start_time,
                        end_time: previousSchedule.end_time ?? null,
                        day_pattern: previousSchedule.day_pattern,
                        custom_days: previousSchedule.custom_days,
                        enabled: previousSchedule.enabled,
                      });
                      await refreshSchedules();
                    })();
                  },
                }
              : undefined,
            duration: 8000,
          });
          break;
        case "delete_schedule":
          toast.success("Schedule deleted.", {
            action: previousSchedule
              ? {
                  label: "Undo",
                  onClick: () => {
                    void (async () => {
                      await api.createSchedule({
                        page_id: previousSchedule.page_id,
                        start_time: previousSchedule.start_time,
                        end_time: previousSchedule.end_time ?? null,
                        day_pattern: previousSchedule.day_pattern,
                        custom_days: previousSchedule.custom_days,
                        enabled: previousSchedule.enabled,
                        start_type: previousSchedule.start_type,
                        start_sun_offset: previousSchedule.start_sun_offset,
                        end_type: previousSchedule.end_type,
                        end_sun_offset: previousSchedule.end_sun_offset,
                      });
                      await refreshSchedules();
                    })();
                  },
                }
              : undefined,
            duration: 8000,
          });
          break;
        case "install_plugin":
          toast.success(`Plugin "${(call.args as InstallPluginArgs).plugin_id}" installed successfully.`);
          break;
        case "update_plugin_config":
          toast.success(`Plugin "${(call.args as UpdatePluginConfigArgs).plugin_id}" configuration updated.`);
          break;
        case "update_plugin":
          toast.success(`Plugin "${(call.args as UpdatePluginArgs).plugin_id}" updated successfully.`);
          break;
        case "enable_plugin":
          toast.success(`Plugin "${(call.args as EnablePluginArgs).plugin_id}" enabled.`);
          break;
        case "disable_plugin":
          toast.success(`Plugin "${(call.args as DisablePluginArgs).plugin_id}" disabled.`);
          break;
        case "uninstall_plugin":
          toast.success(`Plugin "${(call.args as UninstallPluginArgs).plugin_id}" uninstalled.`);
          break;
        case "update_setting":
          toast.success("Setting updated.");
          break;
        case "create_collection":
          toast.success(`Collection "${(call.args as CreateCollectionArgs).name}" created.`);
          break;
        case "update_collection":
          toast.success("Collection updated.");
          break;
        case "trigger_system_update":
          toast.success("System update started. The board will restart shortly.");
          break;
      }
    },
    [queryClient],
  );

  // ---------------------------------------------------------------------------
  // The single execution seam: one POST, then the local UX.
  // ---------------------------------------------------------------------------
  const runServerOp = useCallback(
    async (call: ToolCall) => {
      if (!isServerExecutedCall(call)) {
        // Unreachable via the dispatchers below; a guard so an op added to the
        // grammar cannot silently fall through to a no-op "success".
        throw new Error(`${call.op} is not executed server-side`);
      }

      // Undo needs the pre-mutation entry, so read it before the round trip.
      const previousSchedule =
        call.op === "update_schedule" || call.op === "delete_schedule"
          ? schedulesData?.schedules?.find((s) => s.id === call.args.schedule_id)
          : undefined;

      const result = await api.executeAiOperation(call.op, call.args as unknown as Record<string, unknown>);

      for (const key of queryKeysForOp(call)) {
        await queryClient.invalidateQueries({ queryKey: [key] });
      }
      showServerOpToast(call, result, previousSchedule);
    },
    [queryClient, schedulesData, showServerOpToast],
  );

  // ---------------------------------------------------------------------------
  // Chaining: wrap each handler so that on completion (success or failure),
  // a `[Tool result: ...]` message is injected and the AI re-streams if the
  // current mode is auto-continue or autonomous.
  // Declared before handleToolCall so the callback can reference it directly.
  // ---------------------------------------------------------------------------
  const chainAfter = useCallback(
    (call: ToolCall, handler: () => Promise<void>): (() => Promise<void>) =>
      async () => {
        try {
          await handler();
          if (chainingMode === "manual") return;
          resumeFnRef.current?.(buildToolResultText(call, true));
        } catch (e) {
          if (chainingMode !== "manual") {
            resumeFnRef.current?.(buildToolResultText(call, false, String(e)));
          }
        }
      },
    [chainingMode],
  );

  const handleToolCall = useCallback(
    (call: ToolCall): void => {
      switch (call.op) {
        case "navigate_to_page": {
          void chainAfter(call, async () => {
            // Auto-save any in-progress page before navigating so AI-written
            // content isn't lost when the editor unmounts (supports multi-page
            // creation flows where the AI navigates away after replace_page).
            if (hasEditor) {
              await saveEditor().catch(() => {});
            }
            const { page_id, device_type } = call.args;
            if (page_id === "new") {
              const params = new URLSearchParams();
              if (device_type) params.set("device", device_type);
              params.set("fresh", "1");
              router.push(`/pages/new?${params.toString()}`);
            } else {
              router.push(`/pages/edit/${page_id}`);
            }
            // Wait out the route transition so the destination editor is
            // mounted before the chain resumes; otherwise a follow-up
            // replace_page would race the mount and silently no-op.
            await waitForEditor();
          })();
          break;
        }

        case "navigate_to_schedule": {
          void chainAfter(call, async () => {
            const { prefill } = call.args;
            if (hasScheduleEditor) {
              openScheduleForm(prefill ?? undefined);
            } else {
              const params = new URLSearchParams();
              if (prefill?.page_id) params.set("prefill_page_id", prefill.page_id);
              if (prefill?.start_time) params.set("prefill_start", prefill.start_time);
              if (prefill?.end_time) params.set("prefill_end", prefill.end_time);
              if (prefill?.day_pattern) params.set("prefill_days", prefill.day_pattern);
              const qs = params.size ? `?${params.toString()}` : "";
              router.push(`/schedule${qs}`);
            }
          })();
          break;
        }

        case "update_task_list":
          // Status-only op — update the task panel, do NOT chain or call resume.
          setTaskList(call.args.tasks);
          break;

        case "replace_page":
        case "apply_patch":
        case "suggest_variables":
          void chainAfter(call, async () => {
            // Wait on the live handlersRef rather than the closure-captured
            // `hasEditor` state. When the model emits navigate_to_page and
            // replace_page in the same stream turn, both handlers share the
            // pre-navigation closure (hasEditor === false). waitForEditor
            // resolves as soon as the new editor registers, regardless of
            // when the React state catches up.
            const ready = await waitForEditor();
            if (!ready) {
              // Surface the missing editor so the AI can recover (e.g. by
              // first emitting navigate_to_page) instead of the call being
              // silently dropped.
              throw new Error("no page editor mounted");
            }
            applyEditorOp(call);
            // Auto-save after every AI page edit so the content is persisted
            // immediately (supports chaining: the next navigate_to_page won't
            // lose unsaved work, and the user doesn't need to click Save).
            if (call.op !== "suggest_variables") {
              await saveEditor().catch(() => {});
            }
          })();
          break;

        // Schedule ops run immediately (no confirmation card), exactly as
        // before — only the execution moved from three REST calls in this
        // file to one POST /ai/operations.
        case "create_schedule":
        case "update_schedule":
        case "delete_schedule":
          void chainAfter(call, () => runServerOp(call))();
          break;

        case "install_plugin":
        case "update_plugin_config":
        case "update_plugin":
        case "update_setting":
        case "create_collection":
        case "update_collection":
        case "enable_plugin":
        case "disable_plugin":
        case "uninstall_plugin":
        case "trigger_system_update":
          // Handled declaratively via AiActionConfirmation in the chat
          // thread (see renderToolCallSupplement).
          break;

        default:
          break;
      }
    },
    [
      router,
      hasEditor,
      applyEditorOp,
      saveEditor,
      waitForEditor,
      hasScheduleEditor,
      openScheduleForm,
      runServerOp,
      chainAfter,
    ],
  );

  const renderToolCallSupplement = useCallback(
    (call: ToolCall) => {
      if (call.op === "navigate_to_page") return null;
      if (call.op === "navigate_to_schedule") return null;
      if (call.op === "replace_page" || call.op === "apply_patch" || call.op === "suggest_variables") return null;

      const isDestructive =
        call.op === "delete_schedule" || call.op === "trigger_system_update" || call.op === "uninstall_plugin";

      const autoAllow = chainingMode === "autonomous" && !isDestructive;

      // Schedule ops are applied immediately from handleToolCall (unchanged
      // UX) — they have no confirmation card.
      if (call.op === "create_schedule" || call.op === "update_schedule" || call.op === "delete_schedule") {
        return null;
      }

      if (isServerExecutedCall(call)) {
        return (
          <AiActionConfirmation
            call={call}
            onAllow={chainAfter(call, () => runServerOp(call))}
            onDeny={() => {}}
            // Always false for the destructive ops above (uninstall_plugin,
            // trigger_system_update): autonomous mode never skips those.
            autoAllow={autoAllow}
          />
        );
      }
      return null;
    },
    [chainingMode, chainAfter, runServerOp],
  );

  const hasProviders = (aiSettings?.providers?.length ?? 0) > 0;

  // A wall display never grows an AI drawer.
  if (chromeless || !hasProviders) return null;

  return (
    <Box
      ref={panelRef}
      role="dialog"
      aria-modal="true"
      aria-label={t("panelAriaLabel")}
      tabIndex={-1}
      className={cn(
        // A floating card on the same 12px inset the rail sits on — MainContent
        // already reserves 396px (384 panel + 12 inset) for exactly this
        // geometry. The card chrome itself (bg, border, radius, shadow) lives
        // on AiChatPanel's Card; this Box only places and slides it.
        // Below lg it clears the floating mobile header the same way the nav
        // menu does, and the maxWidth clamp keeps the card inside a phone
        // viewport (384 + the 12px inset overflows a 390px screen).
        "fixed right-3 bottom-3 top-[calc(var(--mobile-header-height,56px)+16px)] lg:top-3 z-40 w-96 flex flex-col overflow-hidden",
        "transition-transform duration-300 ease-in-out sidebar-transition",
      )}
      // Inline rather than a Tailwind arbitrary class: translate-x-full alone
      // would leave the 12px inset's worth of card (plus its shadow) peeking
      // at the screen edge, so the closed offset is 100% + the inset.
      style={{
        maxWidth: "calc(100vw - 1.5rem)",
        transform: isOpen ? "translateX(0)" : "translateX(calc(100% + 0.75rem))",
      }}
      aria-hidden={!isOpen}
    >
      <AiChatPanel
        getTurnContext={getTurnContext}
        onToolCall={handleToolCall}
        onClose={close}
        renderToolCallSupplement={renderToolCallSupplement}
        canUndo={hasEditor && canEditorUndo()}
        onUndo={hasEditor ? editorUndo : undefined}
        resumeFnRef={resumeFnRef}
        chainingMode={chainingMode}
        onChainingModeChange={setChainingMode}
        taskList={taskList}
        onConversationReset={() => setTaskList([])}
      />
    </Box>
  );
}
