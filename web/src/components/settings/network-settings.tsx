"use client";

import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  Label,
} from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Loader2, Lock, RefreshCw, Trash2, Unlink, Wifi, WifiOff, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { useTranslations } from "@/i18n/translations";
import type { SavedWifiNetwork, WifiNetwork } from "@/lib/api";
import { api } from "@/lib/api";

/**
 * Settings → Network tab. Only mounted when the backend reports
 * `wifi/capability.available === true` (i.e. FiestaPi with the D-Bus
 * mount + NET_ADMIN cap), so we don't need to defensively re-check
 * capability inside this component.
 */
export function NetworkSettings() {
  const t = useTranslations("network");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();

  const [connectTarget, setConnectTarget] = useState<WifiNetwork | null>(null);
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [disconnectOpen, setDisconnectOpen] = useState(false);
  const [forgetTarget, setForgetTarget] = useState<SavedWifiNetwork | null>(null);

  const statusQuery = useQuery({
    queryKey: ["wifi", "status"],
    queryFn: api.getWifiStatus,
    refetchInterval: 15_000,
  });

  const savedQuery = useQuery({
    queryKey: ["wifi", "saved"],
    queryFn: api.getSavedWifi,
  });

  const scanMutation = useMutation({
    mutationFn: api.scanWifi,
    onError: (err: Error) => toast.error(t("toastScanFailed", { error: err.message })),
  });

  // Auto-fire one scan when the tab mounts; users can manually re-trigger.
  const scanQuery = useQuery({
    queryKey: ["wifi", "scan"],
    queryFn: api.scanWifi,
    staleTime: 30_000,
    retry: false,
  });

  const networks: WifiNetwork[] = scanMutation.data ?? scanQuery.data ?? [];
  const scanning = scanMutation.isPending || scanQuery.isFetching;

  const connectMutation = useMutation({
    mutationFn: api.connectWifi,
    onSuccess: (resp) => {
      setConnectTarget(null);
      setPassword("");
      setShowPassword(false);
      queryClient.invalidateQueries({ queryKey: ["wifi"] });
      const ssid = resp.status.ssid ?? connectTarget?.ssid ?? "";
      const ip = resp.status.ip_address;
      if (!resp.connectivity_confirmed) {
        toast.warning(t("toastConnectedNoInternet", { ssid }));
        return;
      }
      if (ip) {
        toast.success(t("toastConnected", { ssid, ip }), {
          description: t("reconnectHint", { ip }),
          duration: 10_000,
        });
      } else {
        toast.success(t("toastConnectedNoIp", { ssid }));
      }
    },
    onError: (err: Error) => toast.error(t("toastConnectFailed", { error: err.message })),
  });

  const disconnectMutation = useMutation({
    mutationFn: api.disconnectWifi,
    onSuccess: () => {
      setDisconnectOpen(false);
      queryClient.invalidateQueries({ queryKey: ["wifi"] });
      toast.success(t("toastDisconnected"));
    },
    onError: (err: Error) => toast.error(t("toastDisconnectFailed", { error: err.message })),
  });

  const forgetMutation = useMutation({
    mutationFn: (name: string) => api.forgetWifi(name),
    onSuccess: (_data, name) => {
      setForgetTarget(null);
      queryClient.invalidateQueries({ queryKey: ["wifi"] });
      toast.success(t("toastForgotten", { name }));
    },
    onError: (err: Error) => toast.error(t("toastForgetFailed", { error: err.message })),
  });

  const status = statusQuery.data;
  const isConnected = !!status?.connected && !!status.ssid;

  const handleScan = () => scanMutation.mutate();

  const handleStartConnect = (network: WifiNetwork) => {
    setConnectTarget(network);
    setPassword("");
    setShowPassword(false);
  };

  const handleSubmitConnect = () => {
    if (!connectTarget) return;
    const secured = needsPassword(connectTarget);
    connectMutation.mutate({
      ssid: connectTarget.ssid,
      password: secured ? password : undefined,
    });
  };

  return (
    <>
      {/* ── Current connection ─────────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            {isConnected ? (
              <Wifi className="h-4 w-4 text-emerald-600" />
            ) : (
              <WifiOff className="h-4 w-4 text-muted-foreground" />
            )}
            {t("currentConnection")}
          </CardTitle>
          <CardDescription>{t("description")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {statusQuery.isLoading ? (
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          ) : !isConnected ? (
            <p className="text-sm text-muted-foreground">{t("notConnected")}</p>
          ) : (
            <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
              <dt className="text-muted-foreground">{t("ssidLabel")}</dt>
              <dd className="font-medium">{status?.ssid}</dd>
              {status?.ip_address && (
                <>
                  <dt className="text-muted-foreground">{t("ipLabel")}</dt>
                  <dd className="font-mono">{status.ip_address}</dd>
                </>
              )}
              {status?.gateway && (
                <>
                  <dt className="text-muted-foreground">{t("gatewayLabel")}</dt>
                  <dd className="font-mono">{status.gateway}</dd>
                </>
              )}
              {status?.signal != null && (
                <>
                  <dt className="text-muted-foreground">{t("signalLabel")}</dt>
                  {/* eslint-disable-next-line i18next/no-literal-string */}
                  <dd>{status.signal}%</dd>
                </>
              )}
              <dt className="text-muted-foreground">
                {status?.internet_reachable ? t("internetReachable") : t("internetUnreachable")}
              </dt>
              <dd>
                {status?.internet_reachable ? (
                  <Check className="h-4 w-4 text-emerald-600" />
                ) : (
                  <X className="h-4 w-4 text-destructive" />
                )}
              </dd>
            </dl>
          )}
          <div className="flex gap-2 pt-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => queryClient.invalidateQueries({ queryKey: ["wifi", "status"] })}
              disabled={statusQuery.isFetching}
            >
              {statusQuery.isFetching ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4 mr-2" />
              )}
              {t("refresh")}
            </Button>
            {isConnected && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => setDisconnectOpen(true)}
                className="text-destructive hover:text-destructive"
              >
                <Unlink className="h-4 w-4 mr-2" />
                {t("disconnect")}
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {/* ── Available networks ─────────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2 text-base">
              <Wifi className="h-4 w-4" />
              {t("availableNetworks")}
            </CardTitle>
            <Button size="sm" variant="ghost" onClick={handleScan} disabled={scanning}>
              {scanning ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <RefreshCw className="h-4 w-4 mr-2" />}
              {scanning ? t("scanning") : t("rescan")}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {networks.length === 0 && !scanning ? (
            <p className="text-sm text-muted-foreground">{t("noNetworksFound")}</p>
          ) : (
            <ul className="divide-y divide-border">
              {networks.map((n) => (
                <li key={`${n.ssid}-${n.signal}`} className="flex items-center justify-between py-2 gap-3">
                  <div className="flex items-center gap-3 min-w-0">
                    <SignalIcon strength={n.signal} />
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-medium truncate">{n.ssid}</span>
                        {needsPassword(n) && <Lock className="h-3 w-3 text-muted-foreground" />}
                        {n.in_use && (
                          <Badge variant="secondary" className="text-xs">
                            {t("currentConnection")}
                          </Badge>
                        )}
                      </div>
                      {}
                      <div className="text-xs text-muted-foreground">
                        {n.signal}% · {needsPassword(n) ? t("secured") : t("open")}
                      </div>
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleStartConnect(n)}
                    disabled={n.in_use || connectMutation.isPending}
                  >
                    {t("connect")}
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* ── Saved networks ─────────────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("savedNetworks")}</CardTitle>
        </CardHeader>
        <CardContent>
          {savedQuery.isLoading ? (
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          ) : !savedQuery.data || savedQuery.data.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("savedEmpty")}</p>
          ) : (
            <ul className="divide-y divide-border">
              {savedQuery.data.map((s) => (
                <li key={s.name} className="flex items-center justify-between py-2 gap-3">
                  <span className="font-medium truncate">{s.name}</span>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setForgetTarget(s)}
                    className="text-destructive hover:text-destructive"
                  >
                    <Trash2 className="h-4 w-4 mr-2" />
                    {t("forget")}
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* ── Connect dialog ─────────────────────────────────────────────── */}
      <Dialog
        open={connectTarget !== null}
        onOpenChange={(o) => {
          if (!o) {
            setConnectTarget(null);
            setPassword("");
            setShowPassword(false);
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{connectTarget ? t("connectDialogTitle", { ssid: connectTarget.ssid }) : ""}</DialogTitle>
            <DialogDescription>{t("connectDialogDescription")}</DialogDescription>
          </DialogHeader>
          {connectTarget && needsPassword(connectTarget) && (
            <div className="space-y-2">
              <Label htmlFor="wifi-password">{t("passwordLabel")}</Label>
              <div className="flex gap-2">
                <Input
                  id="wifi-password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  autoFocus
                  onChange={(e) => setPassword(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && password) handleSubmitConnect();
                  }}
                />
                <Button type="button" variant="outline" size="sm" onClick={() => setShowPassword((v) => !v)}>
                  {showPassword ? tCommon("off") : tCommon("on")}
                </Button>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setConnectTarget(null)}>
              {tCommon("cancel")}
            </Button>
            <Button
              onClick={handleSubmitConnect}
              disabled={
                connectMutation.isPending || (connectTarget !== null && needsPassword(connectTarget) && !password)
              }
            >
              {connectMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  {t("connecting")}
                </>
              ) : (
                t("connect")
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Disconnect confirm ─────────────────────────────────────────── */}
      <Dialog open={disconnectOpen} onOpenChange={setDisconnectOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("disconnectConfirmTitle", { ssid: status?.ssid ?? "" })}</DialogTitle>
            <DialogDescription>{t("disconnectConfirmDescription")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDisconnectOpen(false)}>
              {tCommon("cancel")}
            </Button>
            <Button
              variant="outline"
              className="text-destructive hover:text-destructive"
              onClick={() => disconnectMutation.mutate()}
              disabled={disconnectMutation.isPending}
            >
              {disconnectMutation.isPending ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Unlink className="h-4 w-4 mr-2" />
              )}
              {t("disconnect")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Forget confirm ─────────────────────────────────────────────── */}
      <Dialog open={forgetTarget !== null} onOpenChange={(o) => !o && setForgetTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{forgetTarget ? t("forgetConfirmTitle", { name: forgetTarget.name }) : ""}</DialogTitle>
            <DialogDescription>{t("forgetConfirmDescription")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setForgetTarget(null)}>
              {tCommon("cancel")}
            </Button>
            <Button
              variant="outline"
              className="text-destructive hover:text-destructive"
              onClick={() => forgetTarget && forgetMutation.mutate(forgetTarget.name)}
              disabled={forgetMutation.isPending}
            >
              {forgetMutation.isPending ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4 mr-2" />
              )}
              {t("forget")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

// "OPEN" is what nmcli reports for unsecured networks; anything else
// (WPA2, WPA3, WEP) requires a password from the user.
function needsPassword(n: WifiNetwork): boolean {
  const s = (n.security || "").trim().toUpperCase();
  return s !== "" && s !== "OPEN" && s !== "--";
}

function SignalIcon({ strength }: { strength: number }) {
  // Map 0..100 to a single-glyph indicator. The lucide Wifi icon doesn't
  // come in tiered strengths, so we colour-code instead — green for
  // strong, amber for weak, red for very weak.
  const color = strength >= 60 ? "text-emerald-600" : strength >= 30 ? "text-amber-500" : "text-destructive";
  return <Wifi className={`h-4 w-4 ${color}`} aria-hidden />;
}
