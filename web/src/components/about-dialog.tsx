"use client";

/**
 * About FiestaBoard (07e: dialog `343:63073`, phone sheet `343:64171`).
 *
 * Which build this page is, which hub it talks to and on what release
 * channel, and the update waiting, if any. A centred dialog from the rail up;
 * a bottom sheet on a phone, like the app's other phone overlays.
 *
 * Every fact is read from a real endpoint (`/version`, `/system/channel`,
 * `/system/update-check`, settings) or from this build. Rows whose value the
 * server does not know are omitted rather than rendered as "Unknown".
 */

import {
  Badge,
  Box,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  Flex,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  Stack,
  Text,
  TextLink,
} from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";

import Link from "@/components/smart-link";
import { useAvailableUpdate } from "@/hooks/use-available-update";
import { useBelowRail } from "@/hooks/use-below-rail";
import { useHubIdentity } from "@/hooks/use-hub-identity";
import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";
import type { ReleaseChannel } from "@/lib/api/system";

import { version as WEB_VERSION } from "../../package.json";

const REPO_URL = "https://github.com/Fiestaboard/FiestaBoard";
const LINKS = [
  { key: "releaseNotes", href: `${REPO_URL}/releases` },
  { key: "licenses", href: `${REPO_URL}/blob/main/LICENSE` },
  { key: "reportProblem", href: `${REPO_URL}/issues/new/choose` },
] as const;
const CHANNEL_LABELS: Record<ReleaseChannel, string> = {
  stable: "channelStable",
  beta: "channelBeta",
  alpha: "channelAlpha",
};

interface AboutDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AboutDialog({ open, onOpenChange }: AboutDialogProps) {
  const t = useTranslations("aboutDialog");
  const tMenu = useTranslations("settingsMenu");
  const tChannel = useTranslations("releaseChannel");
  const tCommon = useTranslations("common");
  const belowRail = useBelowRail();

  // Shared cache keys, so opening the box usually costs no requests at all.
  const hub = useHubIdentity({ enabled: open });
  const updateVersion = useAvailableUpdate({ enabled: open });
  const { data: channel } = useQuery({
    queryKey: ["system", "channel"],
    queryFn: () => api.getReleaseChannel(),
    staleTime: 60_000,
    retry: false,
    enabled: open,
  });

  const running = channel?.running_channel ?? channel?.channel;
  const facts = [
    { key: "thisPage", label: t("thisPage"), value: t("webVersion", { version: WEB_VERSION }) },
    {
      key: "hub",
      label: t("hub"),
      value: [hub.name, hub.version && t("hubVersion", { version: hub.version }), hub.host].filter(Boolean).join(" · "),
    },
    running && CHANNEL_LABELS[running]
      ? { key: "channel", label: tChannel("title"), value: tChannel(CHANNEL_LABELS[running]) }
      : null,
  ].filter((fact) => fact !== null);

  const updateLink = (
    <Button asChild variant={belowRail ? "default" : "outline"} className={belowRail ? "w-full" : undefined}>
      <Link href="/settings/system" onClick={() => onOpenChange(false)}>
        {t("updateInSettings")}
      </Link>
    </Button>
  );

  const body = (
    <Stack gap="4">
      <dl className="rounded-lg bg-muted px-4 py-3">
        {facts.map((fact) => (
          <Flex key={fact.key} direction={belowRail ? "col" : "row"} gap={belowRail ? "0.5" : "4"} className="py-1.5">
            <dt className="shrink-0 text-sm text-muted-foreground sm:w-32">{fact.label}</dt>
            <dd className="min-w-0 text-sm">{fact.value}</dd>
          </Flex>
        ))}
      </dl>
      {updateVersion && (
        <Flex align="center" gap="3" wrap className="rounded-lg border border-brand px-3 py-2.5">
          <Badge variant="brand">{tMenu("updateAvailable")}</Badge>
          <Text size="sm" className="min-w-0 flex-1">
            {t("hubVersion", { version: updateVersion })}
          </Text>
          {!belowRail && updateLink}
        </Flex>
      )}
      {!belowRail && (
        <Flex gap="4" wrap>
          {LINKS.map((link) => (
            <TextLink key={link.key} href={link.href} target="_blank" rel="noopener noreferrer" className="text-sm">
              {t(link.key)}
            </TextLink>
          ))}
        </Flex>
      )}
    </Stack>
  );

  if (belowRail) {
    return (
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent side="bottom" grabber labels={{ close: tCommon("close") }}>
          <SheetHeader>
            <SheetTitle>{tMenu("about")}</SheetTitle>
            <SheetDescription>{t("description")}</SheetDescription>
          </SheetHeader>
          {body}
          {/* The kit's footer stacks bottom-up: the primary action, listed
              last, sits on top as in 343:64171. */}
          <SheetFooter>
            <Button variant="outline" className="w-full" onClick={() => onOpenChange(false)}>
              {tCommon("close")}
            </Button>
            {updateVersion && updateLink}
          </SheetFooter>
        </SheetContent>
      </Sheet>
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* 07e "Web / Dialog shell · Desktop" (BB-FS-6): 560 wide, 14px corners,
          the raised surface and the 40px close — the kit's wide shell. */}
      <DialogContent variant="wide" labels={{ close: tCommon("close") }}>
        <DialogHeader>
          <DialogTitle>{tMenu("about")}</DialogTitle>
          <DialogDescription>{t("description")}</DialogDescription>
        </DialogHeader>
        {body}
        <Box>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {tCommon("close")}
          </Button>
        </Box>
      </DialogContent>
    </Dialog>
  );
}
