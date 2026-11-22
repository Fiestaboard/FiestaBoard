"use client";

import { Box, Flex, SegmentedControl, SegmentedControlItem, Stack, Switch, Text } from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LayoutGrid, Monitor, Moon, Sun } from "lucide-react";
import { useId } from "react";
import { toast } from "sonner";

import { SettingsPanel } from "@/components/settings/settings-panel";
import { useHomeColorStrip } from "@/hooks/use-home-color-strip";
import { useTheme } from "@/hooks/use-theme";
import { useTranslations } from "@/i18n/translations";
import { anchorProps } from "@/lib/ai-choreography/anchors";
import { api, type DisplaySettings } from "@/lib/api";

const THEMES = [
  { value: "light", Icon: Sun },
  { value: "dark", Icon: Moon },
  { value: "system", Icon: Monitor },
] as const;

type ThemeValue = (typeof THEMES)[number]["value"];

function isThemeValue(value: string): value is ThemeValue {
  return THEMES.some((option) => option.value === value);
}

/**
 * One 07e settings row: a 14/20 title over a 12/16 hint, the switch on the
 * right, named by the title and described by the hint.
 */
export function SettingSwitchRow({
  title,
  hint,
  checked,
  disabled,
  onCheckedChange,
  anchor,
}: {
  /** AI choreography anchor id for the row (`anchorProps`). */
  anchor?: string;
  title: string;
  hint?: string;
  checked: boolean;
  disabled?: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  const id = useId();
  return (
    <Flex align="center" justify="between" gap="3" {...(anchor ? anchorProps(anchor) : {})}>
      <Box className="min-w-0">
        <label htmlFor={id} className="text-sm font-medium cursor-pointer">
          {title}
        </label>
        {hint && (
          <Text id={`${id}-hint`} size="xs" tone="muted" className="mt-0.5">
            {hint}
          </Text>
        )}
      </Box>
      <Switch
        id={id}
        size="touch"
        aria-describedby={hint ? `${id}-hint` : undefined}
        checked={checked}
        disabled={disabled}
        onCheckedChange={onCheckedChange}
        className="shrink-0"
      />
    </Flex>
  );
}

/**
 * 07e Appearance › Boards (`333:56102`): two switches. "Animate tile flips"
 * is the hub's `board_animations` (on / off; the finer choices live in the
 * Motion details panel below). The colour strip is this browser's choice.
 */
function BoardsSettings() {
  const t = useTranslations("profile");
  const queryClient = useQueryClient();
  const [showStrip, setShowStrip] = useHomeColorStrip();
  const { data: allSettings } = useQuery({ queryKey: ["all-settings"], queryFn: api.getAllSettings });
  const mutation = useMutation({
    mutationFn: (settings: Partial<DisplaySettings>) => api.updateDisplaySettings(settings),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["all-settings"] }),
    onError: (error: Error) => toast.error(error.message),
  });
  // `desktop` still animates (on wider screens), so the switch reads on.
  const stored = mutation.isPending ? mutation.variables?.board_animations : undefined;
  const animate = (stored ?? allSettings?.display?.board_animations ?? "on") !== "off";

  return (
    <SettingsPanel icon={<LayoutGrid />} title={t("boardsTitle")}>
      <Stack gap="6">
        <SettingSwitchRow
          anchor="settings.display.board_animations"
          title={t("animateTileFlips")}
          hint={t("animateTileFlipsHint")}
          checked={animate}
          disabled={!allSettings || mutation.isPending}
          onCheckedChange={(checked) => mutation.mutate({ board_animations: checked ? "on" : "off" })}
        />
        <SettingSwitchRow title={t("homeColorStrip")} checked={showStrip} onCheckedChange={setShowStrip} />
      </Stack>
    </SettingsPanel>
  );
}

export function AppearanceSettings() {
  const t = useTranslations("profile");
  const tPanels = useTranslations("settings.panels");
  const { theme, setTheme } = useTheme();
  const labels: Record<ThemeValue, string> = {
    light: t("lightMode"),
    dark: t("darkMode"),
    system: t("systemMode"),
  };

  return (
    <>
      <SettingsPanel icon={<Sun />} title={tPanels("theme")} description={tPanels("browserTheme")}>
        {/* One-of-three, so a radiogroup rather than three independent
            `aria-pressed` buttons: one tab stop, arrow keys move the choice,
            and the selected tile announces its position in the set. */}
        <SegmentedControl
          size="md"
          value={theme}
          onValueChange={(value) => {
            if (isThemeValue(value)) setTheme(value);
          }}
          aria-label={t("appearanceTitle")}
          className="max-w-sm"
        >
          {THEMES.map(({ value, Icon }) => (
            <SegmentedControlItem key={value} value={value} className="min-h-12">
              <Icon className="size-4" aria-hidden="true" />
              {labels[value]}
            </SegmentedControlItem>
          ))}
        </SegmentedControl>
      </SettingsPanel>
      <BoardsSettings />
    </>
  );
}
