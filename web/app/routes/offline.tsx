import { Box, Flex, List, ListItem, Stack, Text } from "@fiestaboard/ui";
import { RefreshCw, WifiOff } from "lucide-react";
import { useEffect, useSyncExternalStore } from "react";

import { useTranslations } from "@/i18n/translations";

/** `navigator.onLine` is an external store — subscribe to it as one. */
function subscribeToOnlineStatus(onChange: () => void) {
  window.addEventListener("online", onChange);
  window.addEventListener("offline", onChange);
  return () => {
    window.removeEventListener("online", onChange);
    window.removeEventListener("offline", onChange);
  };
}

export default function OfflinePage() {
  // Was a mount effect that called setIsOnline(navigator.onLine), i.e. always
  // one render of "offline" before the truth arrived
  // (react-hooks/set-state-in-effect, issue #1568).
  const isOnline = useSyncExternalStore(
    subscribeToOnlineStatus,
    () => navigator.onLine,
    () => false,
  );
  const t = useTranslations("offline");

  const handleRetry = () => {
    if (navigator.onLine) {
      window.location.reload();
    }
  };

  useEffect(() => {
    // Auto-reload when back online
    if (isOnline) {
      setTimeout(() => {
        window.location.reload();
      }, 1000);
    }
  }, [isOnline]);

  return (
    <Flex align="center" justify="center" className="min-h-screen bg-background p-4">
      <Stack gap="6" className="max-w-md w-full text-center">
        <Flex justify="center">
          <Box className="rounded-full bg-muted p-6">
            <WifiOff className="h-12 w-12 text-muted-foreground" />
          </Box>
        </Flex>

        <Stack gap="2">
          {/* Reserved for PageHeader elsewhere; this standalone offline splash has no icon/description
              card to match, so the h1 stays raw here (couldn't snap — see wave 1 report). */}
          {/* eslint-disable-next-line react/forbid-elements -- standalone offline-splash hero title; PageHeader's icon+card shape doesn't fit and Heading has no level=1 */}
          <h1 className="text-3xl font-bold tracking-tight">{isOnline ? t("reconnecting") : t("youreOffline")}</h1>
          <Text tone="muted">{isOnline ? t("connectionRestored") : t("offlineDescription")}</Text>
        </Stack>

        {!isOnline && (
          <Stack gap="4">
            <button
              onClick={handleRetry}
              className="inline-flex items-center justify-center gap-2 rounded-md bg-primary px-6 py-3 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              <RefreshCw className="h-4 w-4" />
              {t("tryAgain")}
            </button>

            <Box className="text-sm text-muted-foreground">
              <Text tone="muted">{t("whileOffline")}</Text>
              <List gap="1" className="mt-2">
                <ListItem>• {t("viewPreviouslyLoaded")}</ListItem>
                <ListItem>• {t("accessCached")}</ListItem>
                <ListItem>• {t("browseSaved")}</ListItem>
              </List>
            </Box>
          </Stack>
        )}

        {isOnline && (
          <Flex justify="center">
            <Box className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></Box>
          </Flex>
        )}
      </Stack>
    </Flex>
  );
}
