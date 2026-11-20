"use client";

import { Popover, PopoverContent, PopoverTitle, PopoverTrigger, Stack, Text } from "@fiestaboard/ui";
import { ChevronDown, MonitorCog } from "lucide-react";
import type { ReactNode } from "react";

import { useTranslations } from "@/i18n/translations";

export interface PreviewTargetPopoverProps {
  /** The target as the preview header states it: "Kitchen board · Flagship 22 × 6". */
  target: string;
  /** `meta`: the pane header's mono text with a chevron. `icon`: the phone dock's icon button. */
  variant?: "meta" | "icon";
  /** The board picker, the size picker and the board colour. */
  children: ReactNode;
}

/**
 * The preview's target, said once (BB-E-6, D3). Figma 53:137378 draws the
 * target as the preview header's mono meta and nothing else on the canvas, so
 * that meta is the one place to change it: which board the preview and mirror
 * use, the page's board size, and the preview's board colour.
 */
export function PreviewTargetPopover({ target, variant = "meta", children }: PreviewTargetPopoverProps) {
  const t = useTranslations("editorTouch");
  const label = t("previewTargetTrigger", { target });
  return (
    <Popover>
      <PopoverTrigger
        aria-label={label}
        title={label}
        data-testid="preview-target-trigger"
        className={
          variant === "icon"
            ? "inline-flex size-11 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            : "inline-flex max-w-full min-w-0 items-center gap-1 rounded-sm font-mono text-xs font-medium text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        }
      >
        {variant === "icon" ? (
          <MonitorCog aria-hidden className="size-5" />
        ) : (
          <>
            <Text as="span" className="truncate font-mono text-xs">
              {target}
            </Text>
            <ChevronDown aria-hidden className="size-3 shrink-0" />
          </>
        )}
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 max-w-[calc(100vw-24px)]" label={t("previewTarget")}>
        <Stack gap="3">
          <PopoverTitle className="text-sm font-semibold">{t("previewTarget")}</PopoverTitle>
          {children}
        </Stack>
      </PopoverContent>
    </Popover>
  );
}
