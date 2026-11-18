// Preview header controls (04c C3 / 07c H6): Inspect, Live · Sample · Missing,
// and the render-at clock.

"use client";

import { Button, type DataSource, DataSourceSwitch, Flex, Toggle } from "@fiestaboard/ui";
import { Clock, ScanSearch, X } from "lucide-react";

import { TimePicker } from "@/components/ui/time-picker";
import { useTranslations } from "@/i18n/translations";

export interface PreviewDataControlsProps {
  mode: DataSource;
  onModeChange: (mode: DataSource) => void;
  /** `HH:MM`, or "" for now. */
  atTime: string;
  onAtTimeChange: (value: string) => void;
  size: "default" | "touch";
  /** Desktop only: Inspect on/off. */
  inspect?: boolean;
  onInspectChange?: (inspect: boolean) => void;
}

export function PreviewDataControls({
  mode,
  onModeChange,
  atTime,
  onAtTimeChange,
  size,
  inspect,
  onInspectChange,
}: PreviewDataControlsProps) {
  const t = useTranslations("formulaIde");
  return (
    <Flex align="center" gap="2" wrap data-testid="preview-data-controls">
      {onInspectChange && (
        <Toggle
          variant="outline"
          size="sm"
          pressed={inspect ?? false}
          onPressedChange={onInspectChange}
          aria-keyshortcuts="I"
          data-testid="inspect-toggle"
        >
          <ScanSearch aria-hidden />
          {t("inspect")}
        </Toggle>
      )}
      <DataSourceSwitch
        aria-label={t("dataSourceLabel")}
        value={mode}
        onValueChange={onModeChange}
        size={size}
        options={[
          { value: "live", label: t("live") },
          { value: "sample", label: t("sample") },
          { value: "missing", label: t("missing") },
        ]}
      />
      <Flex align="center" gap="1">
        <Clock aria-hidden className="size-4 text-muted-foreground" />
        <TimePicker value={atTime} onChange={onAtTimeChange} placeholder={t("atNow")} aria-label={t("renderAtLabel")} />
        {atTime && (
          <Button
            variant="ghost"
            size={size === "touch" ? "icon-touch" : "icon-sm"}
            aria-label={t("renderAtReset")}
            onClick={() => onAtTimeChange("")}
          >
            <X aria-hidden />
          </Button>
        )}
      </Flex>
    </Flex>
  );
}
