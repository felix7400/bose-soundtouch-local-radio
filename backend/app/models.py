from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl, validator


class SpeakerConfig(BaseModel):
    host: Optional[str] = None
    port: int = 8090

    @validator("host")
    def blank_host_to_none(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class DiscoveredDevice(BaseModel):
    host: str
    port: int = 8090
    name: Optional[str] = None
    model: Optional[str] = None
    device_id: Optional[str] = None
    source: str
    location: Optional[str] = None


class AppPlayback(BaseModel):
    station_id: Optional[str] = None
    playing: bool = False
    mode: Optional[Literal["direct", "proxy"]] = None
    stream_url: Optional[str] = None
    updated_at: Optional[datetime] = None


class SpeakerStatus(BaseModel):
    configured: bool
    reachable: bool
    error: Optional[str] = None
    info: Optional[Dict[str, Any]] = None
    now_playing: Optional[Dict[str, Any]] = None
    volume: Optional[Dict[str, Any]] = None
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    presets: List[Dict[str, Any]] = Field(default_factory=list)
    app_playback: Optional[AppPlayback] = None


class KeyRequest(BaseModel):
    key: str


class PlaybackRequest(BaseModel):
    action: Literal["play", "pause", "stop", "next", "previous"]


class VolumeRequest(BaseModel):
    level: int = Field(ge=0, le=100)


class MuteRequest(BaseModel):
    enabled: bool


class SourceRequest(BaseModel):
    source: str
    source_account: str = ""


class StationBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    stream_url: str = Field(min_length=4, max_length=2048)
    logo_url: Optional[str] = Field(default=None, max_length=2048)
    tags: List[str] = Field(default_factory=list)
    use_proxy_by_default: bool = False

    @validator("name", "stream_url")
    def trim_required(cls, value: str) -> str:
        return value.strip()

    @validator("logo_url")
    def trim_optional(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @validator("tags", pre=True)
    def normalize_tags(cls, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [part.strip() for part in value.split(",")]
        tags: List[str] = []
        for tag in value:
            cleaned = str(tag).strip()
            if cleaned and cleaned not in tags:
                tags.append(cleaned)
        return tags


class StationCreate(StationBase):
    pass


class StationUpdate(StationBase):
    pass


class Station(StationBase):
    id: str
    created_at: datetime
    updated_at: datetime


class StationMetadata(BaseModel):
    station_id: str
    station_name: str
    title: Optional[str] = None
    artist: Optional[str] = None
    track: Optional[str] = None
    stream_url: Optional[str] = None
    icy_name: Optional[str] = None
    icy_genre: Optional[str] = None
    raw: Optional[str] = None
    error: Optional[str] = None


class AppPreferences(BaseModel):
    favorite_station_ids: List[str] = Field(default_factory=list)
    quick_buttons: Dict[str, Optional[str]] = Field(default_factory=dict)


class PlayStationRequest(BaseModel):
    mode: Literal["direct", "proxy", "auto"] = "auto"


class PlayStationResponse(BaseModel):
    station: Station
    mode: Literal["direct", "proxy"]
    stream_url: str
    speaker_response: Dict[str, Any]
