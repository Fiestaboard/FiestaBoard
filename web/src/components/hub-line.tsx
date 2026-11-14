"use client";

import { Flex, StatusDot, Text } from "@fiestaboard/ui";

import type { HubIdentity } from "@/hooks/use-hub-identity";
import { useTranslations } from "@/i18n/translations";
import { cn } from "@/lib/utils";

/**
 * "fiestapi.local · Online · FiestaBoard 11.1.0" with a status dot (07a More
 * sheet `308:36070` foot, 07e Settings hub card). The dot never stands alone:
 * the state is in the words too (WCAG 1.4.1), and no dot is drawn until the
 * state is known.
 */
export function HubLine({ hub, className }: { hub: HubIdentity; className?: string }) {
  const t = useTranslations("navigation.hub");
  const parts = [hub.host];
  if (hub.online === true) parts.push(t("online"));
  if (hub.online === false) parts.push(t("unreachable"));
  if (hub.version) parts.push(t("version", { version: hub.version }));

  return (
    <Flex align="center" gap="1.5" className={cn("min-w-0", className)} data-slot="hub-line">
      {hub.online !== null && (
        <StatusDot status={hub.online ? "success" : "danger"} size="md" className="shrink-0" aria-hidden="true" />
      )}
      <Text size="xs" tone="muted" className="min-w-0 truncate">
        {parts.filter(Boolean).join(" · ")}
      </Text>
    </Flex>
  );
}
