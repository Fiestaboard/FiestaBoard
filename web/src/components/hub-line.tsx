"use client";

import { type BoardSelectorHubStatus, Flex, StatusDot, Text } from "@fiestaboard/ui";
import { type RefObject, useEffect, useRef, useState } from "react";

import { useHubLine } from "@/hooks/use-hub-connection";
import type { HubIdentity } from "@/hooks/use-hub-identity";
import { useTranslations } from "@/i18n/translations";
import { cn } from "@/lib/utils";

/** The dot for each state, as the BoardSelector draws it (07a `302:2146`). */
const DOT: Record<BoardSelectorHubStatus, "success" | "info" | "danger"> = {
  online: "success",
  remote: "info",
  unreachable: "danger",
};

/**
 * Whether the element is outside any `aria-hidden="true"` ancestor (a closed
 * drawer), following that ancestor as it opens and closes.
 */
function useNotHidden(ref: RefObject<HTMLElement | null>): boolean {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const host = ref.current?.parentElement?.closest<HTMLElement>("[aria-hidden]") ?? null;
    const read = () => setShown(!host || host.getAttribute("aria-hidden") !== "true");
    read();
    if (!host) return;
    const observer = new MutationObserver(read);
    observer.observe(host, { attributes: true, attributeFilter: ["aria-hidden"] });
    return () => observer.disconnect();
  }, [ref]);
  return shown;
}

/**
 * "fiestapi.local · Online · FiestaBoard 11.1.0" with a status dot (07a More
 * sheet `308:36070` foot, 07e Settings hub card). The host and state come
 * from `useHubLine`, the one source the BoardSelector line and phone pill use
 * too (slice 2.3), so the two can never disagree. The dot never stands alone:
 * the state is in the words too (WCAG 1.4.1), and no dot is drawn until the
 * state is known.
 */
export function HubLine({ hub, className }: { hub: HubIdentity; className?: string }) {
  const t = useTranslations("statusBanners");
  const ref = useRef<HTMLDivElement>(null);
  // The More drawer stays mounted while closed (aria-hidden). Poll the hub
  // only while the line can be seen, so a closed drawer adds no request.
  const shown = useNotHidden(ref);
  const { host, status } = useHubLine({ enabled: shown });
  const words: Record<BoardSelectorHubStatus, string> = {
    online: t("hubOnline"),
    remote: t("hubRemote"),
    unreachable: t("hubUnreachable"),
  };
  const parts = [host, status ? words[status] : null, hub.version ? t("hubVersion", { version: hub.version }) : null];

  return (
    <Flex
      ref={ref}
      align="center"
      gap="1.5"
      className={cn("min-w-0", className)}
      data-slot="hub-line"
      data-status={status}
    >
      {status && <StatusDot status={DOT[status]} size="md" className="shrink-0" aria-hidden="true" />}
      <Text size="xs" tone="muted" className="min-w-0 truncate">
        {parts.filter(Boolean).join(" · ")}
      </Text>
    </Flex>
  );
}
