"use client";

import { Check, Monitor, Moon, Sun } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useTheme } from "@/hooks/use-theme";
import { useTranslations } from "@/i18n/translations";
import { cn } from "@/lib/utils";

export function AppearanceSettings() {
  const t = useTranslations("profile");
  const { theme, setTheme } = useTheme();

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Sun className="h-4 w-4" />
          {t("appearanceTitle")}
        </CardTitle>
        <CardDescription>{t("appearanceDescription")}</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-3 gap-3 max-w-sm">
          {(
            [
              { value: "light", label: t("lightMode"), Icon: Sun },
              { value: "dark", label: t("darkMode"), Icon: Moon },
              { value: "system", label: t("systemMode"), Icon: Monitor },
            ] as const
          ).map(({ value, label, Icon }) => {
            const isActive = theme === value;
            return (
              <button
                key={value}
                type="button"
                onClick={() => setTheme(value)}
                aria-pressed={isActive}
                className={cn(
                  "relative flex flex-col items-center gap-2 rounded-lg border p-3 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  isActive
                    ? "border-primary bg-primary/5 text-primary"
                    : "border-border hover:border-primary/50 hover:bg-accent",
                )}
              >
                {isActive && (
                  <span className="absolute right-1.5 top-1.5">
                    <Check className="h-3 w-3 text-primary" />
                  </span>
                )}
                <Icon className="h-5 w-5" />
                {label}
              </button>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
