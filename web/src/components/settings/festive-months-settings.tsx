"use client";

import { Sparkles } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";

const COOKIE_NAME = "hide_festive_months";
// 10 years — this is a sticky per-browser preference, not a session
// thing. The cookie is the gate the root layout reads in its
// `useState` initializer on first mount (post-RR7-SPA migration; was
// a `next/headers` `cookies()` read in the prior Next.js layout).
const COOKIE_MAX_AGE = 60 * 60 * 24 * 365 * 10;

function readCookie(): boolean {
  if (typeof document === "undefined") return false;
  return document.cookie.split("; ").some((c) => c === `${COOKIE_NAME}=true`);
}

function writeCookie(hide: boolean) {
  document.cookie = hide
    ? `${COOKIE_NAME}=true; path=/; max-age=${COOKIE_MAX_AGE}; samesite=lax`
    : `${COOKIE_NAME}=; path=/; max-age=0; samesite=lax`;
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
        <div className="flex items-start justify-between gap-4 rounded-md border p-4">
          <div className="space-y-1">
            <span className="font-medium">{t("hideLabel")}</span>
            <p className="text-sm text-muted-foreground">{t("hideHint")}</p>
          </div>
          <Switch checked={hide} onCheckedChange={onToggle} aria-label={t("hideLabel")} />
        </div>
      </CardContent>
    </Card>
  );
}
