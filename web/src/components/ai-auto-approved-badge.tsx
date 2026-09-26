"use client";

import { Badge, Text, Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@fiestaboard/ui";

import { useTranslations } from "@/i18n/translations";

const BADGE_CLASS = "px-1 py-0 text-[10px] uppercase tracking-wide";

/**
 * "auto": a destructive call that ran without a pause — the install is in
 * Auto, or the user chose "don't ask again" for this chat.
 *
 * Two renderings, because the badge sits in two places:
 * - `interactive` (the live step timeline): a real button trigger with the
 *   explanation as a tooltip, so it opens from the keyboard too.
 * - plain (a tool-call card's header): the header is already one button —
 *   the collapsible trigger — so no control may nest inside it; the
 *   explanation rides along as visually hidden text instead.
 */
export function AiAutoApprovedBadge({ interactive = true }: { interactive?: boolean }) {
  const t = useTranslations("aiChatPanel");
  const label = t("autoApproved.badge");
  const explanation = t("autoApproved.tooltip");

  if (!interactive) {
    return (
      <Badge variant="outline" className={`ml-1.5 ${BADGE_CLASS}`} data-testid="ai-auto-approved-badge">
        {label}
        <Text as="span" className="sr-only">
          : {explanation}
        </Text>
      </Badge>
    );
  }

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger className="ml-1.5 inline-flex rounded-full align-middle" data-testid="ai-auto-approved-badge">
          <Badge variant="outline" className={BADGE_CLASS}>
            {label}
          </Badge>
        </TooltipTrigger>
        <TooltipContent>{explanation}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
