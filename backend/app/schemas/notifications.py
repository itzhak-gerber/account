import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import NotificationEvent


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event: NotificationEvent
    title: str
    body: str
    link: str
    read_at: datetime | None
    created_at: datetime


class UnreadCount(BaseModel):
    unread: int


class MarkRead(BaseModel):
    # Omit to mark everything as read.
    ids: list[uuid.UUID] | None = Field(default=None, max_length=200)


class ChannelPrefs(BaseModel):
    in_app: bool = True
    email: bool = False
    push: bool = False


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=1, max_length=200)
    auth: str = Field(min_length=1, max_length=100)


class PushSubscriptionIn(BaseModel):
    endpoint: str = Field(min_length=1, max_length=1000)
    keys: PushKeys


class PushSubscriptionRef(BaseModel):
    endpoint: str = Field(min_length=1, max_length=1000)


class PushConfig(BaseModel):
    # None when push is not configured on this server.
    public_key: str | None
    devices: int


class PreferenceOut(BaseModel):
    event: NotificationEvent
    channels: ChannelPrefs


class PreferencesIn(BaseModel):
    preferences: dict[NotificationEvent, ChannelPrefs]


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str
    last_ip: str
    first_seen_at: datetime
    last_seen_at: datetime
    current: bool = False  # the browser making this request
