"use client";

import {
  Alert,
  AlertDescription,
  AlertTitle,
  Button,
  Flex,
  Heading,
  ListRowGroup,
  NotificationRow,
  Stack,
  StatusBanner,
  StatusBannerAction,
  StatusDot,
  Text,
} from "@fiestaboard/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { useElementWidth } from "@/hooks/use-element-width";
import { useTranslations } from "@/i18n/translations";
import { pushApi, PushApiError, type PushStatus } from "@/lib/api/push";
import { HTTPS_HELP_URL } from "@/lib/pwa/https-help";
import {
  BrowserPushError,
  disableBrowserPush,
  enableBrowserPush,
  getPushAvailability,
  readBrowserPush,
} from "@/lib/pwa/push";

const STATUS_KEY = ["push-status"];
const BROWSER_KEY = ["browser-push"];

/** H15 enrollment only: its four production alert sources are not wired yet. */
export function NotificationSettings() {
  const t = useTranslations("notifications");
  const queryClient = useQueryClient();
  const panel = useRef<HTMLDivElement>(null);
  const panelWidth = useElementWidth(panel);
  const [busy, setBusy] = useState<"account" | "device" | "test" | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const availability = typeof window === "undefined" ? "unsupported" : getPushAvailability();
  const status = useQuery({ queryKey: STATUS_KEY, queryFn: pushApi.getStatus, retry: false, staleTime: 15_000 });
  const browser = useQuery({ queryKey: BROWSER_KEY, queryFn: readBrowserPush, retry: false, staleTime: 0 });
  const refreshStatus = status.refetch;
  const refreshBrowser = browser.refetch;
  useEffect(() => {
    const refresh = () => {
      if (document.visibilityState !== "visible") return;
      void refreshStatus();
      void refreshBrowser();
    };
    // Browser settings can change permission without remounting this screen.
    // The global QueryClient intentionally disables automatic focus refetch.
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [refreshStatus, refreshBrowser]);
  const permission = browser.data?.permission ?? "default";
  const enrolled = !!status.data?.device_enabled && !!status.data.subscribed;
  const ready = enrolled && !!browser.data?.subscribed && permission === "granted" && availability === "supported";
  const rowPermission = availability === "insecure" ? "unavailable" : permission === "denied" ? "denied" : "granted";
  const rowLabels = { denied: t("blockedLabel"), unavailable: t("httpsLabel") };

  async function change(kind: "account" | "device", checked: boolean) {
    if (!status.data || busy) return;
    const sessionQuery = queryClient.getQueryCache().find({ queryKey: STATUS_KEY });
    const sameSession = () => queryClient.getQueryCache().find({ queryKey: STATUS_KEY }) === sessionQuery;
    setBusy(kind);
    setFeedback(null);
    try {
      // Calling enableBrowserPush here preserves the click's permission gesture.
      const next: PushStatus = await (kind === "account"
        ? pushApi.setPreference(checked)
        : checked
          ? enableBrowserPush(status.data.public_key)
          : disableBrowserPush());
      // Sign-out removes the query. A late mutation must not recreate the old
      // account's consent cache after that identity boundary.
      if (!sameSession()) return;
      queryClient.setQueryData(STATUS_KEY, next);
    } catch (error) {
      if (!sameSession()) return;
      setFeedback(
        error instanceof BrowserPushError && error.code === "default"
          ? "dismissed"
          : error instanceof BrowserPushError && error.code === "denied"
            ? "deniedHelp"
            : "actionError",
      );
    } finally {
      if (sameSession()) await browser.refetch();
      setBusy(null);
    }
  }

  async function sendTest() {
    const sessionQuery = queryClient.getQueryCache().find({ queryKey: STATUS_KEY });
    const sameSession = () => queryClient.getQueryCache().find({ queryKey: STATUS_KEY }) === sessionQuery;
    setBusy("test");
    setFeedback(null);
    try {
      const result = await pushApi.sendTest();
      if (!sameSession()) return;
      setFeedback(result.sent > 0 ? "testSent" : result.expired > 0 ? "testExpired" : "notSent");
      // A provider expiry removes the server registration; do not leave the toggle stale.
      await status.refetch();
      await browser.refetch();
    } catch (error) {
      if (!sameSession()) return;
      setFeedback(error instanceof PushApiError && error.status === 429 ? "cooldown" : "testError");
    } finally {
      setBusy(null);
    }
  }

  const environmentNotice =
    availability === "insecure" ? (
      <StatusBanner
        kind="https"
        layout={panelWidth < 560 ? "stacked" : "inline"}
        politeness="off"
        title={t("insecureTitle")}
        description={t("insecureHelp")}
        action={
          <StatusBannerAction variant="ghost" asChild>
            {/* eslint-disable-next-line react/forbid-elements -- Button Slot requires one anchor, matching existing HttpsRequiredBanner */}
            <a href={HTTPS_HELP_URL} target="_blank" rel="noreferrer">
              {t("httpsHelp")}
            </a>
          </StatusBannerAction>
        }
      />
    ) : availability !== "supported" ? (
      <Alert>
        <AlertTitle>{t(`${availability}Title`)}</AlertTitle>
        <AlertDescription>{t(`${availability}Help`)}</AlertDescription>
      </Alert>
    ) : permission === "denied" ? (
      <Alert variant="warning">
        <AlertTitle>{t("permissionDenied")}</AlertTitle>
        <AlertDescription>{t("deniedHelp")}</AlertDescription>
      </Alert>
    ) : null;

  if (status.isPending)
    return (
      <Stack ref={panel} gap="4">
        {environmentNotice}
        <Text role="status" tone="muted">
          {t("loading")}
        </Text>
      </Stack>
    );
  if (!status.data) {
    const needsSession = status.error instanceof PushApiError && [401, 403].includes(status.error.status);
    return (
      <Stack ref={panel} gap="4">
        {environmentNotice}
        <Alert>
          <AlertTitle>{t(needsSession ? "signInTitle" : "loadError")}</AlertTitle>
          <AlertDescription>
            <Stack gap="3">
              {needsSession && <Text size="sm">{t("signInHelp")}</Text>}
              <Button variant="outline" onClick={() => void status.refetch()} disabled={status.isFetching}>
                {t("retry")}
              </Button>
            </Stack>
          </AlertDescription>
        </Alert>
      </Stack>
    );
  }

  return (
    <Stack ref={panel} gap="4" data-slot="notification-settings" aria-busy={!!busy}>
      <Text size="sm" tone="muted">
        {t("privacy")}
      </Text>
      {environmentNotice}

      <ListRowGroup>
        <NotificationRow
          title={t("account")}
          reason={t("accountHint")}
          checked={status.data.user_enabled}
          disabled={!!busy || status.isError}
          onCheckedChange={(checked) => void change("account", checked)}
        />
        <NotificationRow
          title={t("device")}
          reason={t("deviceHint")}
          checked={enrolled}
          disabled={
            !!busy ||
            status.isError ||
            browser.isPending ||
            (!enrolled && (!status.data.user_enabled || availability !== "supported" || permission === "denied"))
          }
          onCheckedChange={(checked) => void change("device", checked)}
        />
      </ListRowGroup>
      {status.isError && (
        <Alert>
          <AlertDescription>{t("loadError")}</AlertDescription>
          <Button variant="outline" onClick={() => void status.refetch()}>
            {t("retry")}
          </Button>
        </Alert>
      )}
      {enrolled && !ready && availability === "supported" && permission !== "denied" && (
        <Text size="sm" tone="muted">
          {t("reconnect")}
        </Text>
      )}
      <Stack gap="2">
        <Heading level={3} size="sm">
          {t("categories")}
        </Heading>
        <Text size="sm" tone="muted">
          {t("unavailable")}
        </Text>
        <ListRowGroup>
          {(["offline", "override", "update", "silence"] as const).map((category) => (
            <NotificationRow
              key={category}
              title={t(category)}
              reason={t(`${category}Hint`)}
              checked={false}
              disabled
              permission={rowPermission}
              labels={rowLabels}
            />
          ))}
        </ListRowGroup>
      </Stack>
      <Flex align="center" justify="between" gap="3" wrap>
        {permission !== "denied" && (
          <Flex align="center" gap="2">
            {ready && <StatusDot status="success" aria-hidden="true" />}
            <Text size="sm" weight="medium">
              {t(permission === "granted" ? "permissionGranted" : "permissionDefault")}
            </Text>
          </Flex>
        )}
        <Button
          variant="outline"
          size="touch"
          disabled={!!busy || status.isError || !ready || !status.data.user_enabled || !status.data.test_available}
          onClick={() => void sendTest()}
        >
          {t(busy === "test" ? "sending" : "sendTest")}
        </Button>
      </Flex>
      {ready && status.data.user_enabled && !status.data.test_available && (
        <Text size="sm" tone="muted">
          {t("senderUnavailable")}
        </Text>
      )}
      {feedback && (
        <Alert role="status">
          <AlertDescription>{t(feedback)}</AlertDescription>
        </Alert>
      )}
    </Stack>
  );
}
