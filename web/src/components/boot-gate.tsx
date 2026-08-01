"use client";

import { FiestaLogo } from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";
import { WifiOff } from "lucide-react";
import { useEffect, useState } from "react";

import { useTranslations } from "@/i18n/translations";
import { apiUrl, appUrl } from "@/lib/base-path";

/** How long to wait before showing the splash (avoids a flash for fast startups). */
const SHOW_SPLASH_DELAY_MS = 600;

/** After this long without a connection, switch from "waiting" to the error state. */
const ERROR_TIMEOUT_MS = 30_000;

/**
 * Gates the main UI behind an API availability check on boot.
 *
 * - If the API responds within SHOW_SPLASH_DELAY_MS → no splash ever shown.
 * - If the API is still unavailable after SHOW_SPLASH_DELAY_MS → "Waiting to start…" screen.
 * - If still unavailable after ERROR_TIMEOUT_MS → error screen with a refresh button.
 * - Once the API responds for the first time → the gate is removed permanently for this session.
 *   A brief connection hiccup during normal use never re-shows the splash.
 */
export function BootGate({ children }: { children: React.ReactNode }) {
  const t = useTranslations("bootGate");
  const [hasConnected, setHasConnected] = useState(false);
  const [showSplash, setShowSplash] = useState(false);
  const [timedOut, setTimedOut] = useState(false);

  const { data } = useQuery({
    queryKey: ["boot-health"],
    // Use the unauthenticated /health endpoint so the boot splash
    // clears even on a fresh install where /status would 409 with
    // "setup required" until the admin creates the first account.
    queryFn: async () => {
      const res = await fetch(apiUrl("/health"), { credentials: "include" });
      if (!res.ok) throw new Error(`health: ${res.status}`);
      return res.json();
    },
    refetchInterval: hasConnected ? false : 2000,
    retry: false,
    staleTime: 0,
    gcTime: 0,
    enabled: !hasConnected,
  });

  // Mark connected on first successful response.
  useEffect(() => {
    if (data) setHasConnected(true);
  }, [data]);

  // Delay showing the splash so fast startups never flash it.
  useEffect(() => {
    const timer = setTimeout(() => {
      setShowSplash(true);
    }, SHOW_SPLASH_DELAY_MS);
    return () => clearTimeout(timer);
  }, []);

  // Switch to error state after the timeout elapses.
  useEffect(() => {
    const timer = setTimeout(() => {
      setTimedOut(true);
    }, ERROR_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, []);

  // API is up — show the real app.
  if (hasConnected) return <>{children}</>;

  // Still within the no-flash delay window — render nothing.
  if (!showSplash) return null;

  return (
    <div className="fixed inset-0 z-[200] flex flex-col items-center justify-center bg-background">
      <div
        className="flex flex-col items-center gap-6 text-center px-6 max-w-sm"
        role="status"
        aria-live="polite"
        aria-atomic="true"
      >
        {/* Branding */}
        <div className="flex items-center gap-3">
          <img src={appUrl("/icons/favicon-32x32.png")} alt="" width={36} height={36} className="flex-shrink-0" />
          <FiestaLogo className="text-2xl" />
        </div>

        {timedOut ? (
          /* ── Error state ── */
          <>
            <WifiOff className="h-10 w-10 text-muted-foreground" strokeWidth={1.5} aria-hidden="true" />
            <div className="space-y-1.5">
              <p className="text-base font-semibold">{t("errorHeading")}</p>
              <p className="text-sm text-muted-foreground">{t("errorDescription")}</p>
            </div>
            <button
              onClick={() => window.location.reload()}
              className="px-4 py-2 text-sm font-medium rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              {t("refreshPage")}
            </button>
          </>
        ) : (
          /* ── Waiting state ── */
          <>
            <div
              className="h-8 w-8 rounded-full border-[2.5px] border-muted-foreground/25 border-t-muted-foreground animate-spin"
              aria-hidden="true"
            />
            <p className="text-sm text-muted-foreground">{t("waiting")}</p>
          </>
        )}
      </div>
    </div>
  );
}
