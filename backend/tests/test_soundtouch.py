import httpx

from app.metadata import _parse_icy_metadata, _split_title
from app.soundtouch import _content_item_xml, _dlna_set_uri_xml, _parse_response, _preset_xml


def test_parse_volume_response():
    response = httpx.Response(
        200,
        text=(
            '<volume deviceID="abc">'
            "<targetvolume>31</targetvolume>"
            "<actualvolume>30</actualvolume>"
            "<muteenabled>false</muteenabled>"
            "</volume>"
        ),
    )

    parsed = _parse_response(response)

    assert parsed["_tag"] == "volume"
    assert parsed["targetvolume"] == "31"
    assert parsed["actualvolume"] == "30"
    assert parsed["muteenabled"] == "false"


def test_station_content_item_uses_local_radio_source():
    xml = _content_item_xml(
        source="LOCAL_INTERNET_RADIO",
        stream_url="http://192.168.1.10:8000/stream/example",
        station_name="Local Test",
        logo_url="http://example.test/logo.png",
        item_type="stationurl",
    )

    assert 'source="LOCAL_INTERNET_RADIO"' in xml
    assert 'type="stationurl"' in xml
    assert "<itemName>Local Test</itemName>" in xml
    assert "<containerArt>http://example.test/logo.png</containerArt>" in xml


def test_dlna_set_uri_xml_escapes_stream_url():
    xml = _dlna_set_uri_xml("http://example.test/live.mp3?x=1&y=2")

    assert "SetAVTransportURI" in xml
    assert "<CurrentURI>http://example.test/live.mp3?x=1&amp;y=2</CurrentURI>" in xml


def test_preset_xml_uses_local_internet_radio_descriptor():
    xml = _preset_xml(
        preset_id=1,
        source="LOCAL_INTERNET_RADIO",
        location_url="http://192.168.1.10:8000/bose/stations/bayern-1.json",
        station_name="BAYERN 1",
        logo_url=None,
    )

    assert '<preset id="1">' in xml
    assert 'source="LOCAL_INTERNET_RADIO"' in xml
    assert 'type="stationurl"' in xml
    assert 'location="http://192.168.1.10:8000/bose/stations/bayern-1.json"' in xml
    assert "<itemName>BAYERN 1</itemName>" in xml


def test_parse_icy_metadata_title():
    parsed = _parse_icy_metadata("StreamTitle='Artist - Track';StreamUrl='https://example.test';")
    artist, track = _split_title(parsed["StreamTitle"])

    assert parsed["StreamTitle"] == "Artist - Track"
    assert parsed["StreamUrl"] == "https://example.test"
    assert artist == "Artist"
    assert track == "Track"
