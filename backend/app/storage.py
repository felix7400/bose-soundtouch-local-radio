from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from .config import DATA_DIR, settings
from .models import AppPlayback, AppPreferences, SpeakerConfig, Station, StationCreate, StationUpdate


CONFIG_PATH = DATA_DIR / "config.json"
STATIONS_PATH = DATA_DIR / "stations.json"


def _read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")
    os.replace(temp_path, path)


class AppStorage:
    def get_speaker_config(self) -> SpeakerConfig:
        data = _read_json(CONFIG_PATH, {})
        host = data.get("speaker", {}).get("host") or settings.soundtouch_host
        port = data.get("speaker", {}).get("port") or settings.soundtouch_port
        return SpeakerConfig(host=host, port=port)

    def set_speaker_config(self, config: SpeakerConfig) -> SpeakerConfig:
        payload = _read_json(CONFIG_PATH, {})
        payload["speaker"] = config.dict()
        _write_json(CONFIG_PATH, payload)
        return config

    def get_preferences(self) -> AppPreferences:
        data = _read_json(CONFIG_PATH, {})
        preferences = data.get("preferences", {})
        return AppPreferences(**preferences)

    def set_preferences(self, preferences: AppPreferences) -> AppPreferences:
        payload = _read_json(CONFIG_PATH, {})
        payload["preferences"] = preferences.dict()
        _write_json(CONFIG_PATH, payload)
        return preferences

    def get_app_playback(self) -> AppPlayback:
        data = _read_json(CONFIG_PATH, {})
        return AppPlayback(**data.get("playback", {}))

    def set_app_playback(self, playback: AppPlayback) -> AppPlayback:
        payload = _read_json(CONFIG_PATH, {})
        payload["playback"] = playback.dict()
        _write_json(CONFIG_PATH, payload)
        return playback

    def list_stations(self) -> List[Station]:
        data = _read_json(STATIONS_PATH, [])
        return [Station(**item) for item in data]

    def get_station(self, station_id: str) -> Station:
        for station in self.list_stations():
            if station.id == station_id:
                return station
        raise KeyError(station_id)

    def create_station(self, station: StationCreate) -> Station:
        now = datetime.utcnow()
        new_station = Station(
            id=str(uuid4()),
            created_at=now,
            updated_at=now,
            **station.dict(),
        )
        stations = self.list_stations()
        stations.append(new_station)
        self._save_stations(stations)
        return new_station

    def update_station(self, station_id: str, update: StationUpdate) -> Station:
        stations = self.list_stations()
        now = datetime.utcnow()
        for index, station in enumerate(stations):
            if station.id == station_id:
                updated = Station(
                    id=station.id,
                    created_at=station.created_at,
                    updated_at=now,
                    **update.dict(),
                )
                stations[index] = updated
                self._save_stations(stations)
                return updated
        raise KeyError(station_id)

    def delete_station(self, station_id: str) -> None:
        stations = self.list_stations()
        remaining = [station for station in stations if station.id != station_id]
        if len(remaining) == len(stations):
            raise KeyError(station_id)
        self._save_stations(remaining)
        if self.get_app_playback().station_id == station_id:
            self.set_app_playback(AppPlayback())

    def _save_stations(self, stations: List[Station]) -> None:
        payload: List[Dict[str, Any]] = [station.dict() for station in stations]
        _write_json(STATIONS_PATH, payload)


storage = AppStorage()
