from __future__ import annotations

import asyncio
import html
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

import httpx

from .config import settings


SENDER = "Gabbo"
PLAYBACK_KEYS = {
    "play": "PLAY",
    "pause": "PAUSE",
    "stop": "STOP",
    "next": "NEXT_TRACK",
    "previous": "PREV_TRACK",
}


class SoundTouchError(RuntimeError):
    pass


class SoundTouchClient:
    def __init__(self, host: str, port: int = 8090, timeout: float = 4.0, dlna_port: int = 8091) -> None:
        if host in settings.soundtouch_blocklist:
            raise SoundTouchError(f"Blocked SoundTouch host: {host}")
        self.host = host
        self.port = port
        self.dlna_port = dlna_port
        self.timeout = timeout
        self.base_url = f"http://{host}:{port}"
        self.dlna_url = f"http://{host}:{dlna_port}"

    async def get_info(self) -> Dict[str, Any]:
        return await self._get_xml("/info")

    async def get_now_playing(self) -> Dict[str, Any]:
        return await self._get_xml("/now_playing")

    async def get_volume(self) -> Dict[str, Any]:
        return await self._get_xml("/volume")

    async def get_sources(self) -> List[Dict[str, Any]]:
        payload = await self._get_xml("/sources")
        items = payload.get("sourceItem", [])
        if isinstance(items, dict):
            items = [items]
        return items if isinstance(items, list) else []

    async def get_presets(self) -> List[Dict[str, Any]]:
        payload = await self._get_xml("/presets")
        presets = payload.get("preset", [])
        if isinstance(presets, dict):
            presets = [presets]
        return presets if isinstance(presets, list) else []

    async def get_status_bundle(self) -> Dict[str, Any]:
        info, now_playing, volume, sources, presets = await asyncio.gather(
            self.get_info(),
            self.get_now_playing(),
            self.get_volume(),
            self.get_sources(),
            self.get_presets(),
        )
        return {
            "info": info,
            "now_playing": now_playing,
            "volume": volume,
            "sources": sources,
            "presets": presets,
        }

    async def send_key(self, key: str) -> Dict[str, Any]:
        normalized = key.strip().upper()
        press = self._key_xml(normalized, "press")
        release = self._key_xml(normalized, "release")
        await self._post_xml("/key", press)
        return await self._post_xml("/key", release)

    async def playback(self, action: str) -> Dict[str, Any]:
        key = PLAYBACK_KEYS[action]
        return await self.send_key(key)

    async def set_volume(self, level: int) -> Dict[str, Any]:
        return await self._post_xml("/volume", f"<volume>{level}</volume>")

    async def set_mute(self, enabled: bool) -> Dict[str, Any]:
        mute = "true" if enabled else "false"
        current = await self.get_volume()
        level = current.get("targetvolume") or current.get("actualvolume") or ""
        root = ET.Element("volume")
        if level:
            root.text = str(level)
        mute_element = ET.SubElement(root, "muteenabled")
        mute_element.text = mute
        return await self._post_xml("/volume", _xml_to_string(root))

    async def select_source(self, source: str, source_account: str = "") -> Dict[str, Any]:
        root = ET.Element("ContentItem", {"source": source, "sourceAccount": source_account})
        return await self._post_xml("/select", _xml_to_string(root))

    async def select_preset(self, preset_id: int) -> Dict[str, Any]:
        if preset_id < 1 or preset_id > 6:
            raise SoundTouchError("Preset id must be between 1 and 6")
        return await self.send_key(f"PRESET_{preset_id}")

    async def store_preset(
        self,
        preset_id: int,
        station_name: str,
        location_url: str,
        logo_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        if preset_id < 1 or preset_id > 6:
            raise SoundTouchError("Preset id must be between 1 and 6")
        return await self._post_xml(
            "/storePreset",
            _preset_xml(
                preset_id=preset_id,
                source="LOCAL_INTERNET_RADIO",
                location_url=location_url,
                station_name=station_name,
                logo_url=logo_url,
            ),
        )

    async def play_station_url(
        self,
        stream_url: str,
        station_name: str,
        logo_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        errors: List[str] = []
        if stream_url.lower().startswith("http://"):
            try:
                response = await self.play_url_via_dlna(stream_url)
                response["transport"] = "dlna"
                return response
            except SoundTouchError as exc:
                errors.append(f"DLNA: {exc}")

        for source in ("LOCAL_INTERNET_RADIO", "INTERNET_RADIO", "TUNEIN"):
            payload = _content_item_xml(
                source=source,
                stream_url=stream_url,
                station_name=station_name,
                logo_url=logo_url,
                item_type="stationurl",
            )
            try:
                response = await self._post_xml("/select", payload)
                response["transport"] = "select"
                response["source"] = source
                return response
            except SoundTouchError as exc:
                errors.append(f"{source}: {exc}")

        raise SoundTouchError("; ".join(errors))

    async def play_url_via_dlna(self, stream_url: str) -> Dict[str, Any]:
        if not stream_url.lower().startswith("http://"):
            raise SoundTouchError("DLNA URL playback requires an HTTP URL. Use the local proxy for HTTPS streams.")

        action = "urn:schemas-upnp-org:service:AVTransport:1#SetAVTransportURI"
        body = _dlna_set_uri_xml(stream_url)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.dlna_url}/AVTransport/Control",
                    content=body.encode("utf-8"),
                    headers={
                        "User-Agent": "SoundTouchLocal/1.0",
                        "Accept": "*/*",
                        "Content-Type": 'text/xml; charset="utf-8"',
                        "HOST": f"{self.host}:{self.dlna_port}",
                        "SOAPACTION": action,
                    },
                )
            except httpx.HTTPError as exc:
                raise SoundTouchError(str(exc)) from exc

        if response.status_code >= 400:
            raise SoundTouchError(f"DLNA returned HTTP {response.status_code}: {response.text[:300]}")
        return {"ok": True, "raw": response.text}

    async def _get_xml(self, path: str) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(f"{self.base_url}{path}")
            except httpx.HTTPError as exc:
                raise SoundTouchError(str(exc)) from exc
        return _parse_response(response)

    async def _post_xml(self, path: str, body: str) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}{path}",
                    content=body.encode("utf-8"),
                    headers={"Content-Type": "application/xml;charset=utf-8"},
                )
            except httpx.HTTPError as exc:
                raise SoundTouchError(str(exc)) from exc
        return _parse_response(response)

    def _key_xml(self, key: str, state: str) -> str:
        root = ET.Element("key", {"state": state, "sender": SENDER})
        root.text = key
        return _xml_to_string(root)


