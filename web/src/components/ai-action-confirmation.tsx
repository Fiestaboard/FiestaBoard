"use client";

import {
  Calendar,
  CheckCircle,
  Download,
  ListVideo,
  Power,
  PowerOff,
  RefreshCw,
  Settings,
  Sliders,
  Trash2,
  XCircle,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useTranslations } from "@/i18n/translations";
import type {
  CreateCollectionArgs,
  CreateScheduleArgs,
  DeleteScheduleArgs,
  DisablePluginArgs,
  EnablePluginArgs,
  InstallPluginArgs,
  ToolCall,
  UninstallPluginArgs,
  UpdateCollectionArgs,
  UpdatePluginArgs,
  UpdatePluginConfigArgs,
  UpdateScheduleArgs,
  UpdateSettingArgs,
} from "@/lib/ai-chat-types";

type ConfirmableOp = Exclude<ToolCall["op"], "replace_page" | "apply_patch" | "suggest_variables" | "navigate_to_page">;

type ActionState = "pending" | "running" | "done" | "denied";

interface AiActionConfirmationProps {
  call: ToolCall & { op: ConfirmableOp };
  onAllow: () => Promise<void> | void;
  onDeny: () => void;
  /**
   * When true and the action is not destructive, trigger the action
   * immediately on mount without requiring a user click. Used by
   * Autonomous chaining mode.
   */
  autoAllow?: boolean;
}

type TranslateFn = (key: string, params?: Record<string, unknown>) => string;

function actionLabel(call: AiActionConfirmationProps["call"], t: TranslateFn): string {
  switch (call.op) {
    case "install_plugin":
      return t("label.installPlugin", { id: (call.args as InstallPluginArgs).plugin_id });
    case "update_plugin_config":
      return t("label.updatePluginConfig", { id: (call.args as UpdatePluginConfigArgs).plugin_id });
    case "update_plugin":
      return t("label.updatePlugin", { id: (call.args as UpdatePluginArgs).plugin_id });
    case "enable_plugin":
      return t("label.enablePlugin", { id: (call.args as EnablePluginArgs).plugin_id });
    case "disable_plugin":
      return t("label.disablePlugin", { id: (call.args as DisablePluginArgs).plugin_id });
    case "uninstall_plugin":
      return t("label.uninstallPlugin", { id: (call.args as UninstallPluginArgs).plugin_id });
    case "update_setting":
      return t("label.updateSetting", { category: (call.args as UpdateSettingArgs).category });
    case "create_collection":
      return t("label.createCollection", { name: (call.args as CreateCollectionArgs).name });
    case "update_collection":
      return t("label.updateCollection");
    case "create_schedule":
      return t("label.createSchedule");
    case "update_schedule":
      return t("label.updateSchedule");
    case "delete_schedule":
      return t("label.deleteSchedule");
    case "trigger_system_update":
      return t("label.triggerSystemUpdate");
  }
}

function actionDescription(call: AiActionConfirmationProps["call"], t: TranslateFn): string {
  switch (call.op) {
    case "install_plugin": {
      const a = call.args as InstallPluginArgs;
      return a.auto_enable !== false
        ? t("description.installPluginEnable", { id: a.plugin_id })
        : t("description.installPlugin", { id: a.plugin_id });
    }
    case "update_plugin_config": {
      const a = call.args as UpdatePluginConfigArgs;
      const keys = Object.keys(a.config).join(", ");
      return t("description.updatePluginConfig", { id: a.plugin_id, keys: keys || t("noChanges") });
    }
    case "update_plugin": {
      const a = call.args as UpdatePluginArgs;
      return t("description.updatePlugin", { id: a.plugin_id });
    }
    case "enable_plugin": {
      const a = call.args as EnablePluginArgs;
      return t("description.enablePlugin", { id: a.plugin_id });
    }
    case "disable_plugin": {
      const a = call.args as DisablePluginArgs;
      return t("description.disablePlugin", { id: a.plugin_id });
    }
    case "uninstall_plugin": {
      const a = call.args as UninstallPluginArgs;
      return t("description.uninstallPlugin", { id: a.plugin_id });
    }
    case "update_setting": {
      const a = call.args as UpdateSettingArgs;
      const entries = Object.entries(a.values)
        .map(([k, v]) => `${k}: ${JSON.stringify(v)}`)
        .join(", ");
      return t("description.updateSetting", { values: entries || t("noValues"), category: a.category });
    }
    case "create_collection": {
      const a = call.args as CreateCollectionArgs;
      return t("description.createCollection", { count: a.page_ids.length, interval: a.interval_seconds });
    }
    case "update_collection": {
      const a = call.args as UpdateCollectionArgs;
      const changes: string[] = [];
      if (a.name != null) changes.push(t("change.rename", { name: a.name }));
      if (a.page_ids != null) changes.push(t("change.setPages", { count: a.page_ids.length }));
      if (a.interval_seconds != null) changes.push(t("change.interval", { interval: a.interval_seconds }));
      return changes.length ? changes.join(", ") + "." : t("noChangesSpecified");
    }
    case "create_schedule": {
      const a = call.args as CreateScheduleArgs;
      const time = `${a.start_time}${a.end_time ? `–${a.end_time}` : "+"}`;
      return t("description.createSchedule", { page: a.page_id, time, days: a.day_pattern });
    }
    case "update_schedule": {
      const a = call.args as UpdateScheduleArgs;
      const changes: string[] = [];
      if (a.page_id != null) changes.push(t("change.page", { page: a.page_id }));
      if (a.start_time != null) changes.push(t("change.start", { start: a.start_time }));
      if (a.end_time !== undefined) changes.push(t("change.end", { end: a.end_time ?? t("openEnd") }));
      if (a.day_pattern != null) changes.push(t("change.days", { days: a.day_pattern }));
      if (a.enabled != null) changes.push(a.enabled ? t("change.enable") : t("change.disable"));
      return changes.length ? changes.join(", ") + "." : t("noChangesSpecified");
    }
    case "delete_schedule":
      return t("description.deleteSchedule", { id: (call.args as DeleteScheduleArgs).schedule_id });
    case "trigger_system_update":
      return t("description.triggerSystemUpdate");
  }
}

