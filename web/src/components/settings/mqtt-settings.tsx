"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ChevronDown, Eye, EyeOff, Loader2, Radio, XCircle } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import type { MqttSettings } from "@/lib/api";
import { api } from "@/lib/api";

export function MqttSettingsCard() {
  const t = useTranslations("mqttSettings");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
  const [expanded, setExpanded] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [draft, setDraft] = useState<Partial<MqttSettings>>({});

  const { data: settings, isLoading } = useQuery({
    queryKey: ["mqtt-settings"],
    queryFn: () => api.getMqttSettings(),
  });

  const { data: status } = useQuery({
    queryKey: ["mqtt-status"],
    queryFn: () => api.getMqttStatus(),
    refetchInterval: 5000,
  });

  const saveMutation = useMutation({
    mutationFn: (updates: Partial<MqttSettings>) => api.updateMqttSettings(updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["mqtt-settings"] });
      queryClient.invalidateQueries({ queryKey: ["mqtt-status"] });
      setDraft({});
      toast.success(t("toastSaved"));
    },
    onError: (err: Error) => {
      toast.error(err.message);
    },
  });

  const merged: MqttSettings = {
    enabled: false,
    broker_host: "localhost",
    broker_port: 1883,
    username: "",
    password: "",
    external_url: "",
    ...settings,
    ...draft,
  };

  const hasDraft = Object.keys(draft).length > 0;

  const handleToggleEnabled = (checked: boolean) => {
    saveMutation.mutate({ ...merged, enabled: checked });
  };

  const handleSave = () => {
    saveMutation.mutate(merged);
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-4 w-56" />
        </CardHeader>
      </Card>
    );
  }

  const isConnected = status?.connected;
  const isEnabled = merged.enabled;

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Radio className="h-4 w-4" />
            <CardTitle className="text-base">{t("title")}</CardTitle>
          </div>
          <div className="flex items-center gap-3">
            {isEnabled &&
              (isConnected ? (
                <Badge variant="default" className="text-[10px] h-5 bg-board-green flex items-center gap-1">
                  <CheckCircle2 className="h-2.5 w-2.5" />
                  {t("connected")}
                </Badge>
              ) : (
                <Badge variant="secondary" className="text-[10px] h-5 flex items-center gap-1">
                  <XCircle className="h-2.5 w-2.5" />
                  {t("disconnected")}
                </Badge>
              ))}
            <Switch checked={isEnabled} onCheckedChange={handleToggleEnabled} disabled={saveMutation.isPending} />
          </div>
        </div>
        <CardDescription>{t("description")}</CardDescription>
      </CardHeader>

      <Collapsible open={expanded} onOpenChange={setExpanded}>
        <CollapsibleTrigger className="flex w-full items-center justify-between px-6 py-2 text-xs text-muted-foreground hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm">
          <span>{t("brokerConfiguration")}</span>
          <ChevronDown className={`h-4 w-4 transition-transform duration-200 ${expanded ? "rotate-180" : ""}`} />
        </CollapsibleTrigger>

        <CollapsibleContent>
          <CardContent className="pt-2 space-y-4">
            <div className="grid grid-cols-3 gap-3">
              <div className="col-span-2 space-y-1">
                <Label htmlFor="mqtt-broker-host" className="text-xs">
                  {t("brokerHost")}
                </Label>
                <Input
                  id="mqtt-broker-host"
                  value={merged.broker_host}
                  onChange={(e) => setDraft((d) => ({ ...d, broker_host: e.target.value }))}
                  placeholder="localhost"
                  className="h-8 text-xs font-mono"
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="mqtt-broker-port" className="text-xs">
                  {t("port")}
                </Label>
                <Input
                  id="mqtt-broker-port"
                  type="number"
                  value={merged.broker_port}
                  onChange={(e) => setDraft((d) => ({ ...d, broker_port: Number(e.target.value) }))}
                  placeholder="1883"
                  className="h-8 text-xs font-mono"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label htmlFor="mqtt-username" className="text-xs">
                  {t("username")}
                </Label>
                <Input
                  id="mqtt-username"
                  value={merged.username}
                  onChange={(e) => setDraft((d) => ({ ...d, username: e.target.value }))}
                  placeholder={t("optional")}
                  className="h-8 text-xs"
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="mqtt-password" className="text-xs">
                  {t("password")}
                </Label>
                <div className="flex gap-1.5">
                  <Input
                    id="mqtt-password"
                    type={showPassword ? "text" : "password"}
                    value={merged.password === "***" ? "" : merged.password}
                    onChange={(e) => setDraft((d) => ({ ...d, password: e.target.value }))}
                    placeholder={settings?.password === "***" ? t("passwordSet") : t("optional")}
                    className="h-8 text-xs font-mono flex-1"
                  />
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setShowPassword((p) => !p)}
                    className="h-8 w-8 p-0 flex-shrink-0"
                    aria-label={showPassword ? t("hidePassword") : t("showPassword")}
                  >
                    {showPassword ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                  </Button>
                </div>
              </div>
            </div>

            <div className="space-y-1">
              <Label htmlFor="mqtt-external-url" className="text-xs">
                {t("externalUrl")}
              </Label>
              <Input
                id="mqtt-external-url"
                value={merged.external_url}
                onChange={(e) => setDraft((d) => ({ ...d, external_url: e.target.value }))}
                placeholder={t("externalUrlPlaceholder")}
                className="h-8 text-xs font-mono"
              />
              <p className="text-[10px] text-muted-foreground">{t("externalUrlHint")}</p>
            </div>

            {hasDraft && (
              <div className="flex justify-end pt-1">
                <Button
                  size="sm"
                  variant="brand"
                  onClick={handleSave}
                  disabled={saveMutation.isPending}
                  className="text-xs gap-1.5"
                >
                  {saveMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                  {tCommon("save")}
                </Button>
              </div>
            )}
          </CardContent>
        </CollapsibleContent>
      </Collapsible>
    </Card>
  );
}