def _parse_response(response: httpx.Response) -> Dict[str, Any]:
    if response.status_code >= 400:
        raise SoundTouchError(f"SoundTouch returned HTTP {response.status_code}: {response.text[:300]}")
    text = response.text.strip()
    if not text:
        return {"ok": True}
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return {"ok": True, "raw": text}
    parsed = _element_to_dict(root)
    parsed["_tag"] = _strip_namespace(root.tag)
    return parsed


def _element_to_dict(element: ET.Element) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in element.attrib.items():
        result[key] = value

    children = list(element)
    if children:
        grouped: Dict[str, Any] = {}
        for child in children:
            tag = _strip_namespace(child.tag)
            child_value: Any
            if list(child) or child.attrib:
                child_value = _element_to_dict(child)
                if child.text and child.text.strip():
                    child_value["text"] = child.text.strip()
            else:
                child_value = child.text.strip() if child.text else ""

            if tag in grouped:
                if not isinstance(grouped[tag], list):
                    grouped[tag] = [grouped[tag]]
                grouped[tag].append(child_value)
            else:
                grouped[tag] = child_value
        result.update(grouped)
    elif element.text and element.text.strip():
        result["text"] = element.text.strip()

    return result


def _content_item_xml(
    source: str,
    stream_url: str,
    station_name: str,
    logo_url: Optional[str],
    item_type: str,
) -> str:
    root = ET.Element(
        "ContentItem",
        {
            "source": source,
            "sourceAccount": "",
            "location": stream_url,
            "type": item_type,
            "isPresetable": "true",
        },
    )
    item_name = ET.SubElement(root, "itemName")
    item_name.text = station_name
    if logo_url:
        container_art = ET.SubElement(root, "containerArt")
        container_art.text = logo_url
    return _xml_to_string(root)


def _preset_xml(
    preset_id: int,
    source: str,
    location_url: str,
    station_name: str,
    logo_url: Optional[str] = None,
) -> str:
    root = ET.Element("preset", {"id": str(preset_id)})
    item = ET.SubElement(
        root,
        "ContentItem",
        {
            "source": source,
            "type": "stationurl",
            "location": location_url,
            "sourceAccount": "",
            "isPresetable": "true",
        },
    )
    item_name = ET.SubElement(item, "itemName")
    item_name.text = station_name
    if logo_url:
        container_art = ET.SubElement(item, "containerArt")
        container_art.text = logo_url
    return _xml_to_string(root)


def _strip_namespace(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _xml_to_string(element: ET.Element) -> str:
    return ET.tostring(element, encoding="unicode", short_empty_elements=False)


def _dlna_set_uri_xml(stream_url: str) -> str:
    escaped_url = html.escape(stream_url, quote=False)
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
        's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
        "<s:Body>"
        '<u:SetAVTransportURI xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">'
        "<InstanceID>0</InstanceID>"
        f"<CurrentURI>{escaped_url}</CurrentURI>"
        "<CurrentURIMetaData></CurrentURIMetaData>"
        "</u:SetAVTransportURI>"
        "</s:Body>"
        "</s:Envelope>"
    )
