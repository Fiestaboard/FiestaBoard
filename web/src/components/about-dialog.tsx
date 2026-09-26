"use client";

/**
 * The About box, in the tradition that invented them: one centred column,
 * the mark large and proud at the top, a quiet block of facts beneath it,
 * the licence last. No cards, no grid, no accent colour — the taco is the
 * only loud thing in here and everything else gets out of its way.
 *
 * Every fact is read from a real endpoint (`/version`,
 * `/system/update/status`, `/system/channel`) or from board settings the app
 * already holds. Rows whose value the server does not know are omitted
 * rather than rendered as "Unknown": an About box that pads itself out to
 * look substantial is worse than a short one that is entirely true.
 */

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  FiestaIcon,
  FiestaLogo,
  Flex,
  Stack,
  Text,
  TextLink,
} from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";

import { useCurrentBoard } from "@/components/current-board-context";
import { useTranslations } from "@/i18n/translations";
import type { AutoUpdateInterval, UpdateStatusResponse } from "@/lib/api";
import { api } from "@/lib/api";
import { resolveDimensions } from "@/lib/board-dimensions";

/**
 * Straight from the repo's LICENSE file — not from memory, and not from a
 * `new Date().getFullYear()` that would silently relicense the project every
 * January. If LICENSE changes, change these.
 */
const LICENSE_HOLDER = "Fiestaboard contributors";
const LICENSE_YEAR = "2026";
const REPO_URL = "https://github.com/Fiestaboard/FiestaBoard";

interface AboutDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AboutDialog({ open, onOpenChange }: AboutDialogProps) {
  const t = useTranslations("aboutDialog");
  const { currentBoard } = useCurrentBoard();

  // All three are shared cache keys, so opening the box usually costs no
  // requests at all — something else has already asked. `enabled: open`
  // keeps a box nobody opens from ever being a reason to hit the API.
  const { data: version } = useQuery({
    queryKey: ["version"],
    queryFn: () => api.getVersion(),
    staleTime: Infinity,
    retry: false,
    enabled: open,
  });
  const { data: updateStatus } = useQuery({
    queryKey: ["update-status"],
    queryFn: () => api.getUpdateStatus(),
    staleTime: 1000 * 30,
    retry: false,
    enabled: open,
  });
  const { data: channel } = useQuery({
    queryKey: ["system", "channel"],
    queryFn: () => api.getReleaseChannel(),
    staleTime: 60_000,
    retry: false,
    enabled: open,
  });
  const { data: updateCheck } = useQuery({
    queryKey: ["update-check"],
    queryFn: () => api.checkForUpdate(),
    staleTime: 1000 * 60 * 60,
    retry: false,
    enabled: open,
  });

  // The rail used to carry an always-visible update arrow next to the version
  // string. The version string is in here now, so its arrow is too — as a
  // line of text rather than an icon, because there is finally room to say
  // which version is waiting. Hidden when an external supervisor owns updates
  // (the Home Assistant add-on): FiestaBoard cannot apply it, so announcing
  // it would be an offer it cannot honour.
  const updateAvailable =
    !updateStatus?.managed_externally && updateCheck?.update_available ? updateCheck.latest_version : null;

  const facts: { key: string; label: string; value: string }[] = [];

  if (channel?.channel) {
    facts.push({
      key: "channel",
      label: t("channel"),
      value: channel.channel === "beta" ? t("channelBeta") : t("channelStable"),
    });
  }

  if (updateStatus?.profile) {
    facts.push({
      key: "platform",
      label: t("platform"),
      value: updateStatus.profile === "pi" ? t("platformPi") : t("platformDocker"),
    });
  }

  if (version?.hardware_model) {
    facts.push({ key: "hardware", label: t("hardware"), value: version.hardware_model });
  }

  if (updateStatus) {
    facts.push({ key: "updates", label: t("updates"), value: describeUpdates(updateStatus, t) });
  }

  if (currentBoard) {
    const { rows, cols } = resolveDimensions(
      currentBoard.device_type,
      currentBoard.notes_wide ?? 1,
      currentBoard.notes_tall ?? 1,
    );
    facts.push({
      key: "board",
      label: t("board"),
      // `×` is the multiplication sign, not the letter x — this is a
      // dimension, and the board's own docs write it that way.
      value: `${currentBoard.name} — ${cols}×${rows}`,
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[calc(100%-2rem)] max-w-sm gap-0 p-0 sm:rounded-xl">
        {/* pt-9: the mark needs air above it more than the facts need air
            below them, and that asymmetry is what makes the box read as a
            portrait rather than a form. */}
        <Stack gap="4" align="center" className="px-6 pb-6 pt-9">
          <FiestaIcon size={96} />
          <Stack gap="1" align="center">
            {/* The wordmark IS the title — a separate heading above it would
                say the product's name twice. One accessible name, one
                visible one, and they are the same name. */}
            <DialogTitle className="text-3xl font-normal leading-none">
              <FiestaLogo className="text-3xl" />
            </DialogTitle>
            {version && (
              <Text size="sm" tone="muted" suppressHydrationWarning>
                {version.running_version}
                {version.is_dev && ` · ${t("devSuffix")}`}
              </Text>
            )}
            {updateAvailable && (
              <Text size="xs" tone="warning">
                {t("updateAvailable", { version: updateAvailable })}
              </Text>
            )}
          </Stack>
          <DialogDescription className="sr-only">{t("description")}</DialogDescription>
        </Stack>

        {facts.length > 0 && (
          <dl className="border-t border-border px-6 py-4">
            {facts.map((fact) => (
              <Flex key={fact.key} align="baseline" justify="between" gap="4" className="py-1">
                <dt className="shrink-0 text-sm text-muted-foreground">{fact.label}</dt>
                {/* text-right + min-w-0: a long hardware string wraps under
                    itself rather than shoving the label off the left edge. */}
                <dd className="min-w-0 text-right text-sm">{fact.value}</dd>
              </Flex>
            ))}
          </dl>
        )}

        <Stack gap="1" align="center" className="border-t border-border px-6 py-4 text-center">
          <Text size="xs" tone="muted">
            {t("license")}
          </Text>
          <Text size="xs" tone="muted">
            {t("copyright", { year: LICENSE_YEAR, holder: LICENSE_HOLDER })}
          </Text>
          <TextLink href={REPO_URL} target="_blank" rel="noopener noreferrer" className="text-xs">
            {t("sourceCode")}
          </TextLink>
        </Stack>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Spelled out rather than built from the interval string. A computed key
 * (`updates${capitalize(interval)}`) works at runtime and is invisible to
 * every tool that reads this repo's i18n by grepping for `t("...")` — the
 * four interval strings would read as unused in all 14 locales and get
 * pruned by the next tidy-up.
 */
const UPDATE_INTERVAL_KEYS: Record<AutoUpdateInterval, string> = {
  daily: "updatesDaily",
  weekly: "updatesWeekly",
  monthly: "updatesMonthly",
  manual: "updatesManual",
};

/**
 * One sentence for how this install gets its updates. The order matters: an
 * externally-managed install cannot update itself whatever the interval
 * says, and an install whose updater is unreachable cannot either —
 * reporting "Automatic, daily" in those cases would be a promise FiestaBoard
 * is in no position to keep.
 */
function describeUpdates(status: UpdateStatusResponse, t: (key: string) => string): string {
  if (status.managed_externally) return t("updatesManaged");
  if (!status.updater_available) return t("updatesUnavailable");
  if (!status.auto_update_enabled) return t("updatesManual");
  return t(UPDATE_INTERVAL_KEYS[status.auto_update_interval]);
}
