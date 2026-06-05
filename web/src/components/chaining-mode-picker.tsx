"use client";

/**
 * Compact mode selector for AI tool-call chaining.
 *
 * Renders a small icon+label button that opens a dropdown with three modes:
 *  • Manual        — no auto-chaining (current behaviour)
 *  • Auto-continue — chain after each user-confirmed Allow
 *  • Autonomous    — skip confirmations for non-destructive ops, up to 15 steps
 *
 * The selected mode is controlled externally; the parent is responsible for
 * persisting it to `localStorage["fiestaboard:ai-chaining-mode"]`.
 */

import { Bot, Hand, Zap } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { ChainingMode } from "@/lib/ai-chat-types";

interface ModeConfig {
  label: string;
  Icon: React.ComponentType<{ className?: string }>;
  description: string;
}

const MODE_CONFIG: Record<ChainingMode, ModeConfig> = {
  manual: {
    label: "Manual",
    Icon: Hand,
    description: "I'll re-prompt after each action",
  },
  "auto-continue": {
    label: "Auto-continue",
    Icon: Zap,
    description: "Chain actions, confirm each step",
  },
  autonomous: {
    label: "Autonomous",
    Icon: Bot,
    description: "Run to completion, skip confirmations",
  },
};

const MODES: ChainingMode[] = ["manual", "auto-continue", "autonomous"];

interface ChainingModePickerProps {
  mode: ChainingMode;
  onChange: (mode: ChainingMode) => void;
}

export function ChainingModePicker({ mode, onChange }: ChainingModePickerProps) {
  const { label, Icon, description } = MODE_CONFIG[mode];

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-7 gap-1 px-2 text-[11px] text-muted-foreground hover:text-foreground"
          title={`AI mode: ${label} — ${description}`}
        >
          <Icon className="h-3.5 w-3.5" />
          <span className="hidden sm:inline">{label}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-60">
        <DropdownMenuLabel className="text-xs font-medium">AI chaining mode</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {MODES.map((key) => {
          const cfg = MODE_CONFIG[key];
          const ItemIcon = cfg.Icon;
          const isActive = key === mode;
          return (
            <DropdownMenuItem key={key} onClick={() => onChange(key)} className="flex items-start gap-2.5 py-2 text-xs">
              <ItemIcon
                className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${isActive ? "text-brand-emphasis" : "text-muted-foreground"}`}
              />
              <div className="flex-1 min-w-0">
                <div className={`font-medium ${isActive ? "text-brand-emphasis" : ""}`}>{cfg.label}</div>
                <div className="text-muted-foreground leading-tight">{cfg.description}</div>
              </div>
              {isActive && <div className="ml-auto mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-brand-emphasis" />}
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
