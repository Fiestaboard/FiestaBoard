"use client";

import { Box } from "@fiestaboard/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { type AiChatController, AiChatPanel } from "@/components/ai-chat-panel";
import { useSpotlight } from "@/components/ai-spotlight/spotlight-provider";
import { labelForTool } from "@/components/ai-tool-labels";
import { useGlobalAiPanel } from "@/components/global-ai-panel-context";
import { usePageEditorBridge } from "@/components/page-editor-bridge-context";
import { useScheduleEditorBridge } from "@/components/schedule-editor-bridge-context";
import { useRouter } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";
import type { ChatTurnContext, ToolCall, ToolResult } from "@/lib/ai-chat-types";
import { queryKeysForTool } from "@/lib/ai-choreography/query-keys";
import type { ChoreographyContext } from "@/lib/ai-choreography/types";
import { useChoreographer } from "@/lib/ai-choreography/use-choreographer";
import { type AISettings, api, type ScheduleEntry } from "@/lib/api";
import { isChromelessPath } from "@/lib/chromeless";
import type { StopReason } from "@/lib/use-ai-chat";
import { cn } from "@/lib/utils";

/** The chaining-mode preference of the browser-side loop; gone with it. */
const LEGACY_CHAINING_MODE_KEY = "fiestaboard:ai-chaining-mode";

/**
 * The global AI drawer: a floating card on every screen that hosts the chat
 * panel and reacts to what the server-side loop did.
 *
 * Every tool now runs on the server through the MCP server; the browser's
 * job here is to keep the screen honest afterwards — invalidate the caches a
 * tool made stale, toast the outcome, keep the schedule Undo affordances —
 * and to hand the panel the context each turn starts from. Navigation and
 * the on-screen walkthrough of each call are the next PR (the choreography).
 */
