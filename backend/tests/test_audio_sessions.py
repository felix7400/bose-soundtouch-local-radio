from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.audio_sessions import register_audio_session_routes
from app.models import AppPlayback


class FakeSpeaker:
    def __init__(self) -> None:
        self.actions = []
        self.volume = 22

    async def get_now_playing(self):
        return {"source": "LOCAL_INTERNET_RADIO", "playStatus": "PLAY_STATE"}

    async def get_volume(self):
        return {"actualvolume": str(self.volume)}

    async def set_volume(self, level: int):
        self.volume = level
        self.actions.append(("volume", level))
        return {"ok": True}

    async def play_station_url(self, url: str, name: str, logo_url=None):
        self.actions.append(("play_url", url, name, logo_url))
        return {"ok": True, "transport": "fake"}

    async def playback(self, action: str):
        self.actions.append(("playback", action))
        return {"ok": True}

    async def select_source(self, source: str, source_account: str = ""):
        self.actions.append(("source", source, source_account))
        return {"ok": True}


class FakeStation:
    name = "Old station"
    logo_url = None


class FakeStorage:
    def __init__(self) -> None:
        self.playback = AppPlayback(
            station_id="old",
            playing=True,
            mode="direct",
            stream_url="http://radio.local/old.mp3",
        )

    def get_app_playback(self):
        return self.playback

    def set_app_playback(self, playback):
        self.playback = playback
        return playback

    def get_station(self, station_id: str):
        if station_id != "old":
            raise KeyError(station_id)
        return FakeStation()


def build_client():
    speaker = FakeSpeaker()
    storage = FakeStorage()
    app = FastAPI()
    register_audio_session_routes(app, lambda required=True: speaker, storage)
    return TestClient(app), speaker, storage


def test_direct_url_playback_updates_app_state() -> None:
    client, speaker, storage = build_client()
    response = client.post(
        "/api/speaker/play-url",
        json={"url": "http://zimmeros.local/speech.wav", "name": "ZimmerOS"},
    )
    assert response.status_code == 200
    assert storage.playback.stream_url == "http://zimmeros.local/speech.wav"
    assert speaker.actions[-1][:2] == ("play_url", "http://zimmeros.local/speech.wav")


def test_speech_session_restores_previous_stream_and_volume() -> None:
    client, speaker, storage = build_client()
    response = client.post(
        "/api/speaker/speak-url",
        json={
            "url": "http://zimmeros.local/speech.wav",
            "name": "ZimmerOS speech",
            "volume": 35,
            "duration_seconds": 0,
            "restore": True,
        },
    )
    assert response.status_code == 200
    assert response.json()["restore"]["ok"] is True
    assert ("volume", 35) in speaker.actions
    assert ("playback", "stop") in speaker.actions
    assert ("play_url", "http://radio.local/old.mp3", "Old station", None) in speaker.actions
    assert speaker.actions[-1] == ("volume", 22)
    assert storage.playback.station_id == "old"


def test_snapshot_and_restore_endpoints() -> None:
    client, speaker, _ = build_client()
    snapshot = client.get("/api/speaker/snapshot")
    assert snapshot.status_code == 200
    assert snapshot.json()["volume"] == 22
    restored = client.post("/api/speaker/restore", json={"snapshot": snapshot.json()})
    assert restored.status_code == 200
    assert restored.json()["restored"]["playback"] is True
    assert speaker.actions[-1] == ("volume", 22)


def test_rejects_non_http_urls() -> None:
    client, _, _ = build_client()
    response = client.post(
        "/api/speaker/play-url",
        json={"url": "file:///etc/passwd", "name": "invalid"},
    )
    assert response.status_code == 422
