// OAuth domain: plugin sign-in connections (status, start, disconnect).
//
// Mirrors src/oauth/models.py. Nothing here ever carries a token — these
// describe a connection, they are not the credentials for one.

import { getBasePath } from "../base-path";
import { fetchApi } from "./core";

export type OAuthFlow = "relay" | "device";

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
  status: "connected" | "disconnected" | "reauthorization_required";
  scopes: string[];
  expires_at: number | null;
  connected_at: number | null;
  device: OAuthDeviceStatus | null;
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

  startOAuthConnection: (connectionId: string) =>
    fetchApi<OAuthAuthorizationStart>(`/oauth/connections/${encodeURIComponent(connectionId)}/authorize`, {
      method: "POST",
      body: JSON.stringify({ board_url: boardAddress() }),
    }),

  disconnectOAuthConnection: (connectionId: string) =>
    fetchApi<OAuthConnection>(`/oauth/connections/${encodeURIComponent(connectionId)}`, { method: "DELETE" }),
};
