/**
 * The "Account connection" section of a plugin's settings sheet.
 *
 * Renders only for plugins whose manifest declares an `oauth` block. The
 * platform runs the sign-in (src/oauth/service.py); this shows where it
 * stands and starts or ends it.
 *
 * Two flows, chosen by the plugin:
 *  - relay: the browser leaves for the provider and comes back through the
 *    static relay page (https://github.com/Fiestaboard/auth), which is told
 *    this board's address when the flow starts.
 *  - device: the user types a short code on another device while this polls.
 *
 * Layout: one quiet panel, in the same recipe as the sheet's "Demo page"
 * section, so the connection reads as one object among the plugin's other
 * sections rather than a page of its own. Inside it, top to bottom: the
 * status (a dot plus words, never colour alone), what that means, anything
 * in flight (a device code, or why the last one ended), then the action.
 *
 * Plugins where each user brings their own app with the provider get a
 * guided setup until they are connected: numbered steps to create the app,
 * the redirect URI to give it, and the Client ID field right here, so the
 * sign-in button can save it and start the sign-in in one press. The sheet
 * owns the form values (`appFields`) and leaves those fields out of the
 * general settings form below.
 */
import {
  Alert,
  AlertDescription,
  Button,
  Code,
  CopyButton,
  Field,
  Flex,
  Heading,
  Input,
  List,
  ListItem,
  SecretInput,
  Spinner,
  Stack,
  StatusDot,
  Text,
  TextLink,
} from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleAlert, ExternalLink, Info, TimerOff } from "lucide-react";
import { type ReactNode, useId, useState } from "react";
import { toast } from "sonner";

import { useTranslations } from "@/i18n/translations";
import { api, type OAuthConnection } from "@/lib/api";

export const OAUTH_CONNECTIONS_QUERY_KEY = ["oauth-connections"] as const;

/** How often to re-read the connection while a device code awaits approval. */
const DEVICE_POLL_INTERVAL_MS = 3000;

function findConnection(connections: OAuthConnection[] | undefined, pluginId: string): OAuthConnection | undefined {
  return connections?.find((connection) => connection.id === pluginId);
}

/**
 * The plugin settings the guided setup edits. The settings sheet owns the
 * values, so one save covers these and everything else on the form.
 */
export interface OAuthAppFields {
  /** The sheet's current form values. */
  values: Record<string, unknown>;
  /** Change one setting, by its key. */
  onChange: (key: string, value: string) => void;
  /** Save the plugin's settings without closing the sheet. Rejects when the save is refused. */
  save: () => Promise<void>;
  /** The plugin's own setup guide, when it has one. */
  setupGuideUrl?: string;
}

/** The settings keys the guided setup renders, so the sheet can leave them out of its form. */
export function oauthAppFieldKeys(connection: OAuthConnection | undefined): string[] {
  if (!connection?.user_app) return [];
  return [connection.client_id_setting, connection.client_secret_setting].filter((key): key is string => !!key);
}

export function findOAuthConnection(
  connections: OAuthConnection[] | undefined,
  pluginId: string,
): OAuthConnection | undefined {
  return findConnection(connections, pluginId);
}