function ActionIcon({ op }: { op: ConfirmableOp }) {
  const cls = "h-4 w-4 shrink-0 text-muted-foreground";
  switch (op) {
    case "install_plugin":
      return <Download className={cls} aria-hidden="true" />;
    case "update_plugin_config":
      return <Sliders className={cls} aria-hidden="true" />;
    case "update_plugin":
      return <RefreshCw className={cls} aria-hidden="true" />;
    case "enable_plugin":
      return <Power className={cls} aria-hidden="true" />;
    case "disable_plugin":
      return <PowerOff className={cls} aria-hidden="true" />;
    case "uninstall_plugin":
      return <Trash2 className={cls} aria-hidden="true" />;
    case "update_setting":
      return <Settings className={cls} aria-hidden="true" />;
    case "create_collection":
    case "update_collection":
      return <ListVideo className={cls} aria-hidden="true" />;
    case "create_schedule":
    case "update_schedule":
    case "delete_schedule":
      return <Calendar className={cls} aria-hidden="true" />;
    case "trigger_system_update":
      return <RefreshCw className={cls} aria-hidden="true" />;
  }
}

export function AiActionConfirmation({ call, onAllow, onDeny, autoAllow = false }: AiActionConfirmationProps) {
  const t = useTranslations("aiActionConfirmation");
  const [state, setState] = useState<ActionState>("pending");

  const handleAllow = async () => {
    setState("running");
    try {
      await onAllow();
      setState("done");
    } catch {
      setState("pending");
    }
  };

  const handleDeny = () => {
    setState("denied");
    onDeny();
  };

  const isSettled = state === "done" || state === "denied";

  const isDestructive =
    call.op === "delete_schedule" || call.op === "trigger_system_update" || call.op === "uninstall_plugin";

  // Autonomous mode: auto-fire on mount for non-destructive ops.
  const hasAutoFired = useRef(false);
  useEffect(() => {
    if (autoAllow && !isDestructive && !hasAutoFired.current) {
      hasAutoFired.current = true;
      void handleAllow();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <Card className="p-3 text-sm border-border/60 bg-muted/30">
      <div className="flex items-start gap-2">
        <ActionIcon op={call.op} />
        <div className="flex-1 min-w-0">
          <p className="font-medium leading-tight">{actionLabel(call, t)}</p>
          <p className="text-muted-foreground mt-0.5 leading-snug">{actionDescription(call, t)}</p>
        </div>
      </div>

      {!isSettled && (
        <div className="flex gap-2 mt-3 justify-end">
          <Button
            variant="outline"
            size="sm"
            onClick={handleDeny}
            disabled={state === "running"}
            className="h-7 px-3 text-xs"
          >
            {t("deny")}
          </Button>
          <Button
            size="sm"
            onClick={handleAllow}
            disabled={state === "running"}
            variant={isDestructive ? "destructive" : "default"}
            className="h-7 px-3 text-xs"
          >
            {state === "running" ? t("working") : t("allow")}
          </Button>
        </div>
      )}

      {state === "done" && (
        <div className="flex items-center gap-1.5 mt-2 text-xs text-green-600 dark:text-green-400">
          <CheckCircle className="h-3.5 w-3.5" aria-hidden="true" />
          {t("done")}
        </div>
      )}

      {state === "denied" && (
        <div className="flex items-center gap-1.5 mt-2 text-xs text-muted-foreground">
          <XCircle className="h-3.5 w-3.5" aria-hidden="true" />
          {t("denied")}
        </div>
      )}
    </Card>
  );
}
