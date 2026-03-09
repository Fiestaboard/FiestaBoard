"use client";

import { useEffect, useState, useMemo } from "react";
import { useTranslations } from "next-intl";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { TimezonePicker } from "@/components/ui/timezone-picker";
import { cn } from "@/lib/utils";
import { Clock, Star, Wifi, Eye, EyeOff } from "lucide-react";

interface PluginConfig {
  date_time: { enabled: boolean; timezone: string };
  star_trek_quotes: { enabled: boolean; ratio: string };
  guest_wifi: { enabled: boolean; ssid: string; password: string };
}

interface StepEasyPluginsProps {
  config: PluginConfig;
  onConfigChange: (config: PluginConfig) => void;
  onValidChange: (valid: boolean) => void;
}

export function StepEasyPlugins({
  config,
  onConfigChange,
  onValidChange,
}: StepEasyPluginsProps) {
  const t = useTranslations("wizard.easyPlugins");
  const tc = useTranslations("common");
  const [showPassword, setShowPassword] = useState(false);
  const [currentTime, setCurrentTime] = useState("");

  // This step is always valid (all plugins are optional)
  useEffect(() => {
    onValidChange(true);
  }, [onValidChange]);

  // Update current time preview for timezone
  useEffect(() => {
    const updateTime = () => {
      try {
        const now = new Date();
        setCurrentTime(
          now.toLocaleTimeString("en-US", {
            timeZone: config.date_time.timezone,
            hour: "numeric",
            minute: "2-digit",
            hour12: true,
          })
        );
      } catch {
        setCurrentTime("--:--");
      }
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, [config.date_time.timezone]);

  // Note: Feature configs are saved in step-welcome.tsx when the user completes the wizard
  // This step just tracks state locally

  // Random Star Trek quote for preview
  const sampleQuotes = useMemo(() => [
    { quote: "Make it so.", character: "PICARD", series: "TNG" },
    { quote: "Live long and prosper.", character: "SPOCK", series: "TNG" },
    { quote: "Resistance is futile.", character: "BORG", series: "TNG" },
    { quote: "I'm a doctor, not a...", character: "DOCTOR", series: "VOY" },
  ], []);

  const [sampleQuote] = useState(() => 
    sampleQuotes[Math.floor(Math.random() * sampleQuotes.length)]
  );

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground mb-4">
        {t("description")}
      </p>

      {/* Date & Time */}
      <Card className={cn(
        "transition-all",
        config.date_time.enabled && "ring-2 ring-primary"
      )}>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className={cn(
                "p-2 rounded-lg",
                config.date_time.enabled ? "bg-primary/10" : "bg-muted"
              )}>
                <Clock className={cn(
                  "h-5 w-5",
                  config.date_time.enabled ? "text-primary" : "text-muted-foreground"
                )} />
              </div>
              <div>
                <CardTitle className="text-base">{t("dateTimeTitle")}</CardTitle>
                <CardDescription className="text-xs">
                  {t("dateTimeDescription")}
                </CardDescription>
              </div>
            </div>
            <Switch
              checked={config.date_time.enabled}
              onCheckedChange={(enabled) =>
                onConfigChange({
                  ...config,
                  date_time: { ...config.date_time, enabled },
                })
              }
            />
          </div>
        </CardHeader>
        {config.date_time.enabled && (
          <CardContent className="pt-2 space-y-3">
            <div className="space-y-2">
              <Label className="text-sm">{t("timezoneLabel")}</Label>
              <TimezonePicker
                value={config.date_time.timezone}
                onChange={(timezone) =>
                  onConfigChange({
                    ...config,
                    date_time: { ...config.date_time, timezone },
                  })
                }
              />
            </div>
            <div className="text-sm text-muted-foreground bg-muted/50 p-2 rounded">
              {tc("preview")}: <span className="font-mono">{currentTime}</span>
            </div>
          </CardContent>
        )}
      </Card>

      {/* Star Trek Quotes */}
      <Card className={cn(
        "transition-all",
        config.star_trek_quotes.enabled && "ring-2 ring-primary"
      )}>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className={cn(
                "p-2 rounded-lg",
                config.star_trek_quotes.enabled ? "bg-primary/10" : "bg-muted"
              )}>
                <Star className={cn(
                  "h-5 w-5",
                  config.star_trek_quotes.enabled ? "text-primary" : "text-muted-foreground"
                )} />
              </div>
              <div>
                <CardTitle className="text-base">{t("starTrekTitle")}</CardTitle>
                <CardDescription className="text-xs">
                  {t("starTrekDescription")}
                </CardDescription>
              </div>
            </div>
            <Switch
              checked={config.star_trek_quotes.enabled}
              onCheckedChange={(enabled) =>
                onConfigChange({
                  ...config,
                  star_trek_quotes: { ...config.star_trek_quotes, enabled },
                })
              }
            />
          </div>
        </CardHeader>
        {config.star_trek_quotes.enabled && (
          <CardContent className="pt-2">
            <div className="text-sm text-muted-foreground bg-muted/50 p-3 rounded font-mono text-center">
              <p className="italic">"{sampleQuote.quote}"</p>
              <p className="text-xs mt-1">— {sampleQuote.character}, {sampleQuote.series}</p>
            </div>
          </CardContent>
        )}
      </Card>

      {/* Guest WiFi */}
      <Card className={cn(
        "transition-all",
        config.guest_wifi.enabled && "ring-2 ring-primary"
      )}>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className={cn(
                "p-2 rounded-lg",
                config.guest_wifi.enabled ? "bg-primary/10" : "bg-muted"
              )}>
                <Wifi className={cn(
                  "h-5 w-5",
                  config.guest_wifi.enabled ? "text-primary" : "text-muted-foreground"
                )} />
              </div>
              <div>
                <CardTitle className="text-base">{t("guestWifiTitle")}</CardTitle>
                <CardDescription className="text-xs">
                  {t("guestWifiDescription")}
                </CardDescription>
              </div>
            </div>
            <Switch
              checked={config.guest_wifi.enabled}
              onCheckedChange={(enabled) =>
                onConfigChange({
                  ...config,
                  guest_wifi: { ...config.guest_wifi, enabled },
                })
              }
            />
          </div>
        </CardHeader>
        {config.guest_wifi.enabled && (
          <CardContent className="pt-2 space-y-3">
            <div className="space-y-2">
              <Label className="text-sm">{t("networkNameLabel")}</Label>
              <Input
                placeholder={t("networkNamePlaceholder")}
                value={config.guest_wifi.ssid}
                onChange={(e) =>
                  onConfigChange({
                    ...config,
                    guest_wifi: { ...config.guest_wifi, ssid: e.target.value },
                  })
                }
                maxLength={22}
              />
            </div>
            <div className="space-y-2">
              <Label className="text-sm">{t("passwordLabel")}</Label>
              <div className="relative">
                <Input
                  type={showPassword ? "text" : "password"}
                  placeholder={t("passwordPlaceholder")}
                  value={config.guest_wifi.password}
                  onChange={(e) =>
                    onConfigChange({
                      ...config,
                      guest_wifi: { ...config.guest_wifi, password: e.target.value },
                    })
                  }
                  maxLength={22}
                  className="pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>
            {config.guest_wifi.ssid && (
              <div className="text-sm text-muted-foreground bg-muted/50 p-2 rounded font-mono text-center">
                <p>{t("wifiPreview", { ssid: config.guest_wifi.ssid })}</p>
                <p>{t("passPreview", { password: config.guest_wifi.password ? "••••••••" : t("noPassword") })}</p>
              </div>
            )}
          </CardContent>
        )}
      </Card>
    </div>
  );
}

