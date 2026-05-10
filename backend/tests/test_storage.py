from app import storage as storage_module
from app.models import AppPlayback, AppPreferences, SpeakerConfig, StationCreate, StationUpdate


def test_station_crud_uses_json_files(tmp_path, monkeypatch):
    monkeypatch.setattr(storage_module, "STATIONS_PATH", tmp_path / "stations.json")
    monkeypatch.setattr(storage_module, "CONFIG_PATH", tmp_path / "config.json")
    store = storage_module.AppStorage()

    created = store.create_station(
        StationCreate(
            name="Test Radio",
            stream_url="https://example.test/live.mp3",
            logo_url="",
            tags=["jazz", "jazz", "evening"],
            use_proxy_by_default=False,
        )
    )

    assert created.id
    assert created.logo_url is None
    assert created.tags == ["jazz", "evening"]
    assert store.get_station(created.id).name == "Test Radio"

    updated = store.update_station(
        created.id,
        StationUpdate(
            name="Updated Radio",
            stream_url="https://example.test/updated.mp3",
            tags=["news"],
            use_proxy_by_default=True,
        ),
    )

    assert updated.name == "Updated Radio"
    assert updated.use_proxy_by_default is True

    store.delete_station(created.id)
    assert store.list_stations() == []


def test_speaker_config_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(storage_module, "STATIONS_PATH", tmp_path / "stations.json")
    monkeypatch.setattr(storage_module, "CONFIG_PATH", tmp_path / "config.json")
    store = storage_module.AppStorage()

    store.set_speaker_config(SpeakerConfig(host="192.168.1.23", port=8090))

    assert store.get_speaker_config().host == "192.168.1.23"


def test_preferences_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(storage_module, "STATIONS_PATH", tmp_path / "stations.json")
    monkeypatch.setattr(storage_module, "CONFIG_PATH", tmp_path / "config.json")
    store = storage_module.AppStorage()

    store.set_preferences(AppPreferences(favorite_station_ids=["a", "b"], quick_buttons={"1": "a"}))

    assert store.get_preferences().favorite_station_ids == ["a", "b"]
    assert store.get_preferences().quick_buttons == {"1": "a"}


def test_app_playback_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(storage_module, "STATIONS_PATH", tmp_path / "stations.json")
    monkeypatch.setattr(storage_module, "CONFIG_PATH", tmp_path / "config.json")
    store = storage_module.AppStorage()

    store.set_app_playback(AppPlayback(station_id="bayern-1", playing=True, mode="proxy", stream_url="/stream/bayern-1"))

    playback = store.get_app_playback()
    assert playback.station_id == "bayern-1"
    assert playback.playing is True
    assert playback.mode == "proxy"
