"""Version-one native sign-in protocol, separate from browser cookie auth."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

from .session_store import printable


class AuthFlowError(Exception):
    def __init__(self, error: str, detail: str, status: int = 400, retry_after: int | None = None):
        super().__init__(detail)
        self.error, self.detail, self.status, self.retry_after = error, detail, status, retry_after


# TVs get the ``tv_panels`` scope; phones get ``control``. See src/auth/scopes.py.
NativeClientId = Literal["fiestaboard-tvos", "fiestaboard-androidtv", "fiestaboard-ios", "fiestaboard-android"]
NativeScope = Literal["tv_panels", "control"]


class DeviceMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_id: NativeClientId
    device_name: str = Field(min_length=1, max_length=100, pattern=r"^[^\x00-\x1f\x7f]+$")
    app_version: str = Field(min_length=1, max_length=40, pattern=r"^[^\x00-\x1f\x7f]+$")

    @field_validator("device_name", "app_version")
    @classmethod
    def _printable_only(cls, value: str) -> str:
        """Drop C1 controls, bidi overrides and other non-printables (security F7).

        The pattern already refuses C0 and DEL; these names reach Signed-in
        devices, the phone's TV list and the audit log.
        """
        cleaned = printable(value, limit=len(value))
        if not cleaned.strip():
            raise ValueError("must contain printable characters")
        return cleaned


class DeviceLogin(DeviceMetadata):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=1024)


class DeviceCode(BaseModel):
    device_code: str = Field(min_length=1, max_length=128)


class DeviceExchange(DeviceCode):
    client_id: NativeClientId


class UserCode(BaseModel):
    user_code: str = Field(min_length=1, max_length=32)


class DeviceChallenge(BaseModel):
    device_code: str
    user_code: str
    verification_path: str = "/activate"
    verification_path_complete: str
    expires_in: int = 600
    interval: int = 5


class DeviceTokenResult(BaseModel):
    access_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int = 31536000
    session_id: str
    scope: NativeScope = "tv_panels"


class PendingDevice(BaseModel):
    user_code: str
    client_id: str
    device_name: str
    app_version: str
    expires_in: int
    scope: NativeScope = "tv_panels"


class HubAddress(BaseModel):
    """One address a phone might reach this hub at (H18)."""

    url: str = Field(description="scheme://host[:port], never a loopback address.")
    kind: Literal["browser", "configured", "mdns", "lan"] = Field(
        description="browser: this browser's origin; configured: FIESTABOARD_EXTERNAL_URL; "
        "mdns: the advertised <hostname>.local; lan: this host's LAN address."
    )


class PairingRequest(BaseModel):
    """``POST /auth/pairing``'s optional body."""

    model_config = ConfigDict(extra="forbid")

    hub: str | None = Field(
        default=None,
        max_length=2048,
        description="The address the QR should carry: one of a previous offer's hub_addresses. Default: the first.",
    )


class PairingOffer(BaseModel):
    """A QR pairing offer for a phone. The secret is only inside ``qr_payload``."""

    pairing_id: str = Field(description="Handle for polling the offer's state. Not a secret.")
    qr_payload: str = Field(
        description=(
            "Render as a QR code. A fiestaboard://pair URL whose fragment holds v, hub, id, name and the "
            "one-time code; the code is never sent in a request URL."
        )
    )
    hub: str = Field(
        description=("The address the QR tells the phone to use: never loopback (H18). Also inside qr_payload.")
    )
    expires_in: int = Field(default=300, description="Seconds until the code stops working. Single use.")
    scope: NativeScope = "control"
    hub_addresses: list[HubAddress] = Field(
        default_factory=list,
        description="Every address a phone might reach this hub at, best first; `hub` is one of them (H18).",
    )


class PairingState(BaseModel):
    state: Literal["pending", "claimed", "expired", "cancelled"]
    device_name: str | None = None
    session_id: str | None = None


class PairingClaim(DeviceMetadata):
    pairing_code: str = Field(min_length=1, max_length=128)


class EnrollmentSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool


class RevokeSessions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    include_current: StrictBool


class Success(BaseModel):
    status: Literal["ok"] = "ok"


class CSRFContext(BaseModel):
    csrf_token: str
    expires_in: int = 600


class PanelShown(BaseModel):
    panel_id: str
    last_shown_at: str


class ApprovedBy(BaseModel):
    """Who approved a TV's sign-in code (browser Signed-in devices only)."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(description="The approving session's id (it may have signed out since).")
    kind: Literal["browser", "tv", "mobile", "legacy"]
    label: str = Field(
        description='A phone\'s device name, or "<Browser> on <OS>" for a browser ("a web browser" if unknown).'
    )
    signed_in: bool = Field(description="Whether the approver is still signed in.")


class RevokeResult(Success):
    also_signed_out: list[str] = Field(
        default_factory=list,
        description="With include_approved=true on a phone: the TVs it approved, signed out with it.",
    )


class SessionSummary(BaseModel):
    id: str
    kind: Literal["browser", "tv", "mobile", "legacy"]
    device_name: str
    client_id: str
    app_version: str
    method: Literal["password", "device_code", "pairing"]
    created_at: str
    last_active_at: str
    expires_at: str
    # When this signed-in TV last fetched a panel frame (null if never), and
    # per panel, newest first. Persisted at most once a minute per viewer.
    last_shown_at: str | None = None
    shown_panels: list[PanelShown] = []
    # A TV that signed in with a code: the browser or phone that approved it.
    approved_by: ApprovedBy | None = None


class PhoneTV(BaseModel):
    """A signed-in TV, as the phone app sees it. No digests, usernames or approver ids."""

    # A field nobody listed here is an error, not a silent drop.
    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="The TV's sign-in id: the handle for DELETE /auth/device/tvs/{id}.")
    device_name: str
    client_id: str
    app_version: str
    method: Literal["password", "device_code"]
    created_at: str
    last_active_at: str
    expires_at: str
    last_shown_at: str | None = None
    shown_panels: list[PanelShown] = []
    approved_by_you: bool = Field(description="Whether the calling phone approved this TV's sign-in code.")


class PhoneTVList(BaseModel):
    tvs: list[PhoneTV]


class SessionList(BaseModel):
    sessions: list[SessionSummary]
    current_session_id: str


class TVSignInCapability(BaseModel):
    supported: bool = True
    enabled: bool
    protocol_version: Literal[1] = 1
