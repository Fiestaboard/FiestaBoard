"use client";

import { Alert, AlertDescription, AlertTitle, Box, Flex, Text } from "@fiestaboard/ui";
import { Moon } from "lucide-react";
import type { ReactNode } from "react";

import { useTranslations } from "@/i18n/translations";
import { cn } from "@/lib/utils";

export interface SilenceNoticeProps {
  /** When silence ends, already formatted ("7:00 AM"); null when unknown. */
  until: string | null;
  /** False renders nothing — the board is not silenced. */
  active?: boolean;
  /** `info` for "this is what will happen", `warning` for "this wakes the board". */
  variant?: "info" | "warning";
  /** The surface's own sentence: what happens to the thing you are doing. */
  description: ReactNode;
  /** An optional action row (Show now, Discard message, …). */
  children?: ReactNode;
  /** One line, extra-small text — for tight spots like the page builder's live strip. */
  compact?: boolean;
  className?: string;
  "data-testid"?: string;
}

/**
 * The one way the app says "this board is silenced" (#1943).
 *
 * Home, the Change Page sheet, Force Set, Compose and the page builder's Live
 * Output all render this, so the title ("Silenced until 7:00 AM"), the icon
 * and the layout are identical and only the sentence differs: each surface
 * says what silence means for the action in front of you.
 *
 * Desktop: actions sit to the right of the text. Phone: they wrap into a
 * full-width row under it, at a 44 px touch height.
 */
export function SilenceNotice({
  until,
  active = true,
  variant = "info",
  description,
  children,
  compact = false,
  className,
  "data-testid": testId,
}: SilenceNoticeProps) {
  const t = useTranslations("silenceNotice");
  if (!active) return null;

  const title = until ? t("untilTitle", { time: until }) : t("untilTitleNoTime");
  const tone = variant === "warning" ? "border-warning/50 bg-warning/10" : "border-info/50 bg-info/10";
  const iconTone = variant === "warning" ? "text-warning" : "text-info";

  return (
    <Alert
      variant={variant}
      politeness="polite"
      data-testid={testId}
      data-variant={variant}
      className={cn(
        tone,
        "flex min-w-0 flex-col gap-3 [overflow-wrap:anywhere] sm:flex-row sm:items-center sm:gap-4",
        compact && "px-3 py-2",
        className,
      )}
    >
      <Flex align="start" gap="3" className="min-w-0 flex-1">
        <Moon className={cn("mt-0.5 h-4 w-4 shrink-0", iconTone)} aria-hidden="true" />
        {compact ? (
          <Text size="xs" className="min-w-0">
            <Text as="span" size="xs" weight="semibold">
              {title}
            </Text>
            {" — "}
            {description}
          </Text>
        ) : (
          <Box className="min-w-0">
            <AlertTitle>{title}</AlertTitle>
            <AlertDescription className="text-sm">{description}</AlertDescription>
          </Box>
        )}
      </Flex>
      {children ? (
        <Flex
          gap="2"
          className="w-full flex-col sm:w-auto sm:shrink-0 sm:flex-row sm:items-center [&>*]:min-h-11 sm:[&>*]:min-h-0"
        >
          {children}
        </Flex>
      ) : null}
    </Alert>
  );
}

/** Pause always wins, including a confirmed silence override. */
export function PausedNotice({ "data-testid": testId }: { "data-testid"?: string }) {
  const t = useTranslations("displaySettings.pause");
  return (
    <Alert variant="warning" politeness="polite" data-testid={testId}>
      <AlertTitle>{t("badge")}</AlertTitle>
      <AlertDescription>{t("tooltip")}</AlertDescription>
    </Alert>
  );
}
