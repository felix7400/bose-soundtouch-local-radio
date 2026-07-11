from __future__ import annotations

import socket
from datetime import datetime
from urllib.parse import urlparse
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .audio_sessions import register_audio_session_routes
from .auth import OptionalBasicAuthMiddleware
from .config import FRONTEND_DIST, settings
from .discovery import discover_soundtouch_devices, is_blocked_host, probe_soundtouch_host
from .metadata import read_station_metadata
from .models import (
    DiscoveredDevice,
    AppPlayback,
    AppPreferences,
    KeyRequest,
    MuteRequest,
    PlayStationRequest,
    PlayStationResponse,
    PlaybackRequest,
    SourceRequest,
    SpeakerConfig,
    SpeakerStatus,
    Station,
    StationCreate,
    StationMetadata,
    StationUpdate,
    VolumeRequest,
)
from .soundtouch import SoundTouchClient, SoundTouchError
from .storage import storage
from .stream_proxy import proxy_station_stream


app = FastAPI(title="SoundTouch Local", version="0.1.0")
app.add_middleware(OptionalBasicAuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict:
    return {"ok": True, "host": settings.app_host, "port": settings.app_port}


@app.get("/api/network")
async def network() -> dict:
    return {"local_ips": _local_ips(), "port": settings.app_port, "alias_host": settings.app_alias_host}


@app.get("/api/speaker/config", response_model=SpeakerConfig)
async def get_speaker_config() -> SpeakerConfig:
    return storage.get_speaker_config()


@app.post("/api/speaker/config", response_model=SpeakerConfig)
async def set_speaker_config(config: SpeakerConfig) -> SpeakerConfig:
    if not config.host:
        raise HTTPException(status_code=400, detail="Speaker host is required")
    if is_blocked_host(config.host):
        raise HTTPException(status_code=400, detail="This speaker host is blocked and will not be contacted")
    device = await probe_soundtouch_host(config.host, config.port)
    if not device:
        raise HTTPException(status_code=400, detail="No SoundTouch device responded at that host and port")
    return storage.set_speaker_config(config)


@app.get("/api/speaker/discover", response_model=List[DiscoveredDevice])
async def discover_speakers() -> List[DiscoveredDevice]:
    return await discover_soundtouch_devices()


@app.get("/api/speaker/status", response_model=SpeakerStatus)
async def get_speaker_status() -> SpeakerStatus:
    app_playback = storage.get_app_playback()
    client = _speaker_client(required=False)
    if client is None:
        return SpeakerStatus(configured=False, reachable=False, error="No speaker configured", app_playback=app_playback)
    try:
        bundle = await client.get_status_bundle()
    except SoundTouchError as exc:
        return SpeakerStatus(configured=True, reachable=False, error=str(exc), app_playback=app_playback)
    return SpeakerStatus(configured=True, reachable=True, app_playback=app_playback, **bundle)


@app.get("/api/speaker/info")
async def get_speaker_info() -> dict:
    return await _speaker_call(lambda client: client.get_info())


@app.post("/api/speaker/key")
async def send_speaker_key(request: KeyRequest) -> dict:
    return await _speaker_call(lambda client: client.send_key(request.key))


@app.post("/api/speaker/standby")
async def speaker_standby() -> dict:
    response = await _speaker_call(lambda client: client.send_key("POWER"))
    storage.set_app_playback(AppPlayback(updated_at=datetime.utcnow()))
    return response


@app.post("/api/speaker/playback")
async def speaker_playback(request: PlaybackRequest) -> dict:
    response = await _speaker_call(lambda client: client.playback(request.action))
    current = storage.get_app_playback()
    if request.action in {"pause", "stop"}:
        storage.set_app_playback(current.copy(update={"playing": False, "updated_at": datetime.utcnow()}))
    elif request.action == "play" and current.station_id:
        storage.set_app_playback(current.copy(update={"playing": True, "updated_at": datetime.utcnow()}))
    return response


@app.post("/api/speaker/volume")
async def speaker_volume(request: VolumeRequest) -> dict:
    return await _speaker_call(lambda client: client.set_volume(request.level))


@app.post("/api/speaker/mute")
async def speaker_mute(request: MuteRequest) -> dict:
    return await _speaker_call(lambda client: client.set_mute(request.enabled))


@app.post("/api/speaker/source")
async def speaker_source(request: SourceRequest) -> dict:
    return await _speaker_call(lambda client: client.select_source(request.source, request.source_account))


@app.post("/api/speaker/preset/{preset_id}")
async def speaker_preset(preset_id: int) -> dict:
    return await _speaker_call(lambda client: client.select_preset(preset_id))


@app.get("/api/stations", response_model=List[Station])
async def list_stations() -> List[Station]:
    return storage.list_stations()


@app.get("/api/preferences", response_model=AppPreferences)
async def get_preferences() -> AppPreferences:
    return storage.get_preferences()


@app.post("/api/preferences", response_model=AppPreferences)
async def set_preferences(preferences: AppPreferences) -> AppPreferences:
    station_ids = {station.id for station in storage.list_stations()}
    favorite_ids = [station_id for station_id in preferences.favorite_station_ids if station_id in station_ids]
    quick_buttons = {
        str(slot): station_id
        for slot, station_id in preferences.quick_buttons.items()
        if str(slot) in {"1", "2", "3", "4", "5", "6"} and (station_id is None or station_id in station_ids)
    }
    return storage.set_preferences(AppPreferences(favorite_station_ids=favorite_ids, quick_buttons=quick_buttons))


@app.post("/api/hardware-presets/sync")
async def sync_hardware_presets(request: Request) -> dict:
    sources = await _speaker_call(lambda client: client.get_sources())
    if not any(source.get("source") == "LOCAL_INTERNET_RADIO" for source in sources):
        raise HTTPException(
            status_code=400,
            detail="This speaker does not expose LOCAL_INTERNET_RADIO, so physical presets cannot be synced locally.",
        )
    preferences = storage.get_preferences()
    synced = []
    for slot in ["1", "2", "3", "4", "5", "6"]:
        station_id = preferences.quick_buttons.get(slot)
        if not station_id:
            continue
        try:
            station = storage.get_station(station_id)
        except KeyError:
            continue
        location_url = _bose_station_descriptor_url(request, station.id)
        response = await _speaker_call(
            lambda client, slot=slot, station=station, location_url=location_url: client.store_preset(
                int(slot),
                station.name,
                location_url,
                None,
            )
        )
        synced.append(
            {
                "slot": slot,
                "station_id": station.id,
                "station_name": station.name,
                "location_url": location_url,
                "speaker_response": response,
            }
        )
    if not synced:
        raise HTTPException(status_code=400, detail="No quick buttons are assigned")
    return {"ok": True, "synced": synced}


@app.post("/api/stations", response_model=Station)
async def create_station(station: StationCreate) -> Station:
    return storage.create_station(station)


@app.put("/api/stations/{station_id}", response_model=Station)
async def update_station(station_id: str, update: StationUpdate) -> Station:
    try:
        return storage.update_station(station_id, update)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Station not found") from exc


@app.delete("/api/stations/{station_id}")
async def delete_station(station_id: str) -> dict:
    try:
        storage.delete_station(station_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Station not found") from exc
    return {"ok": True}


@app.get("/api/stations/{station_id}/metadata", response_model=StationMetadata)
async def get_station_metadata(station_id: str) -> StationMetadata:
    try:
        station = storage.get_station(station_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Station not found") from exc
    return await read_station_metadata(station)


@app.post("/api/stations/{station_id}/play", response_model=PlayStationResponse)
async def play_station(station_id: str, play_request: PlayStationRequest, request: Request) -> PlayStationResponse:
    try:
        station = storage.get_station(station_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Station not found") from exc
    return await _play_station(station, play_request, request)


@app.post("/api/quick-buttons/{slot}/play", response_model=PlayStationResponse)
async def play_quick_button(slot: str, request: Request) -> PlayStationResponse:
    if slot not in {"1", "2", "3", "4", "5", "6"}:
        raise HTTPException(status_code=404, detail="Quick button not found")
    station_id = storage.get_preferences().quick_buttons.get(slot)
    if not station_id:
        raise HTTPException(status_code=400, detail=f"Quick button {slot} is not assigned")
    try:
        station = storage.get_station(station_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Assigned station not found") from exc
    return await _play_station(station, PlayStationRequest(mode="auto"), request)


async def _play_station(station: Station, play_request: PlayStationRequest, request: Request) -> PlayStationResponse:
    mode = _station_play_mode(station, play_request.mode)
    stream_url = station.stream_url if mode == "direct" else _stream_proxy_url(request, station.id)
    response = await _speaker_call(
        lambda client: client.play_station_url(stream_url, station.name, station.logo_url)
    )
    storage.set_app_playback(
        AppPlayback(
            station_id=station.id,
            playing=True,
            mode=mode,
            stream_url=stream_url,
            updated_at=datetime.utcnow(),
        )
    )
    return PlayStationResponse(station=station, mode=mode, stream_url=stream_url, speaker_response=response)


@app.get("/stream/{station_id}")
async def stream_station(station_id: str):
    try:
        station = storage.get_station(station_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Station not found") from exc
    return await proxy_station_stream(station)


@app.get("/bose/stations/{station_id}.json")
async def bose_station_descriptor(station_id: str, request: Request) -> JSONResponse:
    try:
        station = storage.get_station(station_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Station not found") from exc
    return JSONResponse(
        {
            "name": station.name,
            "imageUrl": "",
            "streamUrl": _stream_proxy_url(request, station.id),
        }
    )


def _speaker_client(required: bool = True) -> Optional[SoundTouchClient]:
    config = storage.get_speaker_config()
    if not config.host:
        if required:
            raise HTTPException(status_code=400, detail="No speaker configured")
        return None
    if is_blocked_host(config.host):
        if required:
            raise HTTPException(status_code=400, detail="Configured speaker host is blocked")
        return None
    return SoundTouchClient(config.host, config.port, dlna_port=settings.soundtouch_dlna_port)


async def _speaker_call(operation):
    client = _speaker_client(required=True)
    try:
        return await operation(client)
    except SoundTouchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _stream_proxy_url(request: Request, station_id: str) -> str:
    base_url = _app_base_url_for_speaker(request)
    if base_url:
        return f"{base_url}/stream/{station_id}"
    return str(request.url_for("stream_station", station_id=station_id))


def _bose_station_descriptor_url(request: Request, station_id: str) -> str:
    base_url = _app_base_url_for_speaker(request)
    if base_url:
        return f"{base_url}/bose/stations/{station_id}.json"
    return str(request.url_for("bose_station_descriptor", station_id=station_id))


def _app_base_url_for_speaker(request: Request) -> Optional[str]:
    if settings.app_stream_base_url:
        return settings.app_stream_base_url
    if settings.app_base_url:
        return settings.app_base_url
    request_host = request.url.hostname
    if request_host in {"127.0.0.1", "localhost", "::1"}:
        local_ips = _local_ips()
        if local_ips:
            return f"{request.url.scheme}://{local_ips[0]}:{settings.app_port}"
    return None


def _station_play_mode(station: Station, requested_mode: str) -> str:
    if requested_mode == "proxy" or station.use_proxy_by_default:
        return "proxy"
    if requested_mode == "direct":
        return "direct"
    parsed = urlparse(station.stream_url)
    if parsed.scheme.lower() != "http":
        return "proxy"
    return "direct"


def _local_ips() -> List[str]:
    addresses = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            addresses.add(sock.getsockname()[0])
    except OSError:
        pass
    try:
        hostname = socket.gethostname()
        for result in socket.getaddrinfo(hostname, None, socket.AF_INET):
            address = result[4][0]
            if not address.startswith("127."):
                addresses.add(address)
    except OSError:
        pass
    return sorted(addresses)


register_audio_session_routes(app, _speaker_client, storage)


if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    index_path = FRONTEND_DIST / "index.html"
    requested_path = (FRONTEND_DIST / full_path).resolve()
    if full_path and requested_path.is_file() and FRONTEND_DIST.resolve() in requested_path.parents:
        return FileResponse(requested_path)
    if index_path.exists():
        return FileResponse(index_path)
    raise HTTPException(
        status_code=404,
        detail="Frontend is not built yet. Run scripts/setup.sh or npm run build in frontend.",
    )