export function GlobalAiChatDrawer() {
  const { isOpen, close } = useGlobalAiPanel();
  const t = useTranslations("globalAiChatDrawer");

  // Focus-management refs for the modal slide-in panel.
  const panelRef = useRef<HTMLDivElement>(null);
  // The element that had focus when the panel opened, so we can restore it on close.
  const openerRef = useRef<HTMLElement | null>(null);
  const queryClient = useQueryClient();
  const router = useRouter();
  const { getEditorSnapshot, staging: pageStaging } = usePageEditorBridge();
  const { staging: scheduleStaging } = useScheduleEditorBridge();
  const spotlight = useSpotlight();
  const tPanel = useTranslations("aiChatPanel");
  const tChoreography = useTranslations("aiChoreography");
  const controllerRef = useRef<AiChatController | null>(null);
  // The call the server paused on, for the spotlight's Approve/Deny.
  const pendingApprovalRef = useRef<string | null>(null);
  const reducedMotion = useReducedMotion();

  // The walkthrough: where each call lands on screen, played in order.
  const choreographyCtx = useMemo<ChoreographyContext>(
    () => ({
      navigate: (href) => router.push(href),
      pathname: () => (typeof window === "undefined" ? "/" : window.location.pathname),
      spotlight,
      pageEditor: pageStaging,
      schedule: scheduleStaging,
      t: tChoreography,
      label: (call) => labelForTool(call, tPanel),
      reducedMotion,
    }),
    [router, spotlight, pageStaging, scheduleStaging, tChoreography, tPanel, reducedMotion],
  );
  const choreographer = useChoreographer(choreographyCtx);
  const driving = choreographer.driving;

  useEffect(() => {
    spotlight.setHandlers({
      onStop: () => controllerRef.current?.stop(),
      onApprove: () => {
        const id = pendingApprovalRef.current;
        if (id) controllerRef.current?.approve(id, "approve");
      },
      onDeny: () => {
        const id = pendingApprovalRef.current;
        if (id) controllerRef.current?.approve(id, "deny");
      },
    });
  }, [spotlight]);

  // The browser-side loop's chaining preference has no meaning any more;
  // clear it so a downgrade cannot resurrect it either.
  useEffect(() => {
    try {
      localStorage.removeItem(LEGACY_CHAINING_MODE_KEY);
    } catch {
      /* storage may be unavailable; nothing to clear */
    }
  }, []);

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

  // Remember what had focus when the panel opened; give it back on close.
  useEffect(() => {
    if (!isOpen) return;
    openerRef.current = document.activeElement as HTMLElement | null;
    return () => {
      openerRef.current?.focus?.();
    };
  }, [isOpen]);

  // Modal focus management: trap Tab focus inside the panel while open and
  // close on Escape. While the walkthrough is driving the screen the panel
  // is not modal: the trap is released, focus is left alone, and Escape
  // stops the assistant instead of closing the panel.
  useEffect(() => {
    if (!isOpen) return;
    if (driving) {
      const stopOnEscape = (e: KeyboardEvent) => {
        if (e.key === "Escape") controllerRef.current?.stop();
      };
      window.addEventListener("keydown", stopOnEscape);
      return () => window.removeEventListener("keydown", stopOnEscape);
    }

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
    };
  }, [isOpen, driving, close]);

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
      // should bias toward updating THAT page); "global" otherwise (so the
      // AI biases toward creating things the app then opens).
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
  // After a tool ran: the toast, and for schedules the same Undo affordances
  // as before. Undo goes over the plain REST client: the MCP create_schedule
  // has no `start_type` / `*_sun_offset` fields, so restoring a deleted
  // sunrise/sunset schedule through it would silently downgrade the entry to
  // a fixed clock time.
  // ---------------------------------------------------------------------------
  const toastForToolResult = useCallback(
    (call: ToolCall, result: ToolResult, previousSchedule?: ScheduleEntry) => {
      const refreshSchedules = () => queryClient.invalidateQueries({ queryKey: ["schedules"] });
      if (result.status === "denied") return;
      if (result.status !== "ok") {
        toast.error(t("toast.toolFailed", { tool: call.title || call.name, error: result.error ?? result.summary }));
        return;
      }
      const payload = (result.result ?? {}) as Record<string, unknown>;
      switch (call.name) {
        case "create_schedule": {
          const createdId = payload.schedule_id;
          toast.success(t("toast.scheduleCreated"), {
            action:
              typeof createdId === "string"
                ? {
                    label: t("toast.undo"),
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
          toast.success(t("toast.scheduleUpdated"), {
            action: previousSchedule
              ? {
                  label: t("toast.undo"),
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
          toast.success(t("toast.scheduleDeleted"), {
            action: previousSchedule
              ? {
                  label: t("toast.undo"),
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
        case "create_page":
          toast.success(t("toast.pageCreated"));
          break;
        case "update_page":
          toast.success(t("toast.pageUpdated"));
          break;
        case "delete_page":
          toast.success(t("toast.pageDeleted"));
          break;
        case "install_plugin":
          toast.success(t("toast.pluginInstalled", { id: String(call.args.plugin_id ?? "") }));
          break;
        case "configure_plugin":
          toast.success(t("toast.pluginConfigured", { id: String(call.args.plugin_id ?? "") }));
          break;
        case "update_plugin":
          toast.success(t("toast.pluginUpdated", { id: String(call.args.plugin_id ?? "") }));
          break;
        case "enable_plugin":
          toast.success(t("toast.pluginEnabled", { id: String(call.args.plugin_id ?? "") }));
          break;
        case "disable_plugin":
          toast.success(t("toast.pluginDisabled", { id: String(call.args.plugin_id ?? "") }));
          break;
        case "uninstall_plugin":
          toast.success(t("toast.pluginUninstalled", { id: String(call.args.plugin_id ?? "") }));
          break;
        case "update_setting":
          toast.success(t("toast.settingUpdated"));
          break;
        case "create_collection":
          toast.success(t("toast.collectionCreated", { name: String(call.args.name ?? "") }));
          break;
        case "update_collection":
          toast.success(t("toast.collectionUpdated"));
          break;
        case "delete_collection":
          toast.success(t("toast.collectionDeleted"));
          break;
        case "set_active_page":
          toast.success(t("toast.activePageSet"));
          break;
        case "send_message":
          toast.success(t("toast.messageSent"));
          break;
        case "trigger_system_update":
          toast.success(t("toast.systemUpdate"));
          break;
        default:
          // Read-only tools and anything this list does not know: no toast.
          break;
      }
    },
    [queryClient, t],
  );

  const invalidateFor = useCallback(
    async (call: ToolCall) => {
      await Promise.all(queryKeysForTool(call).map((key) => queryClient.invalidateQueries({ queryKey: [...key] })));
    },
    [queryClient],
  );

  const handleToolResult = useCallback(
    (result: ToolResult, call: ToolCall) => {
      // Undo needs the pre-mutation entry. Read it from the cache now, not
      // from a render-time snapshot: this handler is captured for the whole
      // turn, and an earlier call in the same turn may have refreshed it.
      const previousSchedule =
        call.name === "update_schedule" || call.name === "delete_schedule"
          ? queryClient
              .getQueryData<{ schedules?: ScheduleEntry[] }>(["schedules"])
              ?.schedules?.find((s) => s.id === call.args.schedule_id)
          : undefined;
      if (pendingApprovalRef.current === result.id) pendingApprovalRef.current = null;
      // The walkthrough settles the call on screen (a created page is
      // opened there); the caches refresh so what it points at is real.
      choreographer.onToolResult(result);
      void invalidateFor(call).then(() => toastForToolResult(call, result, previousSchedule));
    },
    [choreographer, invalidateFor, queryClient, toastForToolResult],
  );

  const handleToolCall = useCallback((call: ToolCall) => choreographer.onToolCall(call), [choreographer]);
  const handleToolStreaming = useCallback(
    (draft: { text: string }) => choreographer.onDraft(draft.text),
    [choreographer],
  );
  const handleAwaitingApproval = useCallback(
    (call: ToolCall) => {
      pendingApprovalRef.current = call.id;
      choreographer.onAwaitingApproval(call);
    },
    [choreographer],
  );
  const handleTurnComplete = useCallback(() => {
    pendingApprovalRef.current = null;
    choreographer.onTurnEnd();
  }, [choreographer]);

  // Stop ends the stream, but a tool that was already running finishes on
  // the server without a result reaching us. Refresh what it may have
  // changed on two ticks — once soon, once after a slow one (a plugin
  // install) has had time to land — the same two-tick idea as
  // scheduleBoardStateInvalidations in use-board.ts.
  //
  // A fatal stream error leaves calls unresolved too; those get the same
  // refresh but no "Stopped" toast — the panel shows the error itself.
  const refreshTimersRef = useRef<number[]>([]);
  useEffect(() => {
    const timers = refreshTimersRef.current;
    return () => {
      for (const id of timers) window.clearTimeout(id);
    };
  }, []);
  const handleStopped = useCallback(
    (unresolved: ToolCall[], reason: StopReason) => {
      pendingApprovalRef.current = null;
      choreographer.onAbort();
      if (unresolved.length === 0) return;
      if (reason === "stopped") toast.info(t("toast.stopped"));
      const refresh = () => {
        for (const call of unresolved) void invalidateFor(call);
      };
      for (const delay of [1000, 5000]) {
        const id = window.setTimeout(() => {
          refreshTimersRef.current = refreshTimersRef.current.filter((t) => t !== id);
          refresh();
        }, delay);
        refreshTimersRef.current.push(id);
      }
    },
    [choreographer, invalidateFor, t],
  );

  const hasProviders = (aiSettings?.providers?.length ?? 0) > 0;

  // A wall display never grows an AI drawer.
  if (chromeless || !hasProviders) return null;

  return (
    <Box
      ref={panelRef}
      role="dialog"
      aria-modal={!driving}
      data-driving={driving ? "" : undefined}
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
        onToolStreaming={handleToolStreaming}
        onToolResult={handleToolResult}
        onAwaitingApproval={handleAwaitingApproval}
        onTurnComplete={handleTurnComplete}
        onStopped={handleStopped}
        onClose={close}
        controllerRef={controllerRef}
      />
    </Box>
  );
}

/** True when the user asked the OS for less motion; tracks the preference live. */
function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return reduced;
}
