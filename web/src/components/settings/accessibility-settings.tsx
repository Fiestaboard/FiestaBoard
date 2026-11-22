"use client";

import { Box, Flex, Stack, Switch, Text } from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";
import { Accessibility } from "lucide-react";

import { SettingsPanel } from "@/components/settings/settings-panel";
import { type BrowserA11yPref, useBrowserA11y } from "@/hooks/use-browser-a11y";
import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";

const ROWS: { pref: BrowserA11yPref; id: string; title: string; hint: string }[] = [
  { pref: "reduceMotion", id: "browser-reduce-motion", title: "reduceMotion", hint: "reduceMotionBrowserHint" },
  { pref: "readAloud", id: "browser-read-aloud", title: "readAloud", hint: "readAloudHint" },
  { pref: "largeTargets", id: "browser-large-targets", title: "largeTargets", hint: "largeTargetsHint" },
  { pref: "boardContrast", id: "browser-board-contrast", title: "boardContrast", hint: "boardContrastHint" },
];

/** One 07e row: a 14/20 title over a 12/16 hint, the switch on the right. */
function PrefRow({ pref, id, title, hint, hubOn }: (typeof ROWS)[number] & { hubOn: boolean }) {
  const t = useTranslations("profile");
  const [on, setOn] = useBrowserA11y(pref);
  // The hub's Reduce motion is on for everyone, so this browser cannot turn
  // motion back on here: show it on and say where it is set.
  const locked = pref === "reduceMotion" && hubOn;
  return (
    <Flex align="center" justify="between" gap="3">
      <Box className="min-w-0">
        <label htmlFor={id} className="text-sm font-medium cursor-pointer">
          {t(title)}
        </label>
        <Text id={`${id}-hint`} size="xs" tone="muted" className="mt-0.5">
          {t(hint)}
        </Text>
        {locked && (
          <Text size="xs" tone="muted" className="mt-1">
            {t("hubReduceMotionOn")}
          </Text>
        )}
      </Box>
      <Switch
        id={id}
        size="touch"
        aria-describedby={`${id}-hint`}
        checked={on || locked}
        disabled={locked}
        onCheckedChange={setOn}
        className="shrink-0"
      />
    </Flex>
  );
}

/**
 * 07e Accessibility (`333:57132`): "Motion and reading · For this browser."
 * Four switches stored in this browser (`useBrowserA11y`). The hub-wide
 * Reduce motion lives in Appearance › Motion details (DESIGN-DELTAS DD-W153).
 */
export function AccessibilitySettings() {
  const t = useTranslations("profile");
  const { data: allSettings } = useQuery({ queryKey: ["all-settings"], queryFn: api.getAllSettings });
  const hubOn = allSettings?.display?.reduce_motion ?? false;

  return (
    <SettingsPanel icon={<Accessibility />} title={t("motionReadingTitle")} description={t("motionReadingScope")}>
      <Stack gap="6">
        {ROWS.map((row) => (
          <PrefRow key={row.pref} {...row} hubOn={hubOn} />
        ))}
      </Stack>
    </SettingsPanel>
  );
}
