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
import { useTranslations } from "@/i18n/translations";
import type { ChainingMode } from "@/lib/ai-chat-types";

const MODE_ICONS: Record<ChainingMode, React.ComponentType<{ className?: string }>> = {
  manual: Hand,
  "auto-continue": Zap,
  autonomous: Bot,
};

const MODES: ChainingMode[] = ["manual", "auto-continue", "autonomous"];

// Maps a ChainingMode to the translation-key suffix used in messages/*.json.
const MODE_KEY: Record<ChainingMode, string> = {
  manual: "manual",
  "auto-continue": "autoContinue",
  autonomous: "autonomous",
};

interface ChainingModePickerProps {
  mode: ChainingMode;
  onChange: (mode: ChainingMode) => void;
}

export function ChainingModePicker({ mode, onChange }: ChainingModePickerProps) {
  const t = useTranslations("chainingModePicker");
  const Icon = MODE_ICONS[mode];
  const label = t(`modes.${MODE_KEY[mode]}.label`);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-7 gap-1 px-2 text-[11px] text-muted-foreground hover:text-foreground"
          aria-label={t("triggerAriaLabel", { mode: label })}
        >
          <Icon className="h-3.5 w-3.5" aria-hidden="true" />
          <span className="hidden sm:inline" aria-hidden="true">
            {label}
          </span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-60">
        <DropdownMenuLabel className="text-xs font-medium">{t("menuTitle")}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {MODES.map((key) => {
          const ItemIcon = MODE_ICONS[key];
          const isActive = key === mode;
          return (
            <DropdownMenuItem key={key} onClick={() => onChange(key)} className="flex items-start gap-2.5 py-2 text-xs">
              <ItemIcon
                aria-hidden="true"
                className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${isActive ? "text-brand-emphasis" : "text-muted-foreground"}`}
              />
              <div className="flex-1 min-w-0">
                <div className={`font-medium ${isActive ? "text-brand-emphasis" : ""}`}>
                  {t(`modes.${MODE_KEY[key]}.label`)}
                </div>
                <div className="text-muted-foreground leading-tight">{t(`modes.${MODE_KEY[key]}.description`)}</div>
              </div>
              {isActive && <div className="ml-auto mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-brand-emphasis" />}
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
