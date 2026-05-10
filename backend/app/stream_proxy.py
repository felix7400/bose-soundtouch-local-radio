from __future__ import annotations

from typing import AsyncIterator

import httpx
from fastapi import HTTPException
from starlette.responses import StreamingResponse

from .models import Station


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


async def proxy_station_stream(station: Station) -> StreamingResponse:
    client = httpx.AsyncClient(timeout=None, follow_redirects=True)
    try:
        request = client.build_request(
            "GET",
            station.stream_url,
            headers={"User-Agent": "SoundTouchLocal/1.0"},
        )
        upstream = await client.send(request, stream=True)
    except httpx.HTTPError as exc:
        await client.aclose()
        raise HTTPException(status_code=502, detail=f"Could not open upstream stream: {exc}") from exc

    if upstream.status_code >= 400:
        detail = f"Upstream returned HTTP {upstream.status_code}"
        await upstream.aclose()
        await client.aclose()
        raise HTTPException(status_code=502, detail=detail)

    headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() in {"content-type", "icy-name", "icy-metaint"}
    }

    async def iterator() -> AsyncIterator[bytes]:
        try:
            async for chunk in upstream.aiter_bytes(64 * 1024):
                if chunk:
                    yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(iterator(), media_type=headers.get("content-type", "audio/mpeg"), headers=headers)

