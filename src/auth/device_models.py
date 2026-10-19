"""Version-one native sign-in protocol, separate from browser cookie auth."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool


class AuthFlowError(Exception):
    def __init__(self, error: str, detail: str, status: int = 400, retry_after: int | None = None):
        super().__init__(detail)
        self.error, self.detail, self.status, self.retry_after = error, detail, status, retry_after


class DeviceMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_id: Literal["fiestaboard-tvos", "fiestaboard-androidtv"]
    device_name: str = Field(min_length=1, max_length=100, pattern=r"^[^\x00-\x1f\x7f]+$")
    app_version: str = Field(min_length=1, max_length=40, pattern=r"^[^\x00-\x1f\x7f]+$")


class DeviceLogin(DeviceMetadata):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=1024)


class DeviceCode(BaseModel):
    device_code: str = Field(min_length=1, max_length=128)


class DeviceExchange(DeviceCode):
    client_id: Literal["fiestaboard-tvos", "fiestaboard-androidtv"]


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
    scope: Literal["tv_panels"] = "tv_panels"


class PendingDevice(BaseModel):
    user_code: str
    client_id: str
    device_name: str
    app_version: str
    expires_in: int
    scope: Literal["tv_panels"] = "tv_panels"


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


class SessionSummary(BaseModel):
    id: str
    kind: Literal["browser", "tv", "legacy"]
    device_name: str
    client_id: str
    app_version: str
    method: Literal["password", "device_code"]
    created_at: str
    last_active_at: str
    expires_at: str


class SessionList(BaseModel):
    sessions: list[SessionSummary]
    current_session_id: str


class TVSignInCapability(BaseModel):
    supported: bool = True
    enabled: bool
    protocol_version: Literal[1] = 1
