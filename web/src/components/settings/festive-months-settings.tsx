"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle, Flex, Stack, Switch, Text } from "@fiestaboard/ui";
import { Sparkles } from "lucide-react";
import { useEffect, useState } from "react";

import { useTranslations } from "@/i18n/translations";
import { HIDE_FESTIVE_COOKIE } from "@/lib/pride";

// 10 years — this is a sticky per-browser preference, not a session
// thing. The cookie is read by the root layout's `useEffect` on first
// mount to toggle the `pride-month` class on `<html>`.
const COOKIE_MAX_AGE = 60 * 60 * 24 * 365 * 10;

function readCookie(): boolean {
  if (typeof document === "undefined") return false;
  return document.cookie.split("; ").some((c) => c === `${HIDE_FESTIVE_COOKIE}=true`);
}

function writeCookie(hide: boolean) {
  document.cookie = hide
    ? `${HIDE_FESTIVE_COOKIE}=true; path=/; max-age=${COOKIE_MAX_AGE}; samesite=lax`
    : `${HIDE_FESTIVE_COOKIE}=; path=/; max-age=0; samesite=lax`;
}

/**
 * Settings → Advanced → Festive Months.
 *
 * Toggles a `hide_festive_months` cookie that the root layout reads
 * on first mount (`useState` initializer in `web/app/root.tsx::Layout`)
 * to decide whether to put the `pride-month` class on `<html>` (the
 * single gate for the rainbow logo, sidebar treatment, and aurora
 * canvases). Flipping the switch reloads the page so the layout
 * re-runs its initializer with the new cookie value.
 */
export function FestiveMonthsSettings() {
  const t = useTranslations("festiveMonthsSettings");
  const [hide, setHide] = useState(false);

  useEffect(() => {
    setHide(readCookie());
  }, []);

  const onToggle = (checked: boolean) => {
    setHide(checked);
    writeCookie(checked);
    window.location.reload();
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base flex items-center gap-2">
          <Sparkles className="h-4 w-4" />
          {t("title")}
        </CardTitle>
        <CardDescription>{t("description")}</CardDescription>
      </CardHeader>
      <CardContent>
        <Flex align="start" justify="between" gap="4" className="rounded-md border p-4">
          <Stack gap="1">
            <Text as="span" weight="medium">
              {t("hideLabel")}
            </Text>
            <Text tone="muted">{t("hideHint")}</Text>
          </Stack>
          <Switch checked={hide} onCheckedChange={onToggle} aria-label={t("hideLabel")} />
        </Flex>
      </CardContent>
    </Card>
  );
}
