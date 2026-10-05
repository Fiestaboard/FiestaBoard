// OAuth domain: plugin sign-in connections (status, start, disconnect).
//
// Mirrors src/oauth/models.py. Nothing here ever carries a token — these
// describe a connection, they are not the credentials for one.

import { getBasePath } from "../base-path";
import { fetchApi } from "./core";

export type OAuthFlow = "relay" | "device" | "key_exchange" | "plex_pin";

/** A device-code sign-in in progress. */
export interface OAuthDeviceStatus {
  status: "pending" | "expired" | "denied" | "failed";
  /** The code the user types at `verification_uri`. */
  user_code: string;
  verification_uri: string;
  /** `verification_uri` with the code filled in, when the provider offers one. */
  verification_uri_complete: string;
  /** Epoch seconds after which the code stops working. */
  expires_at: number;
  /** The provider's error code when `status` is `"failed"`. */
  detail: string;
}

export interface OAuthConnection {
  /** The plugin's key: `plugin_id`, or `plugin_id:label` for a named instance. */
  id: string;
  /** Who the connection is for: a plugin, or one of FiestaBot's AI providers (`ai.<provider id>`). */
  kind?: "plugin" | "ai";
  plugin_id: string;
  instance_label: string | null;
  plugin_name: string;
  provider_name: string;
  /** Flows the plugin supports, preferred first. */
  flows: OAuthFlow[];
  /** Whether a client ID is available, so a flow can start. */
  configured: boolean;
  /**
   * Whether the user registers their own app with the provider and enters its
   * client ID. False when the plugin brings its own app: nothing to set up.
   */
  user_app: boolean;
  /**
   * Whether the plugin ships its own client ID, so sign-in works without the
   * user's own app. With `user_app` too, their own app is an optional override.
   */
  shared_app: boolean;
  /** The plugin settings that hold the user's client ID and secret, when the plugin offers them. */
  client_id_setting: string | null;
  client_secret_setting: string | null;
  /** The provider's developer page, where a user creates their app. Empty when the plugin gives none. */
  app_setup_url: string;
  status: "connected" | "disconnected" | "reauthorization_required";
  /** Why reconnecting is needed: `"rejected"` (the provider refused the token) or `"refresh_refused"`. */
  status_reason?: string;
  scopes: string[];
  expires_at: number | null;
  connected_at: number | null;
  device: OAuthDeviceStatus | null;
  /**
   * The provider's redirect cannot reach this board (ChatGPT's loopback-only
   * redirect): every sign-in ends with the user pasting the address it landed
   * on. Known before the sign-in starts, so the provider can open in a new
   * tab from the click itself.
   */
  paste_expected?: boolean;
}

export interface OAuthConnectionList {
  connections: OAuthConnection[];
  /** The redirect URI to register with a provider when creating an OAuth app. */
  redirect_uri: string;
}

export interface OAuthAuthorizationStart {
  flow: OAuthFlow;
  /** relay: send the browser here. */
  authorization_url: string;
  /** device: show this code to the user. */
  device: OAuthDeviceStatus | null;
  /** The sign-in will not come back on its own: show the paste box straight away. */
  paste_expected?: boolean;
  /** What to paste, when the provider needs explaining. */
  paste_hint?: string;
}

/**
 * The address this board is being browsed at, path prefix included.
 *
 * Only the browser knows it: the same board may be reached by IP address, by
 * an mDNS name, or under a Home Assistant ingress path. It is sent when a
 * relay sign-in starts so the relay page can send the browser back here.
 */
export function boardAddress(): string {
  if (typeof window === "undefined") return "";
  return `${window.location.origin}${getBasePath()}`;
}

export const oauthApi = {
  listOAuthConnections: () => fetchApi<OAuthConnectionList>("/oauth/connections"),

  /** `headless`: sign in without a redirect back (key_exchange); the user pastes the code the provider shows. */
  startOAuthConnection: (connectionId: string, options: { headless?: boolean } = {}) =>
    fetchApi<OAuthAuthorizationStart>(`/oauth/connections/${encodeURIComponent(connectionId)}/authorize`, {
      method: "POST",
      body: JSON.stringify(
        options.headless ? { board_url: boardAddress(), headless: true } : { board_url: boardAddress() },
      ),
    }),

  /** Finish a sign-in from the address (or bare code) the provider showed, when it did not come back on its own. */
  completeOAuthConnection: (connectionId: string, pasted: string) =>
    fetchApi<OAuthConnection>(`/oauth/connections/${encodeURIComponent(connectionId)}/complete`, {
      method: "POST",
      body: JSON.stringify({ pasted }),
    }),

  disconnectOAuthConnection: (connectionId: string) =>
    fetchApi<OAuthConnection>(`/oauth/connections/${encodeURIComponent(connectionId)}`, { method: "DELETE" }),
};
