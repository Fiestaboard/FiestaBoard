import { Box, Flex, List, ListItem, Stack, Text } from "@fiestaboard/ui";
import { RefreshCw, WifiOff } from "lucide-react";
import { useEffect, useState } from "react";

import { useTranslations } from "@/i18n/translations";

export default function OfflinePage() {
  const [isOnline, setIsOnline] = useState(false);
  const t = useTranslations("offline");

  useEffect(() => {
    // Check initial online status
    setIsOnline(navigator.onLine);

    // Listen for online/offline events
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);

    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);

    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);

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
