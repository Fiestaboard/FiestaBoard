import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Flex,
  Label,
  List,
  ListItem,
  Stack,
  Switch,
  Text,
} from "@fiestaboard/ui";
import { useCallback, useEffect, useState } from "react";

import { useRouter } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";
import { SessionApiError, type SessionList, sessionsApi, type SessionSummary } from "@/lib/api/sessions";
import { sessionDisplayName } from "@/lib/session-display-name";

export function SignedInDevices() {
  const t = useTranslations("signedInDevices");
  const router = useRouter();
  const [data, setData] = useState<SessionList | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<"others" | "all" | null>(null);
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
      else setError(t("error"));
    } finally {
      setBusy(false);
    }
  }
  function category(session: SessionSummary) {
    if (session.kind === "browser") return t("browser");
    if (session.client_id === "fiestaboard-tvos") return t("appleTV");
    if (session.client_id === "fiestaboard-androidtv") return t("androidTV");
    return t("legacy");
  }
  const date = (value: string) => new Date(value).toLocaleString();
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("title")}</CardTitle>
        <CardDescription>{t("description")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && (
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
            <List className="space-y-4">
              {data.sessions.map((session) => {
                const name = sessionDisplayName(session, t("browser"));
                return (
                  <ListItem key={session.id} aria-label={name} className="rounded-lg border p-4">
                    <Stack gap="2">
                      <Flex justify="between" align="center" gap="3" wrap>
                        <Text weight="semibold">{name}</Text>
                        {session.id === data.current_session_id && <Text size="sm">{t("current")}</Text>}
                      </Flex>
                      <Text size="sm">
                        {category(session)} · {t(session.method === "device_code" ? "codeMethod" : "passwordMethod")}
                      </Text>
                      {session.app_version && <Text size="sm">{t("version", { version: session.app_version })}</Text>}
                      <Text size="sm" tone="muted">
                        {t("created", { date: date(session.created_at) })}
                      </Text>
                      <Text size="sm" tone="muted">
                        {t("active", { date: date(session.last_active_at) })}
                      </Text>
                      <Text size="sm" tone="muted">
                        {t("expires", { date: date(session.expires_at) })}
                      </Text>
                      {session.kind === "legacy" && <Text size="sm">{t("legacyHint")}</Text>}
                      <Button
                        className="self-start"
                        variant="outline"
                        aria-label={t("revokeDevice", { name })}
                        disabled={busy}
                        onClick={() =>
                          void action(
                            () => sessionsApi.revokeSession(session.id),
                            session.id === data.current_session_id,
                          )
                        }
                      >
                        {t("revoke")}
                      </Button>
                    </Stack>
                  </ListItem>
                );
              })}
            </List>
            <Flex gap="3" wrap>
              <Button variant="outline" disabled={busy} onClick={() => setConfirm("others")}>
                {t("others")}
              </Button>
              <Button variant="destructive" disabled={busy} onClick={() => setConfirm("all")}>
                {t("all")}
              </Button>
            </Flex>
          </>
        )}
        <AlertDialog
          open={confirm !== null}
          onOpenChange={(open) => {
            if (!open && !busy) setConfirm(null);
          }}
        >
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>{t(confirm === "all" ? "all" : "others")}</AlertDialogTitle>
              <AlertDialogDescription>{t(confirm === "all" ? "confirmAll" : "confirmOthers")}</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <Button variant="outline" disabled={busy} onClick={() => setConfirm(null)}>
                {t("cancel")}
              </Button>
              <Button
                variant="destructive"
                disabled={busy}
                onClick={() => void action(() => sessionsApi.revokeSessions(confirm === "all"), confirm === "all")}
              >
                {t("confirm")}
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </CardContent>
    </Card>
  );
}
