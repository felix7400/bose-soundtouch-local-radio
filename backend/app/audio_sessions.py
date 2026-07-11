from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field, validator

from .models import AppPlayback
from .soundtouch import SoundTouchClient, SoundTouchError


class PlayUrlRequest(BaseModel):
    url: str = Field(min_length=4, max_length=2048)
    name: str = Field(default="ZimmerOS", min_length=1, max_length=120)
    logo_url: Optional[str] = Field(default=None, max_length=2048)

    @validator("url")
    def validate_url(cls, value: str) -> str:
        cleaned = value.strip()
        parsed = urlparse(cleaned)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Only absolute HTTP or HTTPS URLs are supported")
        if parsed.username or parsed.password:
            raise ValueError("URLs containing credentials are not supported")
        return cleaned

    @validator("name")
    def trim_name(cls, value: str) -> str:
        return value.strip()


class PlaybackSnapshot(BaseModel):
    app_playback: Dict[str, Any] = Field(default_factory=dict)
    now_playing: Dict[str, Any] = Field(default_factory=dict)
    volume: Optional[int] = Field(default=None, ge=0, le=100)
    source: Optional[str] = None
    source_account: str = ""
    playing: bool = False


class RestoreRequest(BaseModel):
    snapshot: PlaybackSnapshot


class SpeakUrlRequest(PlayUrlRequest):
    volume: int = Field(default=30, ge=0, le=100)
    duration_seconds: float = Field(default=1.0, ge=0.0, le=300.0)
    restore: bool = True


def register_audio_session_routes(
    app: FastAPI,
    speaker_client_factory: Callable[..., SoundTouchClient],
    app_storage: Any,
) -> None:
    """Register direct URL and serialized speech-session endpoints.

    The lock is scoped to this application process so two ZimmerOS announcements do
    not replace each other. A snapshot restores app-controlled radio playback and,
    where possible, the previous native SoundTouch source and volume.
    """

    router = APIRouter()
    session_lock = asyncio.Lock()

    def client() -> SoundTouchClient:
        return speaker_client_factory(required=True)

    async def call(operation):
        try:
            return await operation(client())
        except SoundTouchError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    async def capture_snapshot() -> PlaybackSnapshot:
        soundtouch = client()
        try:
            now_playing, volume_payload = await asyncio.gather(
                soundtouch.get_now_playing(), soundtouch.get_volume()
            )
        except SoundTouchError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        app_playback = app_storage.get_app_playback()
        source, source_account = _source_details(now_playing)
        playing = bool(app_playback.playing) or _looks_playing(now_playing)
        return PlaybackSnapshot(
            app_playback=app_playback.dict(),
            now_playing=now_playing,
            volume=_volume_level(volume_payload),
            source=source,
            source_account=source_account,
            playing=playing,
        )

    async def restore_snapshot(snapshot: PlaybackSnapshot) -> Dict[str, Any]:
        soundtouch = client()
        restored: Dict[str, Any] = {"playback": False, "source": False, "volume": False}
        app_playback = AppPlayback.parse_obj(snapshot.app_playback or {})
        try:
            if app_playback.stream_url:
                station_name = "Restored audio"
                logo_url = None
                if app_playback.station_id:
                    try:
                        station = app_storage.get_station(app_playback.station_id)
                        station_name = station.name
                        logo_url = station.logo_url
                    except KeyError:
                        pass
                restored["speaker_response"] = await soundtouch.play_station_url(
                    app_playback.stream_url, station_name, logo_url
                )
                if not app_playback.playing:
                    await soundtouch.playback("pause")
                app_storage.set_app_playback(app_playback)
                restored["playback"] = True
            elif snapshot.source and snapshot.source.upper() not in {"STANDBY", "INVALID_SOURCE"}:
                restored["speaker_response"] = await soundtouch.select_source(
                    snapshot.source, snapshot.source_account
                )
                restored["source"] = True
                if not snapshot.playing:
                    try:
                        await soundtouch.playback("pause")
                    except SoundTouchError:
                        pass
            else:
                try:
                    await soundtouch.playback("stop")
                except SoundTouchError:
                    pass
                app_storage.set_app_playback(AppPlayback())

            if snapshot.volume is not None:
                await soundtouch.set_volume(snapshot.volume)
                restored["volume"] = True
            return {"ok": True, "restored": restored}
        except SoundTouchError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @router.post("/api/speaker/play-url")
    async def play_url(request: PlayUrlRequest) -> Dict[str, Any]:
        response = await call(
            lambda soundtouch: soundtouch.play_station_url(
                request.url, request.name, request.logo_url
            )
        )
        app_storage.set_app_playback(
            AppPlayback(
                station_id=None,
                playing=True,
                mode="direct",
                stream_url=request.url,
            )
        )
        return {"ok": True, "url": request.url, "speaker_response": response}

    @router.get("/api/speaker/snapshot", response_model=PlaybackSnapshot)
    async def snapshot() -> PlaybackSnapshot:
        return await capture_snapshot()

    @router.post("/api/speaker/restore")
    async def restore(request: RestoreRequest) -> Dict[str, Any]:
        async with session_lock:
            return await restore_snapshot(request.snapshot)

    @router.post("/api/speaker/speak-url")
    async def speak_url(request: SpeakUrlRequest) -> Dict[str, Any]:
        async with session_lock:
            previous = await capture_snapshot() if request.restore else None
            soundtouch = client()
            playback_response: Dict[str, Any]
            restore_response: Optional[Dict[str, Any]] = None
            try:
                await soundtouch.set_volume(request.volume)
                playback_response = await soundtouch.play_station_url(
                    request.url, request.name, request.logo_url
                )
                app_storage.set_app_playback(
                    AppPlayback(
                        station_id=None,
                        playing=True,
                        mode="direct",
                        stream_url=request.url,
                    )
                )
                if request.duration_seconds:
                    await asyncio.sleep(request.duration_seconds)
                try:
                    await soundtouch.playback("stop")
                except SoundTouchError:
                    pass
            except SoundTouchError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            finally:
                if previous is not None:
                    restore_response = await restore_snapshot(previous)
            return {
                "ok": True,
                "url": request.url,
                "duration_seconds": request.duration_seconds,
                "speaker_response": playback_response,
                "restore": restore_response,
            }

    app.include_router(router)


def _volume_level(payload: Dict[str, Any]) -> Optional[int]:
    for key in ("actualvolume", "targetvolume", "volume", "text"):
        value = _find_value(payload, key)
        if value is None:
            continue
        try:
            return max(0, min(100, int(float(str(value)))))
        except (TypeError, ValueError):
            continue
    return None


def _source_details(payload: Dict[str, Any]) -> tuple[Optional[str], str]:
    source = _find_value(payload, "source")
    account = _find_value(payload, "sourceAccount")
    if account is None:
        account = _find_value(payload, "sourceaccount")
    return (str(source) if source else None, str(account) if account else "")


def _looks_playing(payload: Dict[str, Any]) -> bool:
    status = _find_value(payload, "playStatus") or _find_value(payload, "playstatus")
    return str(status or "").upper() in {"PLAY_STATE", "PLAYING", "PLAY"}


def _find_value(value: Any, target: str) -> Any:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).casefold() == target.casefold():
                return item
        for item in value.values():
            found = _find_value(item, target)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_value(item, target)
            if found is not None:
                return found
    return None
