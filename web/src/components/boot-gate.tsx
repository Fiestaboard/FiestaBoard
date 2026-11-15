"use client";

import { Button, FiestaIcon, FiestaLogo, Flex, Stack, Text } from "@fiestaboard/ui";
import { Spinner } from "@fiestaboard/ui/components/feedback/spinner";
import { useQuery } from "@tanstack/react-query";
import { WifiOff } from "lucide-react";
import { useEffect, useState } from "react";

import { OfflineScreen } from "@/components/pwa/offline-screen";
import { useUpdate } from "@/components/update-context";
import { useDepsChanged } from "@/hooks/use-deps-changed";
import { useOnline } from "@/hooks/use-online";
import { useTranslations } from "@/i18n/translations";
import { apiUrl } from "@/lib/base-path";

/** How long to wait before showing the splash (avoids a flash for fast startups). */
const SHOW_SPLASH_DELAY_MS = 600;

/** After this long without a connection, switch from "waiting" to the error state. */
const ERROR_TIMEOUT_MS = 30_000;

/**
 * Restarting after an update legitimately takes longer than a cold boot — the
 * new container has to start from scratch on hardware that was just busy
 * pulling an image. Showing "Couldn't connect to FiestaBoard" at 30 s there
 * reads as a failure when the machine is simply still coming up.
 */
const POST_UPDATE_ERROR_TIMEOUT_MS = 120_000;

/**
 * Gates the main UI behind an API availability check on boot.
 *
 * - If the API responds within SHOW_SPLASH_DELAY_MS → no splash ever shown.
 * - If the API is still unavailable after SHOW_SPLASH_DELAY_MS → "Waiting to start…" screen.
 * - If still unavailable after the error timeout → error screen with a refresh button.
 * - Once the API responds for the first time → the gate is removed permanently for this session.
 *   A brief connection hiccup during normal use never re-shows the splash.
 *
 * When the page has just reloaded itself to finish an update (see
 * `UpdateProvider`), the same states get update-specific copy and a longer
 * error timeout, so a normal post-update restart doesn't look like a crash.
 */
export function BootGate({ children }: { children: React.ReactNode }) {
  const t = useTranslations("bootGate");
  const { awaitingPostUpdateBoot, markPostUpdateBootComplete } = useUpdate();
  const [hasConnected, setHasConnected] = useState(false);
  const [showSplash, setShowSplash] = useState(false);
  const [timedOut, setTimedOut] = useState(false);
  const online = useOnline();

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

  // Mark connected on first successful response. Done during render so the
  // splash clears in the same commit the health check lands
  // (react-hooks/set-state-in-effect, issue #1568).
  if (useDepsChanged([data]) && data) {
    setHasConnected(true);
  }

  // Retiring the post-update marker touches the UpdateProvider's state, which
  // is a different component — that has to stay in an effect.
  useEffect(() => {
    if (!data) return;
    markPostUpdateBootComplete();
  }, [data, markPostUpdateBootComplete]);

  // Delay showing the splash so fast startups never flash it.
  useEffect(() => {
    const timer = setTimeout(() => {
      setShowSplash(true);
    }, SHOW_SPLASH_DELAY_MS);
    return () => clearTimeout(timer);
  }, []);

  // Switch to error state after the timeout elapses.
  useEffect(() => {
    const timer = setTimeout(
      () => {
        setTimedOut(true);
      },
      awaitingPostUpdateBoot ? POST_UPDATE_ERROR_TIMEOUT_MS : ERROR_TIMEOUT_MS,
    );
    return () => clearTimeout(timer);
  }, [awaitingPostUpdateBoot]);

  // API is up — show the real app.
  if (hasConnected) return <>{children}</>;

  // This device has no network (the app opened from the service worker's
  // shell, or the network dropped before the first answer). Say so at once
  // instead of "Waiting to start…": it is this device, not the hub (WEB-16).
  // After an ordinary cold-boot timeout, name the unreachable hub and retain
  // the last-known board. Updates keep their longer, update-specific flow.
  if (!online || (timedOut && !awaitingPostUpdateBoot)) {
    return (
      <Flex role="main" direction="col" className="fixed inset-0 z-[200] overflow-y-auto bg-background">
        <OfflineScreen
          kind={online ? "hub-unreachable" : "device-offline"}
          onRetry={() => {
            if (navigator.onLine) window.location.reload();
          }}
        />
      </Flex>
    );
  }

  // Still within the no-flash delay window — render nothing.
  if (!showSplash) return null;

  return (
    <Flex direction="col" align="center" justify="center" className="fixed inset-0 z-[200] bg-background">
      <Flex
        direction="col"
        align="center"
        gap="6"
        className="text-center px-6 max-w-sm"
        role="status"
        aria-live="polite"
        aria-atomic="true"
      >
        {/* Branding */}
        <Flex align="center" gap="3">
          {timedOut && <FiestaIcon size={36} className="flex-shrink-0" />}
          <FiestaLogo className="text-2xl" />
        </Flex>

        {timedOut ? (
          /* ── Error state ── */
          <>
            <WifiOff className="h-10 w-10 text-muted-foreground" strokeWidth={1.5} aria-hidden="true" />
            <Stack gap="1.5">
              <Text size="base" weight="semibold">
                {awaitingPostUpdateBoot ? t("updateErrorHeading") : t("errorHeading")}
              </Text>
              <Text tone="muted">{awaitingPostUpdateBoot ? t("updateErrorDescription") : t("errorDescription")}</Text>
            </Stack>
            <Button onClick={() => window.location.reload()}>{t("refreshPage")}</Button>
          </>
        ) : (
          /* ── Waiting state ── */
          <>
            <Spinner size="lg" className="size-20" label={null} />
            {awaitingPostUpdateBoot ? (
              <Stack gap="1.5">
                <Text size="base" weight="semibold">
                  {t("updateWaiting")}
                </Text>
                <Text tone="muted">{t("updateWaitingDescription")}</Text>
              </Stack>
            ) : (
              <Text tone="muted">{t("waiting")}</Text>
            )}
          </>
        )}
      </Flex>
    </Flex>
  );
}
