import {
  Alert,
  AlertDescription,
  AlertTitle,
  Badge,
  Box,
  Button,
  Card,
  CardContent,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Flex,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Stack,
  Text,
} from "@fiestaboard/ui";
import { ArrowLeft, Clock, RefreshCw, ShieldCheck, Smartphone } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { useCallback, useEffect, useRef, useState } from "react";

import { useMediaQuery } from "@/hooks/use-media-query";
import { useTranslations } from "@/i18n/translations";
import { type PairingOffer, type PairingState, sessionsApi } from "@/lib/api/sessions";

function reachable(address: string): boolean {
  try {
    const url = new URL(address);
    const host = url.hostname
      .toLowerCase()
      .replace(/^\[|\]$/g, "")
      .replace(/\.$/, "");
    return (
      ["http:", "https:"].includes(url.protocol) &&
      !url.username &&
      !url.password &&
      host !== "localhost" &&
      !host.endsWith(".localhost") &&
      !/^127\./.test(host) &&
      !["::1", "0.0.0.0", "::", "0:0:0:0:0:0:0:1"].includes(host) &&
      !host.startsWith("::ffff:7f")
    );
  } catch {
    return false;
  }
}
function safeOffer(offer: PairingOffer): boolean {
  try {
    const payload = new URL(offer.qr_payload);
    const fields = new URLSearchParams(payload.hash.slice(1));
    return (
      payload.protocol === "fiestaboard:" &&
      payload.hostname === "pair" &&
      reachable(offer.hub) &&
      fields.get("hub") === offer.hub &&
      fields.get("v") === "1" &&
      !!fields.get("code")
    );
  } catch {
    return false;
  }
}

