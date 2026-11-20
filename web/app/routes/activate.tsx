import {
  BoardBackdrop,
  Box,
  Button,
  Card,
  FiestaLogo,
  Flex,
  Heading,
  IconTile,
  Input,
  Label,
  Stack,
  Text,
} from "@fiestaboard/ui";
import { CheckCircle2, Clock, ShieldAlert, Tv, UserRound, X } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { useRouter, useSearchParams } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";
import { authApi } from "@/lib/api/auth";
import { type DeviceInspection, SessionApiError, sessionsApi } from "@/lib/api/sessions";
import { getBasePath } from "@/lib/base-path";

const normalizeCode = (value: string) => value.toUpperCase().replace(/[\s-]/g, "");
const BACKDROP_PHRASES = ["WELCOME", "GOOD MORNING", "72 AND CLEAR", "LETS GET STARTED", "HELLO WORLD"];
type Result = "approved" | "denied" | "expired" | "unavailable";

export default function Activate() {
  const t = useTranslations("deviceSignIn");
  const router = useRouter();
  const params = useSearchParams();
  const scannedCode = params.get("user_code") ?? "";
  const [code, setCode] = useState(normalizeCode(scannedCode));
  const [username, setUsername] = useState("");
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [device, setDevice] = useState<DeviceInspection | null>(null);
  const [deviceName, setDeviceName] = useState("");
  const [decidedAt, setDecidedAt] = useState("");
  const [deadline, setDeadline] = useState(0);
  const [secondsLeft, setSecondsLeft] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [retryAttempt, setRetryAttempt] = useState(0);
  const heading = useRef<HTMLHeadingElement>(null);
  const codeField = useRef<HTMLInputElement>(null);
  const complete = /^[BCDFGHJKLMNPQRSTVWXYZ23456789]{8}$/.test(normalizeCode(code));
  const address = typeof window === "undefined" ? "" : window.location.host + getBasePath();

  const handleError = useCallback(
    (err: unknown, currentCode: string) => {
      if (err instanceof SessionApiError) {
        if (err.status === 401) {
          const target = currentCode ? `/activate?user_code=${encodeURIComponent(currentCode)}` : "/activate";
          router.replace(`/login?redirect=${encodeURIComponent(target)}`);
          setError(t("errors.signIn"));
          return;
        }
        if (["expired_token", "invalid_grant", "access_denied"].includes(err.code)) {
          setResult(err.code === "expired_token" ? "expired" : err.code === "access_denied" ? "denied" : "unavailable");
          return;
        }
        if (["feature_disabled", "slow_down", "rate_limited"].includes(err.code)) {
          setError(t(`errors.${err.code}`));
          return;
        }
      }
      setError(t("errors.network"));
    },
    [router, t],
  );

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const status = await authApi.getAuthStatus();
        if (cancelled) return;
        if (!status.enabled || status.setup_required) {
          setError(t("errors.setup"));
          return;
        }
        if (!status.tv_sign_in?.enabled) {
          setError(t("errors.feature_disabled"));
          return;
        }
        if (!status.authenticated) {
          const target = scannedCode ? `/activate?user_code=${encodeURIComponent(scannedCode)}` : "/activate";
          router.replace(`/login?redirect=${encodeURIComponent(target)}`);
          return;
        }
        setUsername(status.username ?? "");
        setReady(true);
        if (scannedCode) {
          setBusy(true);
          const found = await sessionsApi.inspectDevice(normalizeCode(scannedCode));
          if (!cancelled) {
            setDevice(found);
            setDeviceName(found.device_name);
            setDeadline(Date.now() + found.expires_in * 1000);
            setSecondsLeft(found.expires_in);
          }
        }
      } catch (err) {
        if (!cancelled) handleError(err, scannedCode);
      } finally {
        if (!cancelled) setBusy(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [scannedCode, router, t, retryAttempt, handleError]);

  useEffect(() => {
    // Announce each step; authorization always requires an explicit action.
    if (device || result) heading.current?.focus();
  }, [device, result]);

  useEffect(() => {
    if (!device || result) return;
    const tick = () => setSecondsLeft(Math.max(0, Math.ceil((deadline - Date.now()) / 1000)));
    const interval = setInterval(tick, 1000);
    const timeout = setTimeout(
      () => {
        setDevice(null);
        setResult("expired");
      },
      Math.max(0, deadline - Date.now()),
    );
    return () => {
      clearInterval(interval);
      clearTimeout(timeout);
    };
  }, [device, deadline, result]);

  async function inspect(event: FormEvent) {
    event.preventDefault();
    if (!complete || busy) return;
    setBusy(true);
    setError(null);
    setDevice(null);
    try {
      const found = await sessionsApi.inspectDevice(normalizeCode(code));
      setDevice(found);
      setDeviceName(found.device_name);
      setDeadline(Date.now() + found.expires_in * 1000);
      setSecondsLeft(found.expires_in);
    } catch (err) {
      handleError(err, code);
    } finally {
      setBusy(false);
    }
  }

  async function decide(allow: boolean) {
    if (!device || busy) return;
    setBusy(true);
    setError(null);
    try {
      if (allow) await sessionsApi.approveDevice(device.user_code);
      else await sessionsApi.denyDevice(device.user_code);
      setDecidedAt(new Date().toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" }));
      setResult(allow ? "approved" : "denied");
      setDevice(null);
    } catch (err) {
      setDevice(null);
      handleError(err, code);
    } finally {
      setBusy(false);
    }
  }

  function newCode() {
    setResult(null);
    setError(null);
    setDevice(null);
    setDeviceName("");
    setDecidedAt("");
    setCode("");
    // Keep the query out of the effect dependencies while clearing this attempt.
    // The next manual submission uses state, never the scanned query again.
    requestAnimationFrame(() => codeField.current?.focus());
  }

  const title = result ? t(`${result}Title`, { device: deviceName }) : device ? t("consentTitle") : t("title");
  const ResultIcon =
    result === "approved" ? CheckCircle2 : result === "expired" ? Clock : result === "denied" ? X : ShieldAlert;
  const devicesButton = (primary = false) => (
    <Button
      size="lg"
      variant={primary ? "default" : "outline"}
      className="h-11 w-full sm:h-10"
      onClick={() => router.push("/settings/account")}
    >
      {t("seeDevices")}
    </Button>
  );

  return (
    <Flex
      direction="col"
      align="center"
      justify="start"
      className="relative isolate min-h-svh w-screen bg-background px-4 py-6 sm:justify-center sm:p-8"
    >
      <meta name="referrer" content="no-referrer" />
      <BoardBackdrop phrases={BACKDROP_PHRASES} fixed className="hidden sm:block" />
      <Card className="relative z-10 w-full max-w-[398px] gap-4 p-6 sm:p-8">
        <Flex align="center" justify="between" gap="3" wrap className="min-h-25 min-w-0">
          <FiestaLogo size="sm" />
          <Flex align="center" gap="1.5" className="min-w-0">
            <UserRound className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
            <Text size="xs" tone="muted" className="break-all">
              {[username, address].filter(Boolean).join(" · ")}
            </Text>
          </Flex>
        </Flex>
        <Stack gap="4">
          <Heading level={1} size="xl" ref={heading} tabIndex={-1}>
            {title}
          </Heading>
          {error && (
            <Text role="alert" tone="destructive">
              {error}
            </Text>
          )}
          {!ready && !error && <Text role="status">{t("loading")}</Text>}
          {!ready && error && (
            <Button
              disabled={busy}
              onClick={() => {
                setError(null);
                setBusy(true);
                setRetryAttempt((attempt) => attempt + 1);
              }}
            >
              {t("retry")}
            </Button>
          )}
          {ready && !result && !device && (
            <Box as="form" onSubmit={inspect} className="space-y-4">
              <Text size="sm" tone="muted">
                {t("entryDescription", { username, address })}
              </Text>
              <Stack gap="1.5">
                <Label htmlFor="tv-code" className="sr-only">
                  {t("code")}
                </Label>
                {/* FiestaUI has no segmented code primitive; use its Input until that kit follow-up. */}
                <Input
                  ref={codeField}
                  id="tv-code"
                  autoComplete="off"
                  autoCapitalize="characters"
                  spellCheck={false}
                  maxLength={32}
                  value={code}
                  onChange={(event) => setCode(normalizeCode(event.target.value))}
                  required
                  disabled={busy}
                  aria-describedby="code-hint"
                  className="h-12 text-center font-mono text-xl tracking-[0.3em]"
                />
                <Text id="code-hint" size="xs" tone="muted">
                  {t("codeHint")}
                </Text>
              </Stack>
              <Button type="submit" size="lg" className="h-11 w-full sm:h-10" disabled={busy || !complete}>
                {t("continue")}
              </Button>
              <Text size="xs" tone="muted">
                {t("noCode")}
              </Text>
            </Box>
          )}
          {device && (
            <>
              <Text size="sm" tone="muted">
                {t("consentDescription")}
              </Text>
              <Stack gap="2.5" className="rounded-lg bg-muted p-4">
                <Flex align="center" gap="3">
                  <IconTile tone="muted" size="md">
                    <Tv className="size-5" />
                  </IconTile>
                  <Stack gap="0.5" className="min-w-0">
                    <Text size="sm" weight="medium" className="break-words">
                      {device.device_name}
                    </Text>
                    <Text size="xs" tone="muted">
                      {t(device.client_id === "fiestaboard-tvos" ? "appleTV" : "androidTV")}
                      {device.app_version ? ` · ${device.app_version}` : ""}
                    </Text>
                    <Text size="xs" tone="muted">
                      {t("displayCode", { code: device.user_code })}
                    </Text>
                  </Stack>
                </Flex>
                <Text size="xs">{t("permissions")}</Text>
                <Text size="xs" tone="muted">
                  {t("checkCode")}
                </Text>
                <Flex align="center" gap="1.5">
                  <Clock className="size-3.5" aria-hidden="true" />
                  <Text size="xs">
                    {t("countdown", {
                      time: `${Math.floor(secondsLeft / 60)}:${String(secondsLeft % 60).padStart(2, "0")}`,
                    })}
                  </Text>
                </Flex>
              </Stack>
              <Flex gap="2" className="flex-col sm:flex-row-reverse">
                <Button
                  size="lg"
                  className="h-11 w-full sm:h-10 sm:flex-1"
                  disabled={busy}
                  onClick={() => void decide(true)}
                >
                  {t("allow")}
                </Button>
                <Button
                  variant="outline"
                  size="lg"
                  className="h-11 w-full sm:h-10 sm:flex-1"
                  disabled={busy}
                  onClick={() => void decide(false)}
                >
                  {t("deny")}
                </Button>
              </Flex>
            </>
          )}
          {result && (
            <>
              {result === "expired" && (
                <Text className="font-mono text-xl tracking-[0.2em] text-destructive">
                  {normalizeCode(code).replace(/^(.{4})(.+)$/, "$1–$2")}
                </Text>
              )}
              <Flex align="start" gap="3" role={result === "expired" || result === "unavailable" ? "alert" : "status"}>
                <ResultIcon
                  aria-hidden="true"
                  className={`mt-0.5 size-6 shrink-0 ${result === "denied" ? "text-destructive" : result === "approved" ? "text-success" : "text-muted-foreground"}`}
                />
                <Stack gap="2">
                  <Text size="sm" tone="muted">
                    {t(`${result}Body`, { device: deviceName || t("unknownTV") })}
                  </Text>
                  {(result === "expired" || result === "unavailable") && <Text size="sm">{t(`${result}Hint`)}</Text>}
                  {decidedAt && <Text size="xs">{t(`${result}Meta`, { time: decidedAt })}</Text>}
                </Stack>
              </Flex>
              {result === "unavailable"
                ? devicesButton(true)
                : result !== "expired" && (
                    <Button size="lg" className="h-11 w-full sm:h-10" onClick={() => router.push("/")}>
                      {t("done")}
                    </Button>
                  )}
              {result === "approved" ? (
                devicesButton()
              ) : (
                <Button
                  size="lg"
                  variant={result === "expired" ? "default" : "outline"}
                  className="h-11 w-full sm:h-10"
                  onClick={newCode}
                >
                  {t(result === "unavailable" ? "differentCode" : "newCode")}
                </Button>
              )}
            </>
          )}
        </Stack>
      </Card>
    </Flex>
  );
}