export function OAuthConnectionSection({ pluginId, appFields }: { pluginId: string; appFields?: OAuthAppFields }) {
  const t = useTranslations("integrations.oauth");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
  const hintId = useId();
  const [isSavingApp, setIsSavingApp] = useState(false);

  const { data } = useQuery({
    queryKey: OAUTH_CONNECTIONS_QUERY_KEY,
    queryFn: api.listOAuthConnections,
    refetchInterval: (query) =>
      findConnection(query.state.data?.connections, pluginId)?.device?.status === "pending"
        ? DEVICE_POLL_INTERVAL_MS
        : false,
  });

  const connection = findConnection(data?.connections, pluginId);

  const connectMutation = useMutation({
    mutationFn: () => api.startOAuthConnection(pluginId),
    onSuccess: (start) => {
      if (start.flow === "relay") {
        // A full navigation: the provider's sign-in page replaces this app,
        // and the relay brings the browser back to /integrations.
        window.location.assign(start.authorization_url);
        return;
      }
      queryClient.invalidateQueries({ queryKey: OAUTH_CONNECTIONS_QUERY_KEY });
    },
    onError: (err) => {
      toast.error(t("toastConnectFailed", { error: err instanceof Error ? err.message : tCommon("unknownError") }));
    },
  });

  const disconnectMutation = useMutation({
    mutationFn: () => api.disconnectOAuthConnection(pluginId),
    onSuccess: () => {
      toast.success(t("toastDisconnected", { provider: connection?.provider_name ?? "" }));
      queryClient.invalidateQueries({ queryKey: OAUTH_CONNECTIONS_QUERY_KEY });
      queryClient.invalidateQueries({ queryKey: ["plugin-data", pluginId] });
    },
    onError: (err) => {
      toast.error(t("toastDisconnectFailed", { error: err instanceof Error ? err.message : tCommon("unknownError") }));
    },
  });

  if (!connection || !data) return null;

  const provider = connection.provider_name;
  const isConnected = connection.status === "connected";
  const needsReconnect = connection.status === "reauthorization_required";
  const usesRelay = connection.flows[0] === "relay";
  const device = connection.device;
  const awaitingCode = device?.status === "pending";

  // Guided setup: the user brings their own app, and is not connected yet.
  const showSetup = connection.user_app && !isConnected && !awaitingCode;
  const clientIdKey = connection.client_id_setting;
  const clientSecretKey = connection.client_secret_setting;
  const fieldValue = (key: string | null) => (key && appFields ? String(appFields.values[key] ?? "") : "");
  // With the field in this panel, a typed-but-unsaved Client ID is enough to
  // press the button: pressing it saves first.
  const canConnect = appFields && clientIdKey ? fieldValue(clientIdKey).trim() !== "" : connection.configured;

  const connect = async () => {
    if (connection.user_app && appFields && !isConnected) {
      setIsSavingApp(true);
      try {
        await appFields.save();
      } catch (err) {
        toast.error(t("toastSaveFailed", { error: err instanceof Error ? err.message : tCommon("unknownError") }));
        return;
      } finally {
        setIsSavingApp(false);
      }
    }
    connectMutation.mutate();
  };

  // The one line that says where things stand. It is a live region so the
  // change is announced when a device code is approved, or after Disconnect.
  const status = awaitingCode
    ? { dot: "info" as const, label: t("statusWaiting") }
    : isConnected
      ? { dot: "success" as const, label: t("statusConnected") }
      : needsReconnect
        ? { dot: "warning" as const, label: t("statusReconnect") }
        : { dot: "neutral" as const, label: t("statusDisconnected") };

  const description = isConnected
    ? t("connectedDescription", { provider })
    : needsReconnect
      ? t("reconnectDescription", { provider })
      : connection.user_app && !connection.configured
        ? t("setupIntro", { provider })
        : t("disconnectedDescription", { provider });

  const connectLabel = awaitingCode
    ? t("newCodeButton")
    : isConnected || needsReconnect
      ? t("reconnectButton")
      : t("connectButton", { provider });

  return (
    <Stack gap="3" data-testid="oauth-connection">
      <Heading level={4} size="sm" className="font-medium text-muted-foreground">
        {t("sectionTitle")}
      </Heading>

      <Stack gap="4" className="rounded-lg border bg-muted/30 p-4">
        <Stack gap="1">
          <Flex align="center" gap="2">
            <StatusDot status={status.dot} pulse={awaitingCode} />
            <Text as="span" weight="medium" role="status">
              {status.label}
            </Text>
          </Flex>
          <Text size="sm" tone="muted">
            {description}
          </Text>
        </Stack>

        {device && awaitingCode && (
          <Stack gap="3" className="rounded-md border bg-background p-3">
            <Text size="sm">{t.rich("deviceInstructions", { url: () => <DeviceLink device={device} /> })}</Text>
            <Flex align="center" gap="2" wrap>
              <Text
                as="span"
                className="select-all font-mono text-2xl font-semibold tracking-widest"
                data-testid="oauth-user-code"
              >
                {device.user_code}
              </Text>
              <CopyButton value={device.user_code} labels={{ copy: t("copyCode"), copied: t("copied") }} />
            </Flex>
            <Flex align="center" gap="2">
              <Spinner size="sm" label={null} />
              <Text size="xs" tone="muted">
                {t("deviceWaiting")}
              </Text>
            </Flex>
          </Stack>
        )}
        {device && !awaitingCode && (
          <Alert variant={device.status === "expired" ? "warning" : "destructive"}>
            {device.status === "expired" ? (
              <TimerOff className="size-4" aria-hidden="true" />
            ) : (
              <CircleAlert className="size-4" aria-hidden="true" />
            )}
            <AlertDescription>
              {device.status === "expired"
                ? t("deviceExpired")
                : device.status === "denied"
                  ? t("deviceDenied")
                  : t("deviceFailed", { detail: device.detail })}
            </AlertDescription>
          </Alert>
        )}

        {showSetup && (
          <List as="ol" marker="decimal" gap="4" className="text-sm" data-testid="oauth-setup-steps">
            <ListItem>
              <Stack gap="1.5">
                <Text as="span" weight="medium">
                  {t("setupStepCreate", { provider })}
                </Text>
                {(connection.app_setup_url || appFields?.setupGuideUrl) && (
                  <Flex gap="4" wrap>
                    {connection.app_setup_url && (
                      <SetupLink href={connection.app_setup_url}>{t("setupOpenDeveloperPage", { provider })}</SetupLink>
                    )}
                    {appFields?.setupGuideUrl && (
                      <SetupLink href={appFields.setupGuideUrl}>{t("setupOpenGuide")}</SetupLink>
                    )}
                  </Flex>
                )}
              </Stack>
            </ListItem>
            {usesRelay && (
              <ListItem>
                <Stack gap="1.5">
                  <Text as="span" weight="medium">
                    {t("setupStepRedirect")}
                  </Text>
                  <Flex align="center" gap="1" className="rounded-md border bg-background py-1 pl-2.5 pr-1">
                    <Code className="min-w-0 flex-1 break-all bg-transparent px-0 py-0">{data.redirect_uri}</Code>
                    <CopyButton
                      value={data.redirect_uri}
                      labels={{ copy: t("copyRedirectUri"), copied: t("copied") }}
                    />
                  </Flex>
                </Stack>
              </ListItem>
            )}
            {appFields && clientIdKey && (
              <ListItem>
                <Stack gap="2">
                  <Text as="span" weight="medium">
                    {t("setupStepDetails")}
                  </Text>
                  <Field label={t("clientIdLabel")}>
                    <Input
                      value={fieldValue(clientIdKey)}
                      onChange={(event) => appFields.onChange(clientIdKey, event.target.value)}
                      autoComplete="off"
                      spellCheck={false}
                      className="font-mono"
                    />
                  </Field>
                  {clientSecretKey && (
                    <Field label={t("clientSecretLabel")}>
                      <SecretInput
                        value={fieldValue(clientSecretKey)}
                        onChange={(event) => appFields.onChange(clientSecretKey, event.target.value)}
                        autoComplete="off"
                        showLabel={t("showSecret")}
                        hideLabel={t("hideSecret")}
                      />
                    </Field>
                  )}
                </Stack>
              </ListItem>
            )}
          </List>
        )}

        <Stack gap="2">
          <Flex gap="2" wrap>
            <Button
              size="sm"
              variant={isConnected || awaitingCode ? "outline" : "default"}
              loading={connectMutation.isPending || isSavingApp}
              disabled={!canConnect || disconnectMutation.isPending}
              aria-describedby={canConnect ? undefined : hintId}
              onClick={connect}
            >
              {connectLabel}
            </Button>
            {(isConnected || needsReconnect) && (
              <Button
                size="sm"
                variant="outline"
                loading={disconnectMutation.isPending}
                disabled={connectMutation.isPending || isSavingApp}
                onClick={() => disconnectMutation.mutate()}
              >
                {t("disconnectButton")}
              </Button>
            )}
          </Flex>
          {!canConnect && (
            <Flex align="start" gap="1.5" id={hintId}>
              <Info className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
              <Text size="xs" tone="muted">
                {t("needsClientId")}
              </Text>
            </Flex>
          )}
          {/* What the trip back looks like, for anyone about to make it. */}
          {usesRelay && !isConnected && (
            <Text size="xs" tone="muted">
              {t("relayHint")}
            </Text>
          )}
        </Stack>
      </Stack>
    </Stack>
  );
}

function SetupLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <TextLink href={href} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1">
      {children}
      <ExternalLink className="size-3.5" aria-hidden="true" />
    </TextLink>
  );
}

function DeviceLink({ device }: { device: NonNullable<OAuthConnection["device"]> }) {
  return (
    <TextLink
      href={device.verification_uri_complete || device.verification_uri}
      target="_blank"
      rel="noopener noreferrer"
    >
      {device.verification_uri}
    </TextLink>
  );
}

/** What the relay callback put in the URL on the way back to /integrations. */
export interface OAuthReturn {
  outcome: "connected" | "error";
  pluginId: string | null;
  reason: string | null;
}

const KNOWN_REASONS = ["invalid_state", "expired", "access_denied", "exchange_failed", "provider_error"] as const;

export function readOAuthReturn(params: URLSearchParams): OAuthReturn | null {
  const outcome = params.get("oauth");
  if (outcome !== "connected" && outcome !== "error") return null;
  return { outcome, pluginId: params.get("plugin"), reason: params.get("reason") };
}

/** The translation key (under `integrations.oauth`) explaining a failed return. */
export function oauthReturnErrorKey(reason: string | null): string {
  const known = (KNOWN_REASONS as readonly string[]).includes(reason ?? "");
  return `returnError.${known ? reason : "provider_error"}`;
}
