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

function actionLabel(call: AiActionConfirmationProps["call"]): string {
  switch (call.op) {
    case "install_plugin":
      return `Install plugin: ${(call.args as InstallPluginArgs).plugin_id}`;
    case "update_plugin_config":
      return `Configure plugin: ${(call.args as UpdatePluginConfigArgs).plugin_id}`;
    case "update_plugin":
      return `Update plugin: ${(call.args as UpdatePluginArgs).plugin_id}`;
    case "enable_plugin":
      return `Enable plugin: ${(call.args as EnablePluginArgs).plugin_id}`;
    case "disable_plugin":
      return `Disable plugin: ${(call.args as DisablePluginArgs).plugin_id}`;
    case "uninstall_plugin":
      return `Uninstall plugin: ${(call.args as UninstallPluginArgs).plugin_id}`;
    case "update_setting":
      return `Change setting: ${(call.args as UpdateSettingArgs).category}`;
    case "create_collection":
      return `Create collection: "${(call.args as CreateCollectionArgs).name}"`;
    case "update_collection":
      return `Update collection`;
    case "create_schedule":
      return `Create schedule`;
    case "update_schedule":
      return `Update schedule`;
    case "delete_schedule":
      return `Delete schedule`;
    case "trigger_system_update":
      return `System update`;
  }
}

function actionDescription(call: AiActionConfirmationProps["call"]): string {
  switch (call.op) {
    case "install_plugin": {
      const a = call.args as InstallPluginArgs;
      return `Installs "${a.plugin_id}" from the official registry${a.auto_enable !== false ? " and enables it" : ""}.`;
    }
    case "update_plugin_config": {
      const a = call.args as UpdatePluginConfigArgs;
      const keys = Object.keys(a.config).join(", ");
      return `Updates configuration for "${a.plugin_id}": ${keys || "no changes"}.`;
    }
    case "update_plugin": {
      const a = call.args as UpdatePluginArgs;
      return `Downloads and installs the latest registry version of "${a.plugin_id}".`;
    }
    case "enable_plugin": {
      const a = call.args as EnablePluginArgs;
      return `Enables "${a.plugin_id}" so it can provide data to your boards.`;
    }
    case "disable_plugin": {
      const a = call.args as DisablePluginArgs;
      return `Disables "${a.plugin_id}" without removing it. It can be re-enabled later.`;
    }
    case "uninstall_plugin": {
      const a = call.args as UninstallPluginArgs;
      return `Permanently removes "${a.plugin_id}". This cannot be undone.`;
    }
    case "update_setting": {
      const a = call.args as UpdateSettingArgs;
      const entries = Object.entries(a.values)
        .map(([k, v]) => `${k}: ${JSON.stringify(v)}`)
        .join(", ");
      return `Sets ${entries || "no values"} in ${a.category} settings.`;
    }
    case "create_collection": {
      const a = call.args as CreateCollectionArgs;
      return `Creates a collection with ${a.page_ids.length} page(s), rotating every ${a.interval_seconds}s.`;
    }
    case "update_collection": {
      const a = call.args as UpdateCollectionArgs;
      const changes: string[] = [];
      if (a.name != null) changes.push(`rename to "${a.name}"`);
      if (a.page_ids != null) changes.push(`set ${a.page_ids.length} page(s)`);
      if (a.interval_seconds != null) changes.push(`interval → ${a.interval_seconds}s`);
      return changes.length ? changes.join(", ") + "." : "No changes specified.";
    }
    case "create_schedule": {
      const a = call.args as CreateScheduleArgs;
      const time = `${a.start_time}${a.end_time ? `–${a.end_time}` : "+"}`;
      return `Shows page "${a.page_id}" from ${time} on ${a.day_pattern} days.`;
    }
    case "update_schedule": {
      const a = call.args as UpdateScheduleArgs;
      const changes: string[] = [];
      if (a.page_id != null) changes.push(`page → ${a.page_id}`);
      if (a.start_time != null) changes.push(`start → ${a.start_time}`);
      if (a.end_time !== undefined) changes.push(`end → ${a.end_time ?? "open"}`);
      if (a.day_pattern != null) changes.push(`days → ${a.day_pattern}`);
      if (a.enabled != null) changes.push(a.enabled ? "enable" : "disable");
      return changes.length ? changes.join(", ") + "." : "No changes specified.";
    }
    case "delete_schedule":
      return `Permanently removes schedule "${(call.args as DeleteScheduleArgs).schedule_id}". This cannot be undone.`;
    case "trigger_system_update":
      return "Downloads and installs the latest FiestaBoard update. The system will restart briefly.";
  }
}

function ActionIcon({ op }: { op: ConfirmableOp }) {
  const cls = "h-4 w-4 shrink-0 text-muted-foreground";
  switch (op) {
    case "install_plugin":
      return <Download className={cls} />;
    case "update_plugin_config":
      return <Sliders className={cls} />;
    case "update_plugin":
      return <RefreshCw className={cls} />;
    case "enable_plugin":
      return <Power className={cls} />;
    case "disable_plugin":
      return <PowerOff className={cls} />;
    case "uninstall_plugin":
      return <Trash2 className={cls} />;
    case "update_setting":
      return <Settings className={cls} />;
    case "create_collection":
    case "update_collection":
      return <ListVideo className={cls} />;
    case "create_schedule":
    case "update_schedule":
    case "delete_schedule":
      return <Calendar className={cls} />;
    case "trigger_system_update":
      return <RefreshCw className={cls} />;
  }
}

export function AiActionConfirmation({ call, onAllow, onDeny, autoAllow = false }: AiActionConfirmationProps) {
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
          <p className="font-medium leading-tight">{actionLabel(call)}</p>
          <p className="text-muted-foreground mt-0.5 leading-snug">{actionDescription(call)}</p>
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
            Deny
          </Button>
          <Button
            size="sm"
            onClick={handleAllow}
            disabled={state === "running"}
            variant={isDestructive ? "destructive" : "default"}
            className="h-7 px-3 text-xs"
          >
            {state === "running" ? "Working…" : "Allow"}
          </Button>
        </div>
      )}

      {state === "done" && (
        <div className="flex items-center gap-1.5 mt-2 text-xs text-green-600 dark:text-green-400">
          <CheckCircle className="h-3.5 w-3.5" />
          Done
        </div>
      )}

      {state === "denied" && (
        <div className="flex items-center gap-1.5 mt-2 text-xs text-muted-foreground">
          <XCircle className="h-3.5 w-3.5" />
          Denied
        </div>
      )}
    </Card>
  );
}
