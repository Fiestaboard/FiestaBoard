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
 */
import { Badge, Box, Button, Code as CodeChip, Flex, Heading, Stack, Text, TextLink } from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { useTranslations } from "@/i18n/translations";
import { api, type OAuthConnection } from "@/lib/api";

export const OAUTH_CONNECTIONS_QUERY_KEY = ["oauth-connections"] as const;

/** How often to re-read the connection while a device code awaits approval. */
const DEVICE_POLL_INTERVAL_MS = 3000;

function findConnection(connections: OAuthConnection[] | undefined, pluginId: string): OAuthConnection | undefined {
  return connections?.find((connection) => connection.id === pluginId);
}

export function OAuthConnectionSection({ pluginId }: { pluginId: string }) {
  const t = useTranslations("integrations.oauth");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();

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
  const isBusy = connectMutation.isPending || disconnectMutation.isPending;

  return (
    <Stack gap="3" data-testid="oauth-connection">
      <Flex align="center" justify="between" gap="2">
        <Heading level={4} size="sm" className="font-medium text-muted-foreground">
          {t("sectionTitle")}
        </Heading>
        <Badge variant={isConnected ? "default" : needsReconnect ? "destructive" : "outline"} className="text-[10px]">
          {isConnected ? t("statusConnected") : needsReconnect ? t("statusReconnect") : t("statusDisconnected")}
        </Badge>
      </Flex>

      <Text size="sm" tone="muted">
        {isConnected
          ? t("connectedDescription", { provider })
          : needsReconnect
            ? t("reconnectDescription", { provider })
            : t("disconnectedDescription", { provider })}
      </Text>

      {!connection.configured && (
        <Text size="xs" tone="warning" role="status">
          {t("needsClientId")}
        </Text>
      )}

      {device && awaitingCode && (
        <Box className="rounded-md border p-3" role="status" aria-live="polite">
          <Stack gap="2">
            <Text size="sm">{t.rich("deviceInstructions", { url: () => <DeviceLink device={device} /> })}</Text>
            <Text as="p" className="font-mono text-2xl font-semibold tracking-widest" data-testid="oauth-user-code">
              {device.user_code}
            </Text>
            <Text size="xs" tone="muted">
              {t("deviceWaiting")}
            </Text>
          </Stack>
        </Box>
      )}
      {device && !awaitingCode && (
        <Text size="xs" tone="warning" role="alert">
          {device.status === "expired"
            ? t("deviceExpired")
            : device.status === "denied"
              ? t("deviceDenied")
              : t("deviceFailed", { detail: device.detail })}
        </Text>
      )}

      <Flex gap="2" wrap>
        <Button
          size="sm"
          variant={isConnected || awaitingCode ? "outline" : "default"}
          disabled={!connection.configured || isBusy}
          onClick={() => connectMutation.mutate()}
        >
          {connectMutation.isPending
            ? t("connecting")
            : awaitingCode
              ? t("newCodeButton")
              : isConnected || needsReconnect
                ? t("reconnectButton")
                : t("connectButton", { provider })}
        </Button>
        {(isConnected || needsReconnect) && (
          <Button size="sm" variant="outline" disabled={isBusy} onClick={() => disconnectMutation.mutate()}>
            {t("disconnectButton")}
          </Button>
        )}
      </Flex>

      {/* Only useful while setting up: once connected it is noise. */}
      {usesRelay && !isConnected && (
        <Stack gap="1">
          <Text size="xs" tone="muted">
            {t("relayHint")}
          </Text>
          <Text size="xs" tone="muted">
            {t("redirectUriHint", { provider })} <CodeChip className="break-all">{data.redirect_uri}</CodeChip>
          </Text>
        </Stack>
      )}
    </Stack>
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
