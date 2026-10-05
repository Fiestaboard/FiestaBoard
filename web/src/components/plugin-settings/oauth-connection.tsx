/**
 * The "Account connection" section of a plugin's settings sheet.
 *
 * Renders only for plugins whose manifest declares an `oauth` block. The
 * platform runs the sign-in (src/oauth/service.py); this shows where it
 * stands and starts or ends it.
 *
 * Flows, chosen by the plugin (or an AI sign-in preset):
 *  - relay: the browser leaves for the provider and comes back through the
 *    static relay page (https://github.com/Fiestaboard/auth), which is told
 *    this board's address when the flow starts.
 *  - key_exchange: like relay (OpenRouter), or headless: the provider shows a
 *    code and the user pastes it here.
 *  - device: the user types a short code on another device while this polls.
 *  - plex_pin: the provider opens in another tab and this polls; no code.
 *
 * When a sign-in may not find its own way back (the relay could not reach
 * this board, or the provider only redirects to a loopback address), the
 * panel offers a paste box: the user copies the address they landed on, or
 * the code they were shown, and the board finishes the sign-in with it.
 *
 * A connection whose sign-in can never come back (`paste_expected`, ChatGPT's
 * loopback-only redirect) makes that paste the plan rather than a rescue.
 * Pressing sign-in opens nothing: this tab shows a "Finish signing in" step
 * first, with the provider behind a plain link (step 1), the warning that its
 * tab will end on a page that cannot load and that this is expected, and the
 * paste box. The user reads all of it before anything leaves this tab. (A tab
 * opened in the click itself took focus at once, so those steps rendered in a
 * tab the user had already left, and they never came back to paste.) When
 * the user returns to this tab, the paste field takes the cursor.
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
 *
 * A plugin that ships its own app and also lets users swap in theirs
 * (`shared_app` with `user_app`) leads with a plain sign-in instead: the
 * same setup steps sit in a collapsed, optional "Use your own app" section,
 * open from the start only when the user already saved an app of their own.
 */
