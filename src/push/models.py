"""Strict browser input and deliberate secret-free response projections."""

import base64
import re
from typing import Literal
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.asymmetric import ec
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator

PROVIDERS = frozenset({"fcm.googleapis.com", "updates.push.services.mozilla.com", "web.push.apple.com"})


def validate_endpoint(value: str) -> str:
    """Permit only canonical HTTPS browser-provider URLs; DNS is checked at send."""
    try:
        parts = urlsplit(value)
        if (
            len(value) > 2048
            or not value.isascii()
            or any(c.isspace() or ord(c) < 33 for c in value)
            or "\\" in value
            or parts.scheme != "https"
            or parts.hostname not in PROVIDERS
            or parts.netloc != parts.hostname
            or parts.fragment
            or not parts.path.startswith("/")
        ):
            raise ValueError
    except ValueError:
        raise ValueError("Unsupported push endpoint") from None
    return value


def decode_key(value: str) -> bytes:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("Invalid push key")
    decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    if base64.urlsafe_b64encode(decoded).rstrip(b"=").decode() != value:
        raise ValueError("Invalid push key")
    return decoded


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class PushKeys(StrictModel):
    p256dh: str = Field(min_length=87, max_length=87, repr=False)
    auth: str = Field(min_length=22, max_length=22, repr=False)

    @field_validator("p256dh")
    @classmethod
    def public_point(cls, value):
        try:
            ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), decode_key(value))
        except ValueError:
            raise ValueError("Invalid push key") from None
        return value

    @field_validator("auth")
    @classmethod
    def auth_secret(cls, value):
        if len(decode_key(value)) != 16:
            raise ValueError("Invalid push key")
        return value


class Subscription(StrictModel):
    endpoint: str = Field(max_length=2048, repr=False)
    expirationTime: StrictInt | None = Field(default=None, ge=0, le=8_640_000_000_000_000)
    keys: PushKeys = Field(repr=False)

    _endpoint = field_validator("endpoint")(validate_endpoint)


class PushPreference(StrictModel):
    enabled: StrictBool


class PushSubscription(PushPreference):
    subscription: Subscription = Field(repr=False)


class PushStatus(BaseModel):
    public_key: str
    user_enabled: bool
    device_enabled: bool
    subscribed: bool
    expiration_time: int | None = None
    event_sources: list[Literal["display_offline", "override_ended", "update_available", "silence_held"]] = []
    test_available: bool = False


class TestPushRequest(StrictModel):
    pass


class DeliveryResult(BaseModel):
    sent: int = 0
    failed: int = 0
    skipped: int = 0
    expired: int = 0


class Notification(StrictModel):
    title: str = Field(min_length=1, max_length=80)
    body: str = Field(default="", max_length=240)
    url: str = Field(default="/", max_length=1024)
    tag: str = Field(default="fiestaboard", max_length=64)

    @field_validator("url")
    @classmethod
    def local_url(cls, value):
        if not value.startswith("/") or value.startswith("//") or "\\" in value or any(ord(c) < 32 for c in value):
            raise ValueError("Notification URL must stay on this hub")
        return value
