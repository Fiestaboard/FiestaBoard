"use client";

import { useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { cn } from "@/lib/utils";
import { AiChatPanel } from "@/components/ai-chat-panel";
import { AiActionConfirmation } from "@/components/ai-action-confirmation";
import { useGlobalAiPanel } from "@/components/global-ai-panel-context";
import { usePageEditorBridge } from "@/components/page-editor-bridge-context";
import { useScheduleEditorBridge } from "@/components/schedule-editor-bridge-context";
import { api, type AISettings } from "@/lib/api";
import type {
  ChatTurnContext,
  CreateCarouselArgs,
  CreateScheduleArgs,
  DeleteScheduleArgs,
  InstallPluginArgs,
  ToolCall,
  UpdateCarouselArgs,
  UpdatePluginArgs,
  UpdatePluginConfigArgs,
  UpdateScheduleArgs,
  UpdateSettingArgs,
} from "@/lib/ai-chat-types";

export function GlobalAiChatDrawer() {
  const { isOpen, close } = useGlobalAiPanel();
  const router = useRouter();
  const queryClient = useQueryClient();
  const { getEditorSnapshot, applyEditorOp, hasEditor, canEditorUndo, editorUndo } = usePageEditorBridge();
  const { hasScheduleEditor, openScheduleForm } = useScheduleEditorBridge();

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

  const { data: carouselsData } = useQuery({
    queryKey: ["carousels"],
    queryFn: () => api.getCarousels(),
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

  const getTurnContext = useCallback((): ChatTurnContext => {
    const pages = pagesData?.pages?.map((p) => ({ id: p.id, name: p.name }));
    const plugins = pluginsData?.plugins?.map((p) => ({
      id: p.id,
      name: p.name,
      enabled: p.enabled,
    }));
    const schedules = schedulesData?.schedules?.map((s) => ({
      id: s.id,
      page_id: s.page_id,
      start_time: s.start_time,
      end_time: s.end_time ?? null,
      day_pattern: s.day_pattern as "all" | "weekdays" | "weekends" | "custom",
      enabled: s.enabled,
    }));
    const carousels = carouselsData?.carousels?.map((c) => ({
      id: c.id,
      name: c.name,
      page_ids: c.page_ids,
      interval_seconds: c.interval_seconds,
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
      currentPage: editorSnapshot ?? undefined,
      availablePages: pages,
      installedPlugins: plugins,
      availableSchedules: schedules,
      availableCarousels: carousels,
      registryPlugins,
    };
  }, [pagesData, pluginsData, schedulesData, carouselsData, registryData, getEditorSnapshot]);

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

  const handleToolCall = useCallback(
    (call: ToolCall): void => {
      switch (call.op) {
        case "navigate_to_page": {
          const { page_id, device_type } = call.args;
          if (page_id === "new") {
            const params = new URLSearchParams();
            if (device_type) params.set("device", device_type);
            params.set("fresh", "1");
            router.push(`/pages/new?${params.toString()}`);
          } else {
            router.push(`/pages/edit/${page_id}`);
          }
          break;
        }

        case "navigate_to_schedule": {
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
          break;
        }

        case "replace_page":
        case "apply_patch":
        case "suggest_variables":
          // Delegate to the page editor if one is mounted.
          if (hasEditor) {
            applyEditorOp(call);
          }
          break;

        case "create_schedule":
          void handleCreateSchedule(call.args);
          break;

        case "update_schedule":
          void handleUpdateSchedule(call.args);
          break;

        case "delete_schedule":
          void handleDeleteSchedule(call.args);
          break;

        case "install_plugin":
        case "update_plugin_config":
        case "update_plugin":
        case "update_setting":
        case "create_carousel":
        case "update_carousel":
        case "trigger_system_update":
          // Handled declaratively via AiActionConfirmation in the chat
          // thread (see renderToolCallSupplement).
          break;

        default:
          break;
      }
    },
    [router, close, hasEditor, applyEditorOp, hasScheduleEditor, openScheduleForm, handleCreateSchedule, handleUpdateSchedule, handleDeleteSchedule],
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
          await api.updateSilenceSchedule(
            args.values as Parameters<typeof api.updateSilenceSchedule>[0],
          );
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

  const handleCreateCarousel = useCallback(
    async (args: CreateCarouselArgs) => {
      await api.createCarousel({
        name: args.name,
        page_ids: args.page_ids,
        interval_seconds: args.interval_seconds,
      });
      await queryClient.invalidateQueries({ queryKey: ["carousels"] });
      toast.success(`Carousel "${args.name}" created.`);
    },
    [queryClient],
  );

  const handleUpdateCarousel = useCallback(
    async (args: UpdateCarouselArgs) => {
      const { carousel_id, ...update } = args;
      await api.updateCarousel(carousel_id, {
        ...(update.name != null && { name: update.name }),
        ...(update.page_ids != null && { page_ids: update.page_ids }),
        ...(update.interval_seconds != null && { interval_seconds: update.interval_seconds }),
      });
      await queryClient.invalidateQueries({ queryKey: ["carousels"] });
      toast.success("Carousel updated.");
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
      if (call.op === "replace_page" || call.op === "apply_patch" || call.op === "suggest_variables") return null;

      if (call.op === "install_plugin") {
        return (
          <AiActionConfirmation
            call={call}
            onAllow={() => handleInstallPlugin(call.args as InstallPluginArgs)}
            onDeny={() => {}}
          />
        );
      }
      if (call.op === "update_plugin_config") {
        return (
          <AiActionConfirmation
            call={call}
            onAllow={() => handleUpdatePluginConfig(call.args as UpdatePluginConfigArgs)}
            onDeny={() => {}}
          />
        );
      }
      if (call.op === "update_plugin") {
        return (
          <AiActionConfirmation
            call={call}
            onAllow={() => handleUpdatePlugin(call.args as UpdatePluginArgs)}
            onDeny={() => {}}
          />
        );
      }
      if (call.op === "update_setting") {
        return (
          <AiActionConfirmation
            call={call}
            onAllow={() => handleUpdateSetting(call.args as UpdateSettingArgs)}
            onDeny={() => {}}
          />
        );
      }
      if (call.op === "create_carousel") {
        return (
          <AiActionConfirmation
            call={call}
            onAllow={() => handleCreateCarousel(call.args as CreateCarouselArgs)}
            onDeny={() => {}}
          />
        );
      }
      if (call.op === "update_carousel") {
        return (
          <AiActionConfirmation
            call={call}
            onAllow={() => handleUpdateCarousel(call.args as UpdateCarouselArgs)}
            onDeny={() => {}}
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
            onAllow={() => handleTriggerSystemUpdate()}
            onDeny={() => {}}
          />
        );
      }
      return null;
    },
    [
      handleInstallPlugin,
      handleUpdatePluginConfig,
      handleUpdatePlugin,
      handleUpdateSetting,
      handleCreateCarousel,
      handleUpdateCarousel,
      handleTriggerSystemUpdate,
    ],
  );

  const hasProviders = (aiSettings?.providers?.length ?? 0) > 0;

  if (!hasProviders) return null;

  return (
    <div
      className={cn(
        "fixed right-0 top-0 bottom-0 z-40 w-96 flex flex-col bg-background",
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
      />
    </div>
  );
}
