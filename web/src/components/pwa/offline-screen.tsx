"use client";

import { Button, Flex, Heading, List, ListItem, Stack, Text } from "@fiestaboard/ui";
import { CircleHelp, Info, RefreshCw, Server, WifiOff } from "lucide-react";
import { useEffect, useState } from "react";

import { useTranslations } from "@/i18n/translations";
import { deviceWord, hubHost } from "@/lib/pwa/device-words";
import { type LastKnownBoard, readLastKnownBoard } from "@/lib/pwa/last-known-board";

import { LastKnownBoardCard } from "./last-known-board-card";

export const CONNECTION_HELP_URL = "https://fiestaboard.app/docs/troubleshooting#web-ui-issues";

export type OfflineScreenKind = "device-offline" | "hub-unreachable";

/**
 * The WEB-16 split as a full screen (07e §8: `329:47360` "You're offline",
 * `329:48320` "Can't reach your hub"): an icon, a title that names the thing
 * and its state, an honest body, one primary action, then the last frame this
 * device saw on a board, if it has one.
 *
 * - `device-offline` is about THIS device (`navigator.onLine` false). It says
 *   the hub and displays are fine.
 * - `hub-unreachable` is about the HUB: this device is online, the hub didn't
 *   answer. It names the address and the checks worth doing.
 *
 * TODO(FiestaUI StatusScreen): 07e draws one StatusScreen pattern for boot,
 * offline, hub unreachable, HTTPS and 404; FiestaUI has no such component
 * yet, so this composes it from kit primitives (gap G1 in status/web-2.8.md).
 */
export function OfflineScreen({ kind, onRetry }: { kind: OfflineScreenKind; onRetry: () => void }) {
  const t = useTranslations("offline");
  const [lastKnown, setLastKnown] = useState<LastKnownBoard | null>(null);

  useEffect(() => {
    let live = true;
    // Offline the account can't be checked, but the store only ever holds the
    // last signed-in account's frames and is wiped on sign out.
    void readLastKnownBoard().then((record) => {
      if (live) setLastKnown(record);
    });
    const onStorage = (event: StorageEvent) => {
      if (event.key === null || event.key.startsWith("fiestaboard-offline-revoked:")) {
        // Invalidate pending reads as well as the visible frame immediately.
        live = false;
        setLastKnown(null);
      }
    };
    window.addEventListener("storage", onStorage);
    return () => {
      live = false;
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  const device = t(`device.${deviceWord()}`);
  const host = hubHost();
  const offline = kind === "device-offline";
  const Icon = offline ? WifiOff : Server;

  return (
    <Flex
      direction="col"
      align="center"
      className="min-h-[60vh] w-full px-4 py-12"
      data-testid="offline-screen"
      data-kind={kind}
    >
      <Stack gap="4" align="center" className="w-full max-w-md text-center">
        <Icon className="size-8 text-muted-foreground" strokeWidth={1.5} aria-hidden="true" />
        <Heading level={1} size="xl">
          {offline ? t("youreOffline") : t("cantReachHub")}
        </Heading>
        <Text tone="muted" className="leading-5">
          {offline ? t("offlineBody", { device, host }) : t("cantReachBody", { device, host })}
        </Text>
        {!offline && (
          <List gap="1" className="w-full text-left">
            {(["checkPower", "checkWifi"] as const).map((key) => (
              <ListItem key={key}>
                <Flex align="center" gap="2">
                  <Info className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                  <Text as="span">{t(key)}</Text>
                </Flex>
              </ListItem>
            ))}
          </List>
        )}
        <Flex gap="2" wrap justify="center">
          <Button onClick={onRetry}>
            <RefreshCw aria-hidden="true" />
            {t("tryAgain")}
          </Button>
          {!offline && (
            <Button variant="outline" asChild>
              {/* eslint-disable-next-line react/forbid-elements -- single Slot child of Button asChild; the Button merges its chrome onto this anchor and TextLink would layer conflicting link styling */}
              <a href={CONNECTION_HELP_URL} target="_blank" rel="noreferrer">
                <CircleHelp aria-hidden="true" />
                {t("connectionHelp")}
              </a>
            </Button>
          )}
        </Flex>
      </Stack>
      {lastKnown && (
        <Stack gap="2" className="mt-10 w-full max-w-2xl">
          <LastKnownBoardCard record={lastKnown} />
        </Stack>
      )}
    </Flex>
  );
}