export function ConnectPhone({
  open,
  onClose,
  onChanged,
}: {
  open: boolean;
  onClose: () => void;
  onChanged: () => void;
}) {
  const t = useTranslations("phonePairing");
  const phone = useMediaQuery("(max-width: 767px)");
  const [offer, setOffer] = useState<PairingOffer | null>(null);
  const [state, setState] = useState<PairingState>({ state: "pending" });
  const [remaining, setRemaining] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);
  const deadline = useRef(0);
  const active = useRef(false);
  const changed = useRef(onChanged);
  useEffect(() => {
    changed.current = onChanged;
  }, [onChanged]);
  const create = useCallback(
    async (hub?: string) => {
      const run = ++generation.current;
      setBusy(true);
      setError(null);
      setOffer(null);
      setState({ state: "pending" });
      try {
        const next = await sessionsApi.createPairing(hub);
        if (!active.current || run !== generation.current) return;
        if (!safeOffer(next)) throw new Error("invalid_offer");
        deadline.current = Date.now() + next.expires_in * 1000;
        setRemaining(next.expires_in);
        setOffer(next);
      } catch {
        if (active.current && run === generation.current) setError(t("error"));
      } finally {
        if (active.current && run === generation.current) setBusy(false);
      }
    },
    [t],
  );
  const invalidate = useCallback(() => {
    generation.current++;
  }, []);
  useEffect(() => {
    if (!open) return;
    let mounted = true;
    active.current = true;
    queueMicrotask(() => {
      if (mounted) void create();
    });
    return () => {
      mounted = false;
      active.current = false;
      invalidate();
      void sessionsApi.cancelPairing().catch(() => undefined);
    };
  }, [open, create, invalidate]);
  useEffect(() => {
    if (!open || !offer || state.state !== "pending") return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const run = generation.current;
    const tick = setInterval(() => {
      const left = Math.max(0, Math.ceil((deadline.current - Date.now()) / 1000));
      setRemaining(left);
      // Hide a locally expired QR, but keep polling: the phone may have
      // claimed it just before the deadline. Only the server knows that.
    }, 1000);
    const poll = async () => {
      try {
        const next = await sessionsApi.pairingState(offer.pairing_id);
        if (cancelled || run !== generation.current) return;
        setError(null);
        setState(next);
        if (next.state === "claimed") changed.current();
        if (next.state !== "pending") return;
      } catch {
        if (cancelled || run !== generation.current) return;
        setError(t("pollError"));
      }
      if (!cancelled) timer = setTimeout(() => void poll(), 2000);
    };
    timer = setTimeout(() => void poll(), 2000);
    return () => {
      cancelled = true;
      clearTimeout(timer);
      clearInterval(tick);
    };
  }, [open, offer, state.state, t]);
  const claimed = state.state === "claimed";
  const expired = state.state === "expired" || state.state === "cancelled" || (!!offer && remaining === 0);
  const title = claimed
    ? t("connected", { name: state.device_name ?? t("phone") })
    : expired
      ? t("expired")
      : t("title");
  const host = offer ? new URL(offer.hub).host : "";
  const local = typeof window !== "undefined" && !reachable(window.location.origin);
  async function revoke() {
    if (!state.session_id) return;
    setBusy(true);
    setError(null);
    try {
      await sessionsApi.revokeSession(state.session_id);
      changed.current();
      onClose();
    } catch {
      setError(t("revokeError"));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog
      open={open}
      onOpenChange={(value) => {
        if (!value) onClose();
      }}
    >
      {/* FiestaUI follow-up: PairingQR and the phone page presentation are local Figma frames. */}
      <DialogContent
        className={
          phone
            ? "h-dvh max-h-dvh w-full max-w-none rounded-none overflow-y-auto content-start"
            : "sm:max-w-[560px] sm:rounded-xl max-h-[90dvh] overflow-y-auto"
        }
      >
        {phone && (
          <Button variant="ghost" className="justify-self-start min-h-touch" onClick={onClose}>
            <ArrowLeft className="size-4" />
            {t("back")}
          </Button>
        )}
        <DialogHeader>
          <DialogTitle className="text-2xl md:text-xl">{title}</DialogTitle>
          <DialogDescription>
            {t(claimed ? "connectedHint" : expired ? "expiredHint" : "description")}
          </DialogDescription>
        </DialogHeader>
        {phone && !claimed && !expired && (
          <Alert variant="info">
            <Smartphone />
            <AlertTitle>{t("samePhoneTitle")}</AlertTitle>
            <AlertDescription>{t("samePhoneHint")}</AlertDescription>
          </Alert>
        )}
        {local && !claimed && !expired && (
          <Alert variant="warning" politeness="polite">
            <AlertTitle>{t("localhostTitle")}</AlertTitle>
            <AlertDescription>{t("localhostHint")}</AlertDescription>
          </Alert>
        )}
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        {busy && !offer && <Text role="status">{t("loading")}</Text>}
        {claimed ? (
          <Stack gap="4">
            <Card className="py-0">
              <CardContent className="p-4">
                <Text weight="semibold">{state.device_name ?? t("phone")}</Text>
                <Text size="sm" tone="muted">
                  {t("connectedRow")}
                </Text>
              </CardContent>
            </Card>
            <Text size="sm">{t("notYou")}</Text>
          </Stack>
        ) : expired ? (
          <Alert>
            <AlertTitle>{t(state.state === "pending" ? "pollError" : "nothingConnected")}</AlertTitle>
            <AlertDescription>{t("expiredBody")}</AlertDescription>
          </Alert>
        ) : (
          offer && (
            <Stack gap="4">
              <Flex className="flex-col md:flex-row" gap="6" align="center">
                <Card className="w-full md:w-[242px] shrink-0 py-0">
                  <CardContent className="p-4 flex flex-col items-center gap-2.5">
                    <Box className="bg-white p-0 shrink-0">
                      <QRCodeSVG
                        value={offer.qr_payload}
                        size={208}
                  marginSize={4}
                        bgColor="#ffffff"
                        fgColor="#000000"
                        role="img"
                        aria-label={t("qrLabel")}
                      />
                    </Box>
                    <Text size="xs" weight="medium" className="flex items-center gap-1 text-center break-all">
                      <ShieldCheck className="size-3.5 shrink-0" />
                      {t("connectsTo", { host })}
                    </Text>
                    <Text size="xs" weight="medium" className="flex items-center gap-1">
                      <Clock className="size-3.5" />
                      {t("countdown", {
                        time: `${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, "0")}`,
                      })}
                    </Text>
                    <Box className="h-1 w-[208px] rounded-full bg-muted overflow-hidden" aria-hidden="true">
                      <Box
                        className="h-full rounded-full bg-hue-orange"
                        style={{ width: `${Math.max(0, Math.min(100, (remaining / offer.expires_in) * 100))}%` }}
                      />
                    </Box>
                  </CardContent>
                </Card>
                <Stack gap="3" className="min-w-0 flex-1">
                  {local && (
                    <Stack gap="2">
                      <Label htmlFor="pairing-address">{t("address")}</Label>
                      <Select value={offer.hub} onValueChange={(hub) => void create(hub)}>
                        <SelectTrigger id="pairing-address">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {offer.hub_addresses
                            .filter((address) => reachable(address.url))
                            .map((address) => (
                              <SelectItem key={address.url} value={address.url}>
                                {new URL(address.url).host}
                              </SelectItem>
                            ))}
                        </SelectContent>
                      </Select>
                      <Text size="xs" tone="muted">
                        {t("addressHint")}
                      </Text>
                    </Stack>
                  )}
                  {!phone &&
                    [1, 2, 3].map((step) => (
                      <Flex key={step} gap="2" align="start">
                        <Badge variant="secondary">{step}</Badge>
                        <Text size="sm">{t(`step${step}`, { host })}</Text>
                      </Flex>
                    ))}
                </Stack>
              </Flex>
              <Text size="xs" tone="muted">
                {t("warning")}
              </Text>
            </Stack>
          )
        )}
        <DialogFooter className="flex-col md:flex-row">
          {claimed ? (
            <Button variant="outline" disabled={busy || !state.session_id} onClick={() => void revoke()}>
              {t("signOut")}
            </Button>
          ) : (
            <Button variant={expired || error ? "default" : "outline"} disabled={busy} onClick={() => void create()}>
              <RefreshCw className="size-4" />
              {t("newCode")}
            </Button>
          )}
          {!phone && (
            <Button variant={claimed ? "default" : "outline"} onClick={onClose}>
              {t("done")}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
