import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Checkbox,
  Flex,
  Heading,
  IconTile,
  Label,
  List,
  ListItem,
  Stack,
  Switch,
  Text,
} from "@fiestaboard/ui";
import { AppWindow, Clock, Monitor, QrCode, Smartphone, Tv } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { useRouter } from "@/hooks/use-router";
import { useLocale, useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";
import { SessionApiError, type SessionList, sessionsApi, type SessionSummary } from "@/lib/api/sessions";
import { formatSessionTime } from "@/lib/relative-time";
import { sessionDisplayName } from "@/lib/session-display-name";

import { ConnectPhone } from "./connect-phone";

export function SignedInDevices() {
  const t = useTranslations("signedInDevices");
  const locale = useLocale();
  const router = useRouter();
  const [data, setData] = useState<SessionList | null>(null);
  const [panelNames, setPanelNames] = useState<Record<string, string>>({});
  const [enabled, setEnabled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<"others" | "all" | SessionSummary | null>(null);
  const [cascade, setCascade] = useState(true);
  const [pairing, setPairing] = useState(false);
  const [retryAttempt, setRetryAttempt] = useState(0);
  const load = useCallback(async () => {
    const [list, settings] = await Promise.all([sessionsApi.listSessions(), sessionsApi.getDeviceSettings()]);
    setData(list);
    setEnabled(settings.enabled);
  }, []);
  useEffect(() => {
    let active = true;
    Promise.all([sessionsApi.listSessions(), sessionsApi.getDeviceSettings()])
      .then(([list, settings]) => {
        if (active) {
          setData(list);
          setEnabled(settings.enabled);
        }
      })
      .catch(() => {
        if (active) setError(t("error"));
      });
    return () => {
      active = false;
    };
  }, [t, retryAttempt]);
  useEffect(() => {
    let active = true;
    void api
      .listPanels()
      .then(({ panels }) => {
        if (active) setPanelNames(Object.fromEntries(panels.map((panel) => [panel.id, panel.name])));
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [retryAttempt]);
  async function action(work: () => Promise<unknown>, signOut = false) {
    setBusy(true);
    setError(null);
    try {
      await work();
      setConfirm(null);
      if (signOut) {
        router.replace("/login");
        return;
      }
      await load();
    } catch (err) {
      if (err instanceof SessionApiError && err.status === 401) router.replace("/login");
      else {
        let message = t("error");
        if (phone && cascade) {
          try {
            const fresh = await sessionsApi.listSessions();
            setData(fresh);
            const pending = approved.filter((tv) => fresh.sessions.some((row) => row.id === tv.id));
            if (pending.length) message = t("partial", { names: pending.map((tv) => tv.device_name).join(", ") });
          } catch {
            /* Keep the confirmation retryable if refreshing also fails. */
          }
        }
        setError(message);
        if (phone) toast.error(message);
      }
    } finally {
      setBusy(false);
    }
  }
  const phone = typeof confirm === "object" ? confirm : null;
  const approved = phone
    ? (data?.sessions ?? []).filter((row) => row.kind === "tv" && row.approved_by?.session_id === phone.id)
    : [];
  // 07e reads times the way people say them: "just now", "5:38 PM",
  // "yesterday, 9:12 PM", "Nov 2". `nameToday` says "today, 5:31 PM" where
  // the time follows a "when it happened" date rather than "Last connected".
  const timeLabels = {
    justNow: t("justNow"),
    dayTime: (day: string, time: string) => t("dayTime", { day, time }),
  };
  const date = (value: string, nameToday = false) => formatSessionTime(value, locale, timeLabels, { nameToday });
  function lastShown(session: SessionSummary) {
    return session.last_shown_at
      ? t("lastShown", {
          panel: panelNames[session.shown_panels?.[0]?.panel_id ?? ""] ?? t("panel"),
          date: date(session.last_shown_at),
        })
      : t("nothingShown");
  }
  const groups = [
    { key: "browsers", rows: data?.sessions.filter((row) => row.kind === "browser") ?? [] },
    { key: "phones", rows: data?.sessions.filter((row) => row.kind === "mobile") ?? [] },
    { key: "codeTvs", rows: data?.sessions.filter((row) => row.kind === "tv" && row.method !== "password") ?? [] },
    { key: "passwordTvs", rows: data?.sessions.filter((row) => row.kind === "tv" && row.method === "password") ?? [] },
    // A password sign-in from anything that is not a browser: an older TV
    // app, a script, an API client. The hub cannot tell which (it only sees a
    // non-browser user agent), so it is not called a TV (BB-C-24).
    { key: "passwordApps", rows: data?.sessions.filter((row) => row.kind === "legacy") ?? [] },
  ];
  return (
    <Stack gap="4" className="text-foreground">
      {/* 07e `321:9076`: the heading row carries both actions on its right —
          outline "Sign out other devices…" (it opens a confirm), then the
          primary "Connect a phone" (BB-FC-13). */}
      <Flex align="start" justify="between" gap="3" wrap data-slot="signed-in-devices-head">
        <Stack gap="1" className="min-w-0 flex-1 basis-60">
          <Heading level={3} size="xl">
            {t("title")}
          </Heading>
          <Text size="sm" tone="muted">
            {t("description")}
          </Text>
        </Stack>
        {data && (
          <Flex gap="2" wrap className="flex-col sm:flex-row">
            <Button
              variant="outline"
              className="min-h-touch sm:min-h-0"
              disabled={busy}
              onClick={() => setConfirm("others")}
            >
              {t("othersAction")}
            </Button>
            <Button className="min-h-touch sm:min-h-0" disabled={busy} onClick={() => setPairing(true)}>
              <QrCode className="size-4" />
              {t("connectPhone")}
            </Button>
          </Flex>
        )}
      </Flex>
      <Stack gap="4">
        {error && !confirm && (
          <Text role="alert" tone="destructive">
            {error}
          </Text>
        )}
        {!data && !error && <Text role="status">{t("loading")}</Text>}
        {!data && error && (
          <Button
            onClick={() => {
              setError(null);
              setRetryAttempt((attempt) => attempt + 1);
            }}
          >
            {t("retry")}
          </Button>
        )}
        {data && (
          <>
            {/* The legend chip: a clock for "Last connected", a monitor for
                "Last shown", as the rows draw them (07e `321:9076`). */}
            <Flex
              align="center"
              gap="4"
              wrap
              className="rounded-md bg-muted px-3 py-2"
              data-slot="signed-in-devices-legend"
            >
              {t("clocksLegend")
                .split(" · ")
                .map((part, index) => (
                  <Flex key={part} align="center" gap="1.5">
                    {index === 0 ? (
                      <Clock className="size-3.5 text-muted-foreground" aria-hidden="true" />
                    ) : (
                      <Monitor className="size-3.5 text-muted-foreground" aria-hidden="true" />
                    )}
                    <Text as="span" size="xs" tone="muted">
                      {part}
                    </Text>
                  </Flex>
                ))}
            </Flex>
            {groups
              .filter((group) => group.rows.length)
              .map((group) => (
                <Stack key={group.key} gap="2">
                  <Heading level={3} size="sm" className="text-xs text-muted-foreground uppercase tracking-wide">
                    {t(group.key)}
                  </Heading>
                  <List className="rounded-[var(--radius-card)] border bg-card p-1">
                    {[...group.rows]
                      .sort((a, b) => b.created_at.localeCompare(a.created_at))
                      .map((session) => {
                        const app = session.kind === "legacy";
                        const name = app
                          ? t("appName")
                          : sessionDisplayName(session, t("browser"), (browser, platform) =>
                              t("browserOn", { browser, platform }),
                            );
                        const current = session.id === data.current_session_id;
                        const mobile = session.kind === "mobile";
                        const tv = session.kind === "tv";
                        const codeTV = session.kind === "tv" && session.method !== "password";
                        const kind = current
                          ? t("current")
                          : mobile
                            ? t("phone")
                            : codeTV
                              ? t("tv")
                              : tv || app
                                ? t("passwordSignIn")
                                : t("browser");
                        const Icon = mobile ? Smartphone : tv ? Tv : app ? AppWindow : Monitor;
                        const tvCount = data.sessions.filter(
                          (row) => row.kind === "tv" && row.approved_by?.session_id === session.id,
                        ).length;
                        return (
                          <ListItem key={session.id} aria-label={name} className="border-b last:border-b-0 p-3">
                            {/* FiestaUI follow-up: promote 07e SessionRow; compose existing kit parts meanwhile. */}
                            <Flex gap="3" align="start">
                              <IconTile tone="muted" size="sm">
                                <Icon className="size-4" />
                              </IconTile>
                              <Stack gap="1" className="min-w-0 flex-1 relative md:pr-24">
                                <Flex gap="2" align="center" wrap>
                                  <Text weight="semibold" size="sm" className="break-words">
                                    {name}
                                  </Text>
                                  <Badge
                                    variant={current ? "default" : (tv && !codeTV) || app ? "outline" : "secondary"}
                                  >
                                    {kind}
                                  </Badge>
                                </Flex>
                                {mobile && (
                                  <Text size="xs" tone="muted">
                                    {t("phoneConnected", { date: date(session.created_at, true), count: tvCount })}
                                  </Text>
                                )}
                                {session.approved_by && (
                                  <Text size="xs" tone="muted">
                                    {t("approvedBy", {
                                      name: session.approved_by.label,
                                      date: date(session.created_at, true),
                                    })}
                                  </Text>
                                )}
                                {session.kind === "browser" && (
                                  <Text size="xs" tone="muted">
                                    {t("browserSignedIn", { date: date(session.created_at, true) })}
                                  </Text>
                                )}
                                {tv && !codeTV && (
                                  <Text size="xs" tone="muted">
                                    {t("passwordHint")}
                                  </Text>
                                )}
                                {app && (
                                  <Text size="xs" tone="muted">
                                    {t("appHint", { date: date(session.created_at, true) })}
                                  </Text>
                                )}
                                <Flex gap="3" wrap className="flex-col lg:flex-row">
                                  <Text size="xs" tone="muted" className="flex items-start gap-1">
                                    <Clock className="size-3.5 shrink-0" />
                                    {t("lastConnected", { date: date(session.last_active_at) })}
                                  </Text>
                                  {(tv || (app && session.last_shown_at)) && (
                                    <Text size="xs" tone="muted" className="flex items-start gap-1">
                                      <Monitor className="size-3.5 shrink-0" />
                                      {lastShown(session)}
                                    </Text>
                                  )}
                                </Flex>
                                {!current && (
                                  <Button
                                    className="self-start min-h-touch sm:min-h-0 mt-2 md:absolute md:right-0 md:top-0 md:mt-0"
                                    variant="outline"
                                    aria-label={t("revokeDevice", { name })}
                                    disabled={busy}
                                    onClick={() => {
                                      if (mobile) {
                                        setCascade(true);
                                        setConfirm(session);
                                      } else void action(() => sessionsApi.revokeSession(session.id));
                                    }}
                                  >
                                    {t(mobile ? "signOutMore" : "signOut")}
                                  </Button>
                                )}
                              </Stack>
                            </Flex>
                          </ListItem>
                        );
                      })}
                  </List>
                </Stack>
              ))}
            <Stack gap="2">
              <Flex align="center" gap="3">
                <Switch
                  id="tv-enrollment"
                  checked={enabled}
                  disabled={busy}
                  onCheckedChange={(value) => void action(() => sessionsApi.updateDeviceSettings(value))}
                />
                <Label htmlFor="tv-enrollment">{t("enrollment")}</Label>
              </Flex>
              <Text size="sm" tone="muted">
                {t("enrollmentHint")}
              </Text>
              <Button className="self-start" variant="outline" disabled={busy} onClick={() => setConfirm("all")}>
                {t("all")}
              </Button>
            </Stack>
          </>
        )}
        {pairing && (
          <ConnectPhone
            open={pairing}
            onClose={() => setPairing(false)}
            onChanged={() => void load().catch(() => setError(t("error")))}
          />
        )}
        <AlertDialog
          open={confirm !== null}
          onOpenChange={(open) => {
            if (!open && !busy) setConfirm(null);
          }}
        >
          <AlertDialogContent className="max-h-[90dvh] overflow-y-auto bg-popover sm:rounded-[var(--radius-card)] md:max-w-[560px] max-md:inset-x-0 max-md:bottom-0 max-md:top-auto max-md:w-screen max-md:max-w-none max-md:translate-x-0 max-md:translate-y-0 max-md:rounded-t-[var(--radius-chrome-mobile)] max-md:rounded-b-none max-md:p-5 max-md:pb-4">
            <AlertDialogHeader className="text-left">
              <AlertDialogTitle>
                {phone ? t("phoneTitle", { name: phone.device_name }) : t(confirm === "all" ? "all" : "others")}
              </AlertDialogTitle>
              <AlertDialogDescription>
                {phone ? t("phoneRevokeHint") : t(confirm === "all" ? "confirmAll" : "confirmOthers")}
              </AlertDialogDescription>
            </AlertDialogHeader>
            {error && (
              <Text role={phone ? undefined : "alert"} tone="destructive">
                {error}
              </Text>
            )}
            {phone && (
              <Stack gap="3" className="rounded-md bg-muted p-3">
                <Flex gap="2" align="start">
                  <Checkbox
                    id="revoke-approved-tvs"
                    checked={cascade}
                    disabled={busy}
                    onChange={(event) => setCascade(event.target.checked)}
                  />
                  <Label htmlFor="revoke-approved-tvs">{t("alsoTvs", { count: approved.length })}</Label>
                </Flex>
                <List>
                  {approved.map((tv) => (
                    <ListItem key={tv.id}>
                      <Text size="sm">{tv.device_name}</Text>
                      <Text size="xs" tone="muted">
                        {lastShown(tv)}
                      </Text>
                    </ListItem>
                  ))}
                </List>
                <Text size="xs" tone="muted">
                  {t("keepTvsHint")}
                </Text>
              </Stack>
            )}
            <AlertDialogFooter className="gap-2 flex-col-reverse md:flex-row [&_button]:max-md:min-h-touch [&_button]:max-md:w-full">
              <Button variant="outline" disabled={busy} onClick={() => setConfirm(null)}>
                {t("cancel")}
              </Button>
              <Button
                variant="destructive"
                disabled={busy}
                onClick={() => {
                  if (phone)
                    void action(async () => {
                      const result = await sessionsApi.revokeSession(phone.id, cascade);
                      const wanted = cascade ? approved.map((tv) => tv.id) : [];
                      const failed = approved.filter(
                        (tv) => wanted.includes(tv.id) && !result.also_signed_out?.includes(tv.id),
                      );
                      if (failed.length) throw new Error("partial_sign_out");
                      toast.success(
                        t("signedOutPhone", { name: phone.device_name, count: result.also_signed_out?.length ?? 0 }),
                      );
                    });
                  else void action(() => sessionsApi.revokeSessions(confirm === "all"), confirm === "all");
                }}
              >
                {phone
                  ? t(cascade && approved.length ? "signOutCascade" : "signOutPhone", { count: approved.length })
                  : t("confirm")}
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </Stack>
    </Stack>
  );
}