import {
  Alert,
  AlertDescription,
  Box,
  Button,
  Code,
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
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
import { CheckCircle2, CircleAlert, ExternalLink, Info, TimerOff } from "lucide-react";
import { type FormEvent, type ReactNode, type Ref, useEffect, useId, useRef, useState } from "react";
import { toast } from "sonner";

import { useTranslations } from "@/i18n/translations";
import { api, type OAuthConnection } from "@/lib/api";

export const OAUTH_CONNECTIONS_QUERY_KEY = ["oauth-connections"] as const;

/** FiestaBot AI providers' connection ids: `ai.<provider id>` (src/oauth/service.py). */
const AI_CONNECTION_PREFIX = "ai.";

/** How often to re-read the connection while a device code awaits approval. */
const DEVICE_POLL_INTERVAL_MS = 3000;

/** How long after a sign-in starts the paste box stays on offer. */
const PASTE_WINDOW_MS = 10 * 60 * 1000;

function findConnection(connections: OAuthConnection[] | undefined, id: string): OAuthConnection | undefined {
  return connections?.find((connection) => connection.id === id);
}

/**
 * A sign-in that may need finishing by hand. Kept in sessionStorage as well
 * as state: a relay sign-in leaves this page, and the user comes back to it
 * (a fresh load) with the address they need to paste.
 */
interface PasteOffer {
  /** Epoch ms the sign-in started (this browser's clock: only for expiring the offer). */
  started: number;
  /**
   * The board's `connected_at` when the sign-in started. A different one
   * later means the sign-in came back. Compared with the board's own stamp,
   * never this browser's clock, which may not agree with the board's.
   */
  connectedAt?: number | null;
  /** Open the box straight away: the sign-in cannot come back on its own. */
  open: boolean;
  /** What to paste, when the provider needs explaining. */
  hint: string;
  /** The provider's page, to open again from the box. Empty when it was a same-tab redirect. */
  url: string;
}

const pasteStorageKey = (connectionId: string) => `fiestaboard.oauth.paste.${connectionId}`;

function readPasteOffer(connectionId: string): PasteOffer | null {
  try {
    const raw = window.sessionStorage.getItem(pasteStorageKey(connectionId));
    if (!raw) return null;
    const offer = JSON.parse(raw) as PasteOffer;
    if (typeof offer?.started !== "number" || Date.now() - offer.started > PASTE_WINDOW_MS) {
      window.sessionStorage.removeItem(pasteStorageKey(connectionId));
      return null;
    }
    return offer;
  } catch {
    return null;
  }
}

function writePasteOffer(connectionId: string, offer: PasteOffer | null) {
  try {
    if (offer) window.sessionStorage.setItem(pasteStorageKey(connectionId), JSON.stringify(offer));
    else window.sessionStorage.removeItem(pasteStorageKey(connectionId));
  } catch {
    // Private windows and blocked storage: the offer lives in state only.
  }
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

/** A plugin's connection. FiestaBot's AI connections (`kind: "ai"`) are never a plugin's. */
export function findOAuthConnection(
  connections: OAuthConnection[] | undefined,
  pluginId: string,
): OAuthConnection | undefined {
  const connection = findConnection(connections, pluginId);
  return connection?.kind === "ai" ? undefined : connection;
}

export function OAuthConnectionSection({ pluginId, appFields }: { pluginId: string; appFields?: OAuthAppFields }) {
  return <OAuthConnectionPanel connectionId={pluginId} appFields={appFields} />;
}

/**
 * One connection's panel, by its id: a plugin's (`plugin_id` or
 * `plugin_id:label`) or a FiestaBot AI provider's (`ai.<provider id>`).
 */
export function OAuthConnectionPanel({
  connectionId,
  appFields,
  title,
}: {
  connectionId: string;
  appFields?: OAuthAppFields;
  /** The panel's heading. Defaults to "Account connection". */
  title?: string;
}) {
  const t = useTranslations("integrations.oauth");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
  const hintId = useId();
  const [isSavingApp, setIsSavingApp] = useState(false);
  const [pasteOffer, setPasteOfferState] = useState<PasteOffer | null>(() => readPasteOffer(connectionId));
  const [pasteOpen, setPasteOpen] = useState(() => pasteOffer?.open ?? false);
  const [pasted, setPasted] = useState("");
  // null until the user toggles it: then it follows whether they saved an app.
  const [ownAppToggled, setOwnAppToggled] = useState<boolean | null>(null);
  const [justFinished, setJustFinished] = useState(false);
  const finishTitleId = useId();
  const pasteInputRef = useRef<HTMLInputElement>(null);
  const openProviderRef = useRef<HTMLAnchorElement>(null);
  // Bumped when a paste-only sign-in starts: opening the provider is the next
  // thing to do, so its link takes focus.
  const [focusOpenRequest, setFocusOpenRequest] = useState(0);
  useEffect(() => {
    if (focusOpenRequest) openProviderRef.current?.focus();
  }, [focusOpenRequest]);
  // Coming back to this tab from the provider's means coming back to paste:
  // the finish step's field (rendered only while that step shows) takes the
  // cursor, unless something is already in it.
  useEffect(() => {
    const onVisible = () => {
      const field = pasteInputRef.current;
      if (document.visibilityState === "visible" && field && !field.value) field.focus();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, []);

  const setPasteOffer = (offer: PasteOffer | null) => {
    writePasteOffer(connectionId, offer);
    setPasteOfferState(offer);
    if (offer?.open) setPasteOpen(true);
  };

  const { data } = useQuery({
    queryKey: OAUTH_CONNECTIONS_QUERY_KEY,
    queryFn: api.listOAuthConnections,
    refetchInterval: (query) =>
      findConnection(query.state.data?.connections, connectionId)?.device?.status === "pending"
        ? DEVICE_POLL_INTERVAL_MS
        : false,
  });

  const connection = findConnection(data?.connections, connectionId);

  const refreshAfterChange = () => {
    queryClient.invalidateQueries({ queryKey: OAUTH_CONNECTIONS_QUERY_KEY });
    queryClient.invalidateQueries({ queryKey: ["plugin-data", connectionId] });
    if (connectionId.startsWith(AI_CONNECTION_PREFIX)) {
      // A FiestaBot provider's sign-in changes what it can list and whether
      // the chat panel can use it: refresh both now, not when the cache ages.
      queryClient.invalidateQueries({ queryKey: ["ai-settings"] });
      queryClient.invalidateQueries({
        queryKey: ["ai-provider-models", connectionId.slice(AI_CONNECTION_PREFIX.length)],
      });
    }
  };

  const connectMutation = useMutation({
    mutationFn: (options: { headless?: boolean }) =>
      api.startOAuthConnection(connectionId, options.headless ? { headless: true } : {}),
    onSuccess: (start) => {
      setJustFinished(false);
      // Anything that goes by way of the provider's page may need finishing
      // by hand, so the paste box is on offer from now on.
      if (start.flow !== "device" && start.flow !== "plex_pin") {
        setPasteOffer({
          started: Date.now(),
          connectedAt: connection?.connected_at ?? null,
          open: !!start.paste_expected,
          hint: start.paste_hint ?? "",
          url: start.paste_expected ? start.authorization_url : "",
        });
      }
      if (start.authorization_url && start.paste_expected && connection?.paste_expected) {
        // The finish step's link opens the provider, once its steps are read.
        setFocusOpenRequest((n) => n + 1);
      } else if (start.authorization_url) {
        if (start.paste_expected || start.flow === "plex_pin") {
          // The user comes back to this tab (to paste, or while it polls),
          // so the provider opens in another one.
          window.open(start.authorization_url, "_blank", "noopener,noreferrer");
        } else {
          // A full navigation: the provider's sign-in page replaces this app,
          // and the relay brings the browser back to /integrations.
          window.location.assign(start.authorization_url);
          return;
        }
      }
      queryClient.invalidateQueries({ queryKey: OAUTH_CONNECTIONS_QUERY_KEY });
    },
    onError: (err) => {
      toast.error(t("toastConnectFailed", { error: err instanceof Error ? err.message : tCommon("unknownError") }));
    },
  });

  const completeMutation = useMutation({
    mutationFn: (text: string) => api.completeOAuthConnection(connectionId, text),
    onSuccess: () => {
      setPasteOffer(null);
      setPasteOpen(false);
      setPasted("");
      setJustFinished(true);
      toast.success(t("toastConnected"));
      refreshAfterChange();
    },
  });

  const disconnectMutation = useMutation({
    mutationFn: () => api.disconnectOAuthConnection(connectionId),
    onSuccess: () => {
      setJustFinished(false);
      toast.success(t("toastDisconnected", { provider: connection?.provider_name ?? "" }));
      refreshAfterChange();
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
  const returnsByRelay = usesRelay || connection.flows[0] === "key_exchange";
  const offersHeadless = connection.flows.includes("key_exchange");
  const device = connection.device;
  const awaitingCode = device?.status === "pending";
  // plex_pin: approval happens in the provider's tab; there is no code to type.
  const awaitingApproval = awaitingCode && !device?.user_code;
  // A sign-in that completed after the offer was made needs no paste.
  const connectedSinceOffer =
    isConnected &&
    (pasteOffer && pasteOffer.connectedAt !== undefined
      ? connection.connected_at != null && connection.connected_at !== pasteOffer.connectedAt
      : (connection.connected_at ?? 0) * 1000 >= (pasteOffer?.started ?? 0));
  const showPaste = !!pasteOffer && !awaitingCode && !connectedSinceOffer;
  // The provider's redirect cannot reach this board: pasting is the plan, not a rescue.
  const finishesByPaste = !!connection.paste_expected;
  const showFinishStep = finishesByPaste && showPaste;

  // Guided setup: the user brings their own app, and is not connected yet.
  const showSetup = connection.user_app && !isConnected && !awaitingCode;
  const clientIdKey = connection.client_id_setting;
  const clientSecretKey = connection.client_secret_setting;
  const fieldValue = (key: string | null) => (key && appFields ? String(appFields.values[key] ?? "") : "");
  const hasOwnClientId = fieldValue(clientIdKey).trim() !== "";
  // The plugin's shipped app signs in; the user's own app is an optional override.
  const ownAppOptional = connection.shared_app && connection.user_app;
  const ownAppOpen = ownAppToggled ?? hasOwnClientId;
  // With the field in this panel, a typed-but-unsaved Client ID is enough to
  // press the button: pressing it saves first.
  const canConnect = ownAppOptional
    ? connection.configured || hasOwnClientId
    : appFields && clientIdKey
      ? hasOwnClientId
      : connection.configured;
  // Save the app fields before signing in, unless they sit untouched in the
  // closed optional section (nothing there to save).
  const savesAppFirst = connection.user_app && !!appFields && !isConnected && (!ownAppOptional || ownAppOpen);

  const connect = async () => {
    if (savesAppFirst && appFields) {
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
    connectMutation.mutate({});
  };

  const submitPasted = (event: FormEvent) => {
    event.preventDefault();
    const text = pasted.trim();
    if (text) completeMutation.mutate(text);
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
      ? connection.status_reason === "rejected"
        ? t("rejectedDescription", { provider })
        : t("reconnectDescription", { provider })
      : connection.user_app && !connection.configured && !ownAppOptional
        ? t("setupIntro", { provider })
        : t("disconnectedDescription", { provider });

  const connectLabel = awaitingApproval
    ? t("startAgainButton")
    : awaitingCode
      ? t("newCodeButton")
      : isConnected || needsReconnect
        ? t("reconnectButton")
        : t("connectButton", { provider });

  const setupSteps = (
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
              {appFields?.setupGuideUrl && <SetupLink href={appFields.setupGuideUrl}>{t("setupOpenGuide")}</SetupLink>}
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
              <CopyButton value={data.redirect_uri} labels={{ copy: t("copyRedirectUri"), copied: t("copied") }} />
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
  );

  return (
    <Stack gap="3" data-testid="oauth-connection">
      <Heading level={4} size="sm" className="font-medium text-muted-foreground">
        {title ?? t("sectionTitle")}
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

        {justFinished && isConnected && (
          <Alert variant="success" politeness="polite">
            <CheckCircle2 className="size-4" aria-hidden="true" />
            <AlertDescription>{t("finishDone", { provider })}</AlertDescription>
          </Alert>
        )}

        {device && awaitingApproval && (
          <Flex align="center" gap="2" className="rounded-md border bg-background p-3">
            <Spinner size="sm" label={null} />
            <Text size="sm">{t("approvalWaiting", { provider })}</Text>
          </Flex>
        )}
        {device && awaitingCode && !awaitingApproval && (
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

        {showSetup && !ownAppOptional && setupSteps}
        {showSetup && ownAppOptional && (
          <Collapsible open={ownAppOpen} onOpenChange={setOwnAppToggled}>
            <CollapsibleTrigger asChild>
              <Button size="sm" variant="link" className="h-auto px-0">
                {t("ownAppToggle")}
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <Stack gap="3" className="pt-2">
                <Text size="sm" tone="muted">
                  {t("ownAppDescription", { provider })}
                </Text>
                {setupSteps}
              </Stack>
            </CollapsibleContent>
          </Collapsible>
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
          {offersHeadless && !isConnected && !awaitingCode && (
            <Button
              size="sm"
              variant="link"
              className="h-auto self-start px-0"
              disabled={connectMutation.isPending || disconnectMutation.isPending}
              onClick={() => connectMutation.mutate({ headless: true })}
            >
              {t("headlessButton")}
            </Button>
          )}
          {!canConnect && (
            <Flex align="start" gap="1.5" id={hintId}>
              <Info className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
              <Text size="xs" tone="muted">
                {t("needsClientId")}
              </Text>
            </Flex>
          )}
          {/* What the trip back looks like, for anyone about to make it. */}
          {returnsByRelay && !isConnected && !finishesByPaste && (
            <Text size="xs" tone="muted">
              {t("relayHint")}
            </Text>
          )}
          {finishesByPaste && !isConnected && !showFinishStep && (
            <Text size="xs" tone="muted">
              {t("newTabHint", { provider })}
            </Text>
          )}
        </Stack>

        {showFinishStep && pasteOffer && (
          <Stack
            gap="3"
            role="group"
            aria-labelledby={finishTitleId}
            className="rounded-md border bg-background p-3"
            data-testid="oauth-finish-step"
          >
            <Text id={finishTitleId} weight="medium">
              {t("finishTitle")}
            </Text>
            <List as="ol" marker="decimal" gap="2" className="text-sm">
              <ListItem>
                <Stack gap="1" className="items-start">
                  {pasteOffer.url && (
                    <SetupLink href={pasteOffer.url} linkRef={openProviderRef}>
                      {t("finishOpenLink", { provider })}
                    </SetupLink>
                  )}
                  <Text as="span">{t("finishStepSignIn", { provider })}</Text>
                </Stack>
              </ListItem>
              <ListItem>{t("finishStepCantConnect")}</ListItem>
              <ListItem>{t("finishStepCopy")}</ListItem>
            </List>
            <Box as="form" onSubmit={submitPasted}>
              <Stack gap="2">
                <Field
                  label={t("finishPasteLabel", { provider })}
                  description={t("finishPasteDescription")}
                  error={
                    completeMutation.error ? errorMessage(completeMutation.error, tCommon("unknownError")) : undefined
                  }
                >
                  <Input
                    ref={pasteInputRef}
                    value={pasted}
                    onChange={(event) => {
                      setPasted(event.target.value);
                      if (completeMutation.isError) completeMutation.reset();
                    }}
                    autoComplete="off"
                    spellCheck={false}
                    className="font-mono"
                  />
                </Field>
                <Flex align="center" gap="3" wrap>
                  <Button type="submit" size="sm" loading={completeMutation.isPending} disabled={!pasted.trim()}>
                    {t("pasteSubmit")}
                  </Button>
                </Flex>
              </Stack>
            </Box>
          </Stack>
        )}

        {showPaste && !finishesByPaste && pasteOffer && (
          <Collapsible open={pasteOpen} onOpenChange={setPasteOpen}>
            <CollapsibleTrigger asChild>
              <Button size="sm" variant="link" className="h-auto px-0">
                {t("pasteToggle")}
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <Box as="form" onSubmit={submitPasted} className="pt-2">
                <Stack gap="2">
                  <Field
                    label={t("pasteLabel")}
                    description={pasteOffer.hint || t("pasteDescription")}
                    error={
                      completeMutation.error ? errorMessage(completeMutation.error, tCommon("unknownError")) : undefined
                    }
                  >
                    <Input
                      value={pasted}
                      onChange={(event) => {
                        setPasted(event.target.value);
                        if (completeMutation.isError) completeMutation.reset();
                      }}
                      autoComplete="off"
                      spellCheck={false}
                      className="font-mono"
                    />
                  </Field>
                  <Flex align="center" gap="3" wrap>
                    <Button type="submit" size="sm" loading={completeMutation.isPending} disabled={!pasted.trim()}>
                      {t("pasteSubmit")}
                    </Button>
                    {pasteOffer.url && <SetupLink href={pasteOffer.url}>{t("pasteOpenAgain")}</SetupLink>}
                  </Flex>
                </Stack>
              </Box>
            </CollapsibleContent>
          </Collapsible>
        )}
      </Stack>
    </Stack>
  );
}

function errorMessage(err: unknown, fallback: string): string {
  return err instanceof Error && err.message ? err.message : fallback;
}

function SetupLink({
  href,
  children,
  linkRef,
}: {
  href: string;
  children: ReactNode;
  linkRef?: Ref<HTMLAnchorElement>;
}) {
  return (
    <TextLink
      ref={linkRef}
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1"
    >
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
