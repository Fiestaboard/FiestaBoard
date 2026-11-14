import { Flex } from "@fiestaboard/ui";
import { Spinner } from "@fiestaboard/ui/components/feedback/spinner";
import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";

import { OfflineScreen } from "@/components/pwa/offline-screen";
import { useOnline } from "@/hooks/use-online";
import { useRouter } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";
import { apiUrl } from "@/lib/base-path";

/**
 * `/offline` (WEB-16 split): "You're offline" when this device has no
 * network, "Can't reach your hub" when it does but the hub doesn't answer,
 * and straight back to Home once the hub answers.
 */
export default function OfflinePage() {
  const online = useOnline();
  const router = useRouter();
  const t = useTranslations("offline");

  const health = useQuery({
    queryKey: ["offline-health"],
    queryFn: async () => {
      const res = await fetch(apiUrl("/health"), { credentials: "include", cache: "no-store" });
      if (!res.ok) throw new Error(`health: ${res.status}`);
      return true;
    },
    enabled: online,
    retry: false,
    gcTime: 0,
    refetchInterval: (query) => (query.state.status === "error" ? 15_000 : false),
  });

  const reachable = online && health.isSuccess;
  useEffect(() => {
    if (reachable) router.replace("/");
  }, [reachable, router]);

  if (!online) {
    return (
      <OfflineScreen
        kind="device-offline"
        onRetry={() => {
          if (navigator.onLine) window.location.reload();
        }}
      />
    );
  }

  if (health.isError) {
    return <OfflineScreen kind="hub-unreachable" onRetry={() => void health.refetch()} />;
  }

  return (
    <Flex align="center" justify="center" className="min-h-[60vh]">
      <Spinner size="lg" className="size-8 text-primary" label={t("reconnecting")} />
    </Flex>
  );
}
