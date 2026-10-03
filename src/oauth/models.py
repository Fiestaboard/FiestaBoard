"""Wire models for the ``/oauth`` endpoints.

None of these carries a token, a client secret, a device code or a PKCE
verifier. They describe a connection; they are never the credentials for one.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Flow = Literal["relay", "device", "key_exchange", "plex_pin"]


class OAuthDeviceStatus(BaseModel):
    """A device-code sign-in in progress."""

    status: Literal["pending", "expired", "denied", "failed"]
    user_code: str = Field(description="The code the user types at verification_uri.")
    verification_uri: str
    verification_uri_complete: str = Field(
        default="", description="verification_uri with the code filled in, when the provider offers one."
    )
    expires_at: float = Field(description="Epoch seconds after which the code stops working.")
    detail: str = Field(default="", description="The provider's error code when status is 'failed'.")


class OAuthConnection(BaseModel):
    """One plugin's OAuth connection and whether it is currently usable."""

    id: str = Field(
        description=(
            "The plugin's key: 'plugin_id', or 'plugin_id:label' for a named instance. "
            "'ai.<provider id>' for a FiestaBot AI provider."
        )
    )
    kind: Literal["plugin", "ai"] = Field(
        default="plugin",
        description="'ai' for a FiestaBot AI provider's sign-in; the Integrations page lists 'plugin'.",
    )
    plugin_id: str
    instance_label: str | None = None
    plugin_name: str
    provider_name: str
    flows: list[Flow] = Field(description="Flows the plugin supports, preferred first.")
    configured: bool = Field(description="Whether a client ID is available, so a flow can start.")
    user_app: bool = Field(
        description=(
            "Whether the user registers their own app with the provider and enters its client ID. "
            "False when the plugin brings its own app, so there is nothing for the user to set up."
        )
    )
    shared_app: bool = Field(
        default=False,
        description=(
            "Whether the plugin ships its own client ID, so sign-in works without the user's own app. "
            "With user_app also true, the user's own app is an optional override."
        ),
    )
    client_id_setting: str | None = Field(
        default=None, description="The plugin setting that holds the user's client ID, when the plugin offers one."
    )
    client_secret_setting: str | None = Field(
        default=None, description="The plugin setting that holds the user's client secret, when the plugin offers one."
    )
    app_setup_url: str = Field(default="", description="The provider's developer page, where a user creates their app.")
    status: Literal["connected", "disconnected", "reauthorization_required"]
    status_reason: str = Field(
        default="",
        description=(
            "Why reconnecting is needed, when status is reauthorization_required: "
            "'refresh_refused' or 'rejected' (the provider stopped accepting the sign-in)."
        ),
    )
    scopes: list[str] = Field(description="Scopes granted when connected, otherwise the scopes that will be requested.")
    expires_at: float | None = Field(default=None, description="Epoch seconds when the access token expires.")
    connected_at: float | None = Field(default=None, description="Epoch seconds when the connection was made.")
    device: OAuthDeviceStatus | None = None


class OAuthConnectionList(BaseModel):
    """Every installed plugin that declares an OAuth connection."""

    connections: list[OAuthConnection]
    redirect_uri: str = Field(description="The redirect URI to register with a provider when creating an OAuth app.")


class OAuthAuthorizeRequest(BaseModel):
    """Start connecting. Omit ``flow`` to use the plugin's preferred one."""

    flow: Flow | None = None
    board_url: str | None = Field(
        default=None,
        max_length=512,
        description=(
            "The address the user is browsing this board at, such as http://192.168.1.50:4420. "
            "Required for the relay flow: it is where the sign-in returns to."
        ),
    )
    headless: bool = Field(
        default=False,
        description="key_exchange: sign in without a redirect back; the user pastes the code the provider shows.",
    )


class OAuthAuthorizationStart(BaseModel):
    """How to carry a just-started flow forward."""

    flow: Flow
    authorization_url: str = Field(default="", description="relay: send the browser here.")
    device: OAuthDeviceStatus | None = Field(default=None, description="device: show this code to the user.")
    paste_expected: bool = Field(
        default=False, description="The sign-in will not come back on its own: show the paste box straight away."
    )
    paste_hint: str = Field(default="", description="What to paste, when the provider needs explaining.")


class OAuthCompleteRequest(BaseModel):
    """Finish a sign-in from what the provider showed the user."""

    pasted: str = Field(
        max_length=4096, description="The whole address the sign-in ended on, or the code the provider showed."
    )
