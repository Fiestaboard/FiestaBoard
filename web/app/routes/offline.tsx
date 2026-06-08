import { RefreshCw, WifiOff } from "lucide-react";
import { useTranslations } from "@/i18n/translations";
import { useEffect, useState } from "react";

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
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <div className="max-w-md w-full text-center space-y-6">
        <div className="flex justify-center">
          <div className="rounded-full bg-muted p-6">
            <WifiOff className="h-12 w-12 text-muted-foreground" />
          </div>
        </div>

        <div className="space-y-2">
          <h1 className="text-3xl font-bold tracking-tight">{isOnline ? t("reconnecting") : t("youreOffline")}</h1>
          <p className="text-muted-foreground">{isOnline ? t("connectionRestored") : t("offlineDescription")}</p>
        </div>

        {!isOnline && (
          <div className="space-y-4">
            <button
              onClick={handleRetry}
              className="inline-flex items-center justify-center gap-2 rounded-md bg-primary px-6 py-3 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              <RefreshCw className="h-4 w-4" />
              {t("tryAgain")}
            </button>

            <div className="text-sm text-muted-foreground">
              <p>{t("whileOffline")}</p>
              <ul className="mt-2 space-y-1">
                <li>• {t("viewPreviouslyLoaded")}</li>
                <li>• {t("accessCached")}</li>
                <li>• {t("browseSaved")}</li>
              </ul>
            </div>
          </div>
        )}

        {isOnline && (
          <div className="flex justify-center">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
          </div>
        )}
      </div>
    </div>
  );
}
