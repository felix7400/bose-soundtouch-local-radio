from __future__ import annotations

import re
from typing import Dict, Optional

import httpx

from .models import Station, StationMetadata


STREAM_TITLE_RE = re.compile(r"StreamTitle='([^']*)';?", re.IGNORECASE)
STREAM_URL_RE = re.compile(r"StreamUrl='([^']*)';?", re.IGNORECASE)


async def read_station_metadata(station: Station) -> StationMetadata:
    headers = {
        "Icy-MetaData": "1",
        "User-Agent": "SoundTouchLocal/1.0",
        "Accept": "*/*",
    }
    timeout = httpx.Timeout(8.0, connect=4.0, read=8.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        try:
            async with client.stream("GET", station.stream_url, headers=headers) as response:
                response.raise_for_status()
                icy_headers = _icy_headers(response.headers)
                raw_metadata = await _read_icy_metadata(response)
        except httpx.HTTPError as exc:
            return StationMetadata(station_id=station.id, station_name=station.name, error=str(exc))

    parsed = _parse_icy_metadata(raw_metadata)
    title = parsed.get("StreamTitle") or None
    artist, track = _split_title(title)
    return StationMetadata(
        station_id=station.id,
        station_name=station.name,
        title=title,
        artist=artist,
        track=track,
        stream_url=parsed.get("StreamUrl") or None,
        icy_name=icy_headers.get("icy-name"),
        icy_genre=icy_headers.get("icy-genre"),
        raw=raw_metadata,
    )


async def _read_icy_metadata(response: httpx.Response) -> Optional[str]:
    metaint_header = response.headers.get("icy-metaint")
    if not metaint_header:
        return None
    try:
        metaint = int(metaint_header)
    except ValueError:
        return None

    buffer = bytearray()
    max_bytes = min(max(metaint + 4096, 8192), 512 * 1024)
    async for chunk in response.aiter_bytes():
        buffer.extend(chunk)
        if len(buffer) <= metaint:
            if len(buffer) > max_bytes:
                return None
            continue

        metadata_length = buffer[metaint] * 16
        if metadata_length == 0:
            return None
        end = metaint + 1 + metadata_length
        if len(buffer) >= end:
            raw = bytes(buffer[metaint + 1 : end]).rstrip(b"\0")
            return raw.decode("utf-8", errors="replace").strip() or None
        if len(buffer) > max_bytes:
            return None
    return None


def _parse_icy_metadata(raw: Optional[str]) -> Dict[str, str]:
    if not raw:
        return {}
    parsed: Dict[str, str] = {}
    title_match = STREAM_TITLE_RE.search(raw)
    if title_match:
        parsed["StreamTitle"] = title_match.group(1).strip()
    url_match = STREAM_URL_RE.search(raw)
    if url_match:
        parsed["StreamUrl"] = url_match.group(1).strip()
    return parsed


def _split_title(title: Optional[str]) -> tuple:
    if not title:
        return None, None
    separators = [" - ", " – ", " — "]
    for separator in separators:
        if separator in title:
            artist, track = title.split(separator, 1)
            return artist.strip() or None, track.strip() or None
    return None, title


def _icy_headers(headers: httpx.Headers) -> Dict[str, str]:
    return {
        key.lower(): value
        for key, value in headers.items()
        if key.lower().startswith("icy-") or key.lower().startswith("ice-")
    }
