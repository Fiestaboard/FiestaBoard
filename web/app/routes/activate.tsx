import {
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Flex,
  Heading,
  Input,
  Label,
  Stack,
  Text,
} from "@fiestaboard/ui";
import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { useRouter, useSearchParams } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";
import { authApi } from "@/lib/api/auth";
import { type DeviceInspection, SessionApiError, sessionsApi } from "@/lib/api/sessions";
import { getBasePath } from "@/lib/base-path";

export default function Activate() {
  const t = useTranslations("deviceSignIn");
  const router = useRouter();
  const params = useSearchParams();
  const scannedCode = params.get("user_code") ?? "";
  const [code, setCode] = useState(scannedCode);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [device, setDevice] = useState<DeviceInspection | null>(null);
  const [deadline, setDeadline] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<"approved" | "denied" | null>(null);
  const [retryAttempt, setRetryAttempt] = useState(0);
  const consentHeading = useRef<HTMLHeadingElement>(null);
  const errorMessage = useCallback(
    (err: unknown) => {
      if (err instanceof SessionApiError) {
        if (err.status === 401) {
          router.replace(`/login?redirect=${encodeURIComponent(`/activate?user_code=${encodeURIComponent(code)}`)}`);
          return t("errors.signIn");
        }
        const known = [
          "expired_token",
          "access_denied",
          "invalid_grant",
          "feature_disabled",
          "slow_down",
          "rate_limited",
        ];
        if (known.includes(err.code)) return t(`errors.${err.code}`);
      }
      return t("errors.network");
    },
    [code, router, t],
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
        setReady(true);
        if (scannedCode) {
          setBusy(true);
          const found = await sessionsApi.inspectDevice(scannedCode.toUpperCase().replace(/[\s-]/g, ""));
          if (!cancelled) {
            setDevice(found);
            setDeadline(Date.now() + found.expires_in * 1000);
          }
        }
      } catch (err) {
        if (!cancelled)
          setError(
            err instanceof SessionApiError
              ? t(
                  `errors.${["expired_token", "access_denied", "invalid_grant", "feature_disabled"].includes(err.code) ? err.code : "network"}`,
                )
              : t("errors.network"),
          );
      } finally {
        if (!cancelled) setBusy(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [scannedCode, router, t, retryAttempt]);

  useEffect(() => {
    // Announce the new step without placing focus on an authorization action.
    if (device) consentHeading.current?.focus();
  }, [device]);

  useEffect(() => {
    if (!device || result) return;
    const timeout = setTimeout(
      () => {
        setDevice(null);
        setError(t("errors.expired_token"));
      },
      Math.max(0, deadline - Date.now()),
    );
    return () => clearTimeout(timeout);
  }, [device, deadline, result, t]);

  async function inspect(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setDevice(null);
    try {
      const found = await sessionsApi.inspectDevice(code.toUpperCase().replace(/[\s-]/g, ""));
      setDevice(found);
      setDeadline(Date.now() + found.expires_in * 1000);
    } catch (err) {
      setError(errorMessage(err));
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
      setResult(allow ? "approved" : "denied");
      setDevice(null);
    } catch (err) {
      setDevice(null);
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Flex direction="col" align="center" justify="center" className="min-h-screen p-4">
      <meta name="referrer" content="no-referrer" />
      <Card className="w-full max-w-lg">
        <CardHeader>
          <CardTitle as="h1">{t("title")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Text tone="muted">
            {t("server", { address: typeof window === "undefined" ? "" : window.location.origin + getBasePath() })}
          </Text>
          {error && (
            <Text role="alert" tone="destructive">
              {error}
            </Text>
          )}
          {result && <Text role="status">{t(result)}</Text>}
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
            <Box as="form" onSubmit={inspect} className="space-y-3">
              <Label htmlFor="tv-code">{t("code")}</Label>
              <Input
                id="tv-code"
                autoComplete="off"
                autoCapitalize="characters"
                maxLength={32}
                value={code}
                onChange={(event) => setCode(event.target.value)}
                required
                disabled={busy}
              />
              <Button type="submit" disabled={busy || !code.trim()}>
                {t("continue")}
              </Button>
            </Box>
          )}
          {device && (
            <Stack gap="4">
              <Heading level={2} ref={consentHeading} tabIndex={-1}>
                {device.device_name}
              </Heading>
              <Text>{t(device.client_id === "fiestaboard-tvos" ? "appleTV" : "androidTV")}</Text>
              {device.app_version && <Text>{t("version", { version: device.app_version })}</Text>}
              <Text className="font-mono text-2xl">{device.user_code}</Text>
              <Text>{t("checkCode")}</Text>
              <Text>{t("permissions")}</Text>
              <Text tone="muted">{t("expires", { minutes: Math.max(1, Math.ceil(device.expires_in / 60)) })}</Text>
              <Flex gap="3" wrap>
                <Button disabled={busy} onClick={() => void decide(true)}>
                  {t("allow")}
                </Button>
                <Button variant="outline" disabled={busy} onClick={() => void decide(false)}>
                  {t("deny")}
                </Button>
              </Flex>
            </Stack>
          )}
        </CardContent>
      </Card>
    </Flex>
  );
}
