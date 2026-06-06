"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { AiActionConfirmation } from "@/components/ai-action-confirmation";
import { AiChatPanel } from "@/components/ai-chat-panel";
import { useGlobalAiPanel } from "@/components/global-ai-panel-context";
import { usePageEditorBridge } from "@/components/page-editor-bridge-context";
import { useScheduleEditorBridge } from "@/components/schedule-editor-bridge-context";
import type {
  ChainingMode,
  ChatTurnContext,
  CreateCollectionArgs,
  CreateScheduleArgs,
  DeleteScheduleArgs,
  DisablePluginArgs,
  EnablePluginArgs,
  InstallPluginArgs,
  TaskItem,
  ToolCall,
  UninstallPluginArgs,
  UpdateCollectionArgs,
  UpdatePluginArgs,
  UpdatePluginConfigArgs,
  UpdateScheduleArgs,
  UpdateSettingArgs,
} from "@/lib/ai-chat-types";
import { type AISettings, api } from "@/lib/api";
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

export function GlobalAiChatDrawer() {
  const { isOpen, close } = useGlobalAiPanel();
  const router = useRouter();
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

  const { data: aiSettings } = useQuery<AISettings>({
    queryKey: ["ai-settings"],
    queryFn: () => api.getAiSettings(),
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

  // Close on Escape
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
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

  const handleCreateSchedule = useCallback(
    async (args: CreateScheduleArgs) => {
      const created = await api.createSchedule({
        page_id: args.page_id,
        start_time: args.start_time,
        end_time: args.end_time ?? null,
        day_pattern: args.day_pattern,
        custom_days: args.custom_days ?? undefined,
        enabled: args.enabled,
      });
      await queryClient.invalidateQueries({ queryKey: ["schedules"] });
      toast.success("Schedule created.", {
        action: {
          label: "Undo",
          onClick: () => {
            void (async () => {
              await api.deleteSchedule(created.id);
              await queryClient.invalidateQueries({ queryKey: ["schedules"] });
            })();
          },
        },
        duration: 8000,
      });
    },
    [queryClient],
  );

  const handleUpdateSchedule = useCallback(
    async (args: UpdateScheduleArgs) => {
      const { schedule_id, ...update } = args;
      const oldSchedule = schedulesData?.schedules?.find((s) => s.id === schedule_id);
      await api.updateSchedule(schedule_id, {
        ...(update.page_id != null && { page_id: update.page_id }),
        ...(update.start_time != null && { start_time: update.start_time }),
        ...("end_time" in update && { end_time: update.end_time ?? null }),
        ...(update.day_pattern != null && { day_pattern: update.day_pattern }),
        ...(update.custom_days != null && { custom_days: update.custom_days }),
        ...(update.enabled != null && { enabled: update.enabled }),
      });
      await queryClient.invalidateQueries({ queryKey: ["schedules"] });
      toast.success("Schedule updated.", {
        action: oldSchedule
          ? {
              label: "Undo",
              onClick: () => {
                void (async () => {
                  await api.updateSchedule(schedule_id, {
                    page_id: oldSchedule.page_id,
                    start_time: oldSchedule.start_time,
                    end_time: oldSchedule.end_time ?? null,
                    day_pattern: oldSchedule.day_pattern,
                    custom_days: oldSchedule.custom_days,
                    enabled: oldSchedule.enabled,
                  });
                  await queryClient.invalidateQueries({ queryKey: ["schedules"] });
                })();
              },
            }
          : undefined,
        duration: 8000,
      });
    },
    [queryClient, schedulesData],
  );

  const handleDeleteSchedule = useCallback(
    async (args: DeleteScheduleArgs) => {
      const schedule = schedulesData?.schedules?.find((s) => s.id === args.schedule_id);
      await api.deleteSchedule(args.schedule_id);
      await queryClient.invalidateQueries({ queryKey: ["schedules"] });
      toast.success("Schedule deleted.", {
        action: schedule
          ? {
              label: "Undo",
              onClick: () => {
                void (async () => {
                  await api.createSchedule({
                    page_id: schedule.page_id,
                    start_time: schedule.start_time,
                    end_time: schedule.end_time ?? null,
                    day_pattern: schedule.day_pattern,
                    custom_days: schedule.custom_days,
                    enabled: schedule.enabled,
                    start_type: schedule.start_type,
                    start_sun_offset: schedule.start_sun_offset,
                    end_type: schedule.end_type,
                    end_sun_offset: schedule.end_sun_offset,
                  });
                  await queryClient.invalidateQueries({ queryKey: ["schedules"] });
                })();
              },
            }
          : undefined,
        duration: 8000,
      });
    },
    [queryClient, schedulesData],
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

        case "create_schedule":
          void chainAfter(call, () => handleCreateSchedule(call.args))();
          break;

        case "update_schedule":
          void chainAfter(call, () => handleUpdateSchedule(call.args))();
          break;

        case "delete_schedule":
          void chainAfter(call, () => handleDeleteSchedule(call.args))();
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
      close,
      hasEditor,
      applyEditorOp,
      saveEditor,
      waitForEditor,
      hasScheduleEditor,
      openScheduleForm,
      handleCreateSchedule,
      handleUpdateSchedule,
      handleDeleteSchedule,
      chainAfter,
    ],
  );

  const handleInstallPlugin = useCallback(
    async (args: InstallPluginArgs) => {
      await api.installRegistryPlugin(args.plugin_id);
      if (args.auto_enable !== false) {
        await api.enablePlugin(args.plugin_id);
      }
      if (args.initial_config && Object.keys(args.initial_config).length > 0) {
        await api.updatePluginConfig(args.plugin_id, args.initial_config);
      }
      await queryClient.invalidateQueries({ queryKey: ["plugins"] });
      toast.success(`Plugin "${args.plugin_id}" installed successfully.`);
    },
    [queryClient],
  );

  const handleUpdatePluginConfig = useCallback(
    async (args: UpdatePluginConfigArgs) => {
      await api.updatePluginConfig(args.plugin_id, args.config);
      await queryClient.invalidateQueries({ queryKey: ["plugins"] });
      toast.success(`Plugin "${args.plugin_id}" configuration updated.`);
    },
    [queryClient],
  );

  const handleUpdatePlugin = useCallback(
    async (args: UpdatePluginArgs) => {
      await api.updatePlugin(args.plugin_id);
      await queryClient.invalidateQueries({ queryKey: ["plugins"] });
      toast.success(`Plugin "${args.plugin_id}" updated successfully.`);
    },
    [queryClient],
  );

  const handleEnablePlugin = useCallback(
    async (args: EnablePluginArgs) => {
      await api.enablePlugin(args.plugin_id);
      await queryClient.invalidateQueries({ queryKey: ["plugins"] });
      toast.success(`Plugin "${args.plugin_id}" enabled.`);
    },
    [queryClient],
  );

  const handleDisablePlugin = useCallback(
    async (args: DisablePluginArgs) => {
      await api.disablePlugin(args.plugin_id);
      await queryClient.invalidateQueries({ queryKey: ["plugins"] });
      toast.success(`Plugin "${args.plugin_id}" disabled.`);
    },
    [queryClient],
  );

  const handleUninstallPlugin = useCallback(
    async (args: UninstallPluginArgs) => {
      await api.uninstallPlugin(args.plugin_id);
      await queryClient.invalidateQueries({ queryKey: ["plugins"] });
      toast.success(`Plugin "${args.plugin_id}" uninstalled.`);
    },
    [queryClient],
  );

  const handleUpdateSetting = useCallback(
    async (args: UpdateSettingArgs) => {
      switch (args.category) {
        case "display":
          await api.updateDisplaySettings(args.values as Parameters<typeof api.updateDisplaySettings>[0]);
          await queryClient.invalidateQueries({ queryKey: ["display-settings"] });
          break;
        case "transitions":
          await api.updateTransitionSettings(args.values as Parameters<typeof api.updateTransitionSettings>[0]);
          await queryClient.invalidateQueries({ queryKey: ["transition-settings"] });
          break;
        case "output": {
          const target = (args.values as { target?: string }).target;
          if (target === "ui" || target === "board" || target === "both") {
            await api.updateOutputSettings(target);
            await queryClient.invalidateQueries({ queryKey: ["output-settings"] });
          }
          break;
        }
        case "polling": {
          const interval = (args.values as { interval_seconds?: number }).interval_seconds;
          if (typeof interval === "number") {
            await api.updatePollingSettings(interval);
            await queryClient.invalidateQueries({ queryKey: ["polling-settings"] });
          }
          break;
        }
        case "location":
          await api.updateLocationSettings(args.values as Parameters<typeof api.updateLocationSettings>[0]);
          await queryClient.invalidateQueries({ queryKey: ["location-settings"] });
          break;
        case "silence_schedule":
          await api.updateSilenceSchedule(args.values as Parameters<typeof api.updateSilenceSchedule>[0]);
          await queryClient.invalidateQueries({ queryKey: ["silence-schedule"] });
          break;
        case "active_page": {
          const pageId = (args.values as { page_id?: string }).page_id ?? null;
          await api.setActivePage(pageId);
          await queryClient.invalidateQueries({ queryKey: ["active-page"] });
          break;
        }
      }
      toast.success("Setting updated.");
    },
    [queryClient],
  );

  const handleCreateCollection = useCallback(
    async (args: CreateCollectionArgs) => {
      await api.createCollection({
        name: args.name,
        page_ids: args.page_ids,
        selection_mode: "time",
        time: { interval_seconds: args.interval_seconds },
      });
      await queryClient.invalidateQueries({ queryKey: ["collections"] });
      toast.success(`Collection "${args.name}" created.`);
    },
    [queryClient],
  );

  const handleUpdateCollection = useCallback(
    async (args: UpdateCollectionArgs) => {
      const { collection_id, ...update } = args;
      await api.updateCollection(collection_id, {
        ...(update.name != null && { name: update.name }),
        ...(update.page_ids != null && { page_ids: update.page_ids }),
        ...(update.interval_seconds != null && {
          selection_mode: "time",
          time: { interval_seconds: update.interval_seconds },
        }),
      });
      await queryClient.invalidateQueries({ queryKey: ["collections"] });
      toast.success("Collection updated.");
    },
    [queryClient],
  );

  const handleTriggerSystemUpdate = useCallback(async () => {
    await api.applyUpdate();
    toast.success("System update started. The board will restart shortly.");
  }, []);

  const renderToolCallSupplement = useCallback(
    (call: ToolCall) => {
      if (call.op === "navigate_to_page") return null;
      if (call.op === "navigate_to_schedule") return null;
      if (call.op === "replace_page" || call.op === "apply_patch" || call.op === "suggest_variables") return null;

      const isDestructive =
        call.op === "delete_schedule" || call.op === "trigger_system_update" || call.op === "uninstall_plugin";

      const autoAllow = chainingMode === "autonomous" && !isDestructive;

      if (call.op === "install_plugin") {
        return (
          <AiActionConfirmation
            call={call}
            onAllow={chainAfter(call, () => handleInstallPlugin(call.args as InstallPluginArgs))}
            onDeny={() => {}}
            autoAllow={autoAllow}
          />
        );
      }
      if (call.op === "update_plugin_config") {
        return (
          <AiActionConfirmation
            call={call}
            onAllow={chainAfter(call, () => handleUpdatePluginConfig(call.args as UpdatePluginConfigArgs))}
            onDeny={() => {}}
            autoAllow={autoAllow}
          />
        );
      }
      if (call.op === "update_plugin") {
        return (
          <AiActionConfirmation
            call={call}
            onAllow={chainAfter(call, () => handleUpdatePlugin(call.args as UpdatePluginArgs))}
            onDeny={() => {}}
            autoAllow={autoAllow}
          />
        );
      }
      if (call.op === "enable_plugin") {
        return (
          <AiActionConfirmation
            call={call}
            onAllow={chainAfter(call, () => handleEnablePlugin(call.args as EnablePluginArgs))}
            onDeny={() => {}}
            autoAllow={autoAllow}
          />
        );
      }
      if (call.op === "disable_plugin") {
        return (
          <AiActionConfirmation
            call={call}
            onAllow={chainAfter(call, () => handleDisablePlugin(call.args as DisablePluginArgs))}
            onDeny={() => {}}
            autoAllow={autoAllow}
          />
        );
      }
      if (call.op === "uninstall_plugin") {
        return (
          <AiActionConfirmation
            call={call}
            onAllow={chainAfter(call, () => handleUninstallPlugin(call.args as UninstallPluginArgs))}
            onDeny={() => {}}
            autoAllow={autoAllow}
          />
        );
      }
      if (call.op === "update_setting") {
        return (
          <AiActionConfirmation
            call={call}
            onAllow={chainAfter(call, () => handleUpdateSetting(call.args as UpdateSettingArgs))}
            onDeny={() => {}}
            autoAllow={autoAllow}
          />
        );
      }
      if (call.op === "create_collection") {
        return (
          <AiActionConfirmation
            call={call}
            onAllow={chainAfter(call, () => handleCreateCollection(call.args as CreateCollectionArgs))}
            onDeny={() => {}}
            autoAllow={autoAllow}
          />
        );
      }
      if (call.op === "update_collection") {
        return (
          <AiActionConfirmation
            call={call}
            onAllow={chainAfter(call, () => handleUpdateCollection(call.args as UpdateCollectionArgs))}
            onDeny={() => {}}
            autoAllow={autoAllow}
          />
        );
      }
      if (call.op === "create_schedule" || call.op === "update_schedule" || call.op === "delete_schedule") {
        return null;
      }
      if (call.op === "trigger_system_update") {
        return (
          <AiActionConfirmation
            call={call}
            onAllow={chainAfter(call, () => handleTriggerSystemUpdate())}
            onDeny={() => {}}
            autoAllow={autoAllow} // always false because isDestructive
          />
        );
      }
      return null;
    },
    [
      chainingMode,
      chainAfter,
      handleInstallPlugin,
      handleUpdatePluginConfig,
      handleUpdatePlugin,
      handleEnablePlugin,
      handleDisablePlugin,
      handleUninstallPlugin,
      handleUpdateSetting,
      handleCreateCollection,
      handleUpdateCollection,
      handleTriggerSystemUpdate,
    ],
  );

  const hasProviders = (aiSettings?.providers?.length ?? 0) > 0;

  if (!hasProviders) return null;

  return (
    <div
      className={cn(
        "fixed right-0 top-0 bottom-0 z-40 w-96 flex flex-col bg-background overflow-hidden",
        "transition-transform duration-300 ease-in-out sidebar-transition",
        isOpen ? "translate-x-0" : "translate-x-full",
      )}
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
    </div>
  );
}
