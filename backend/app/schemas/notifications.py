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
