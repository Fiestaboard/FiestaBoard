"""Wire models for the ``/oauth`` endpoints.

None of these carries a token, a client secret, a device code or a PKCE
verifier. They describe a connection; they are never the credentials for one.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Flow = Literal["relay", "device"]


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

    id: str = Field(description="The plugin's key: 'plugin_id', or 'plugin_id:label' for a named instance.")
    plugin_id: str
    instance_label: str | None = None
    plugin_name: str
    provider_name: str
    flows: list[Flow] = Field(description="Flows the plugin supports, preferred first.")
    configured: bool = Field(description="Whether a client ID is available, so a flow can start.")
    status: Literal["connected", "disconnected", "reauthorization_required"]
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


class OAuthAuthorizationStart(BaseModel):
    """How to carry a just-started flow forward."""

    flow: Flow
    authorization_url: str = Field(default="", description="relay: send the browser here.")
    device: OAuthDeviceStatus | None = Field(default=None, description="device: show this code to the user.")
