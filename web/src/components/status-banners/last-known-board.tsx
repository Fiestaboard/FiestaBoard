"use client";

import { Badge, Box, Flex, Text } from "@fiestaboard/ui";
import type { ReactNode } from "react";

import { useStatus } from "@/hooks/use-board";
import { useTranslations } from "@/i18n/translations";
import { isDisplayOffline } from "@/lib/status-banners";

function timeLabel(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? null
    : date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

/**
 * A display's board preview while the hub can't reach the display (H12;
 * 07a `310:38645`): a destructive "Offline" badge with when it was last
 * connected, and the last-known board dimmed so it never reads as live.
 * Renders `children` untouched while the display is reachable or its health
 * is unknown.
 *
 * TODO(FiestaUI): the kit has no "last known" board state yet; the dim is the
 * plain opacity utility on a wrapper until a board-level prop lands (status
 * gap G4 in program/status/web-2.3.md).
 */
export function LastKnownBoard({ boardId, children }: { boardId: string; children: ReactNode }) {
  const t = useTranslations("statusBanners");
  const { data: status } = useStatus();
  const health = status?.boards?.[boardId]?.health;
  if (!isDisplayOffline(health)) return <>{children}</>;

  const time = timeLabel(health?.last_connected_at);
  return (
    <Flex direction="col" align="center" className="w-full" data-slot="last-known-board" data-state="offline">
      <Flex align="center" gap="2" wrap className="mb-3 self-start">
        <Badge variant="destructive">{t("offlineBadge")}</Badge>
        <Text as="span" size="sm" tone="muted">
          {time ? t("offlineMeta", { time }) : t("offlineMetaNever")}
        </Text>
      </Flex>
      <Box className="opacity-60" data-slot="last-known-board-preview">
        {children}
      </Box>
    </Flex>
  );
}
