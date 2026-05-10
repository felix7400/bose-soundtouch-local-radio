from __future__ import annotations

import asyncio
import ipaddress
import socket
import urllib.parse
from typing import Dict, Iterable, List, Optional, Set

import httpx

from .models import DiscoveredDevice
from .config import settings
from .soundtouch import SoundTouchClient, SoundTouchError


SSDP_ADDRESS = ("239.255.255.250", 1900)
SSDP_TARGETS = ["urn:schemas-upnp-org:device:MediaRenderer:1", "ssdp:all"]


async def discover_soundtouch_devices(timeout: float = 3.0) -> List[DiscoveredDevice]:
    devices: Dict[str, DiscoveredDevice] = {}
    if settings.soundtouch_enable_ssdp and not settings.soundtouch_blocklist:
        for device in await _discover_via_ssdp(timeout):
            if not is_blocked_host(device.host):
                devices[f"{device.host}:{device.port}"] = device

    candidates = [
        host
        for host in await _candidate_subnet_hosts()
        if f"{host}:8090" not in devices and not is_blocked_host(host)
    ]
    for device in await _probe_hosts(candidates):
        devices[f"{device.host}:{device.port}"] = device

    return sorted(devices.values(), key=lambda item: (item.name or "", item.host))


async def probe_soundtouch_host(host: str, port: int = 8090) -> Optional[DiscoveredDevice]:
    if is_blocked_host(host):
        return None
    return await _probe_host(host, port=port, source="manual")


async def _discover_via_ssdp(timeout: float) -> List[DiscoveredDevice]:
    return await _run_in_thread(_ssdp_search_sync, timeout)


def _ssdp_search_sync(timeout: float) -> List[DiscoveredDevice]:
    found: Dict[str, DiscoveredDevice] = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as sock:
        sock.settimeout(timeout)
        for target in SSDP_TARGETS:
            message = "\r\n".join(
                [
                    "M-SEARCH * HTTP/1.1",
                    f"HOST: {SSDP_ADDRESS[0]}:{SSDP_ADDRESS[1]}",
                    'MAN: "ssdp:discover"',
                    "MX: 2",
                    f"ST: {target}",
                    "",
                    "",
                ]
            )
            sock.sendto(message.encode("utf-8"), SSDP_ADDRESS)

        while True:
            try:
                data, address = sock.recvfrom(4096)
            except socket.timeout:
                break
            headers = _parse_ssdp_headers(data.decode("utf-8", errors="ignore"))
            haystack = " ".join(headers.values()).lower()
            if "soundtouch" not in haystack and "bose" not in haystack:
                continue
            location = headers.get("location")
            host = _host_from_location(location) or address[0]
            found[host] = DiscoveredDevice(host=host, source="ssdp", location=location)
    return list(found.values())


def _parse_ssdp_headers(payload: str) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    for line in payload.splitlines()[1:]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    return headers


def _host_from_location(location: Optional[str]) -> Optional[str]:
    if not location:
        return None
    parsed = urllib.parse.urlparse(location)
    return parsed.hostname


async def _candidate_subnet_hosts(limit: int = 512) -> Set[str]:
    hosts = await _run_in_thread(_local_subnet_hosts_sync, limit)
    return hosts


def _local_subnet_hosts_sync(limit: int) -> Set[str]:
    candidates: Set[str] = set()
    for ip in _local_ipv4_addresses():
        network = ipaddress.ip_network(f"{ip}/24", strict=False)
        for host in network.hosts():
            if str(host) != ip:
                candidates.add(str(host))
            if len(candidates) >= limit:
                return candidates
    return candidates


def _local_ipv4_addresses() -> Iterable[str]:
    addresses: Set[str] = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            addresses.add(sock.getsockname()[0])
    except OSError:
        pass
    try:
        hostname = socket.gethostname()
        for result in socket.getaddrinfo(hostname, None, socket.AF_INET):
            addresses.add(result[4][0])
    except OSError:
        pass
    return [address for address in addresses if not address.startswith("127.")]


async def _probe_host(host: str, port: int = 8090, source: str = "subnet-scan") -> Optional[DiscoveredDevice]:
    if is_blocked_host(host):
        return None
    try:
        async with httpx.AsyncClient(timeout=0.8) as client:
            response = await client.get(f"http://{host}:{port}/info")
            if response.status_code >= 400 or "SoundTouch" not in response.text:
                return None
        info = await SoundTouchClient(host, port, timeout=1.5).get_info()
    except (httpx.HTTPError, SoundTouchError, OSError):
        return None

    return DiscoveredDevice(
        host=host,
        port=port,
        name=_text_field(info, "name"),
        model=_text_field(info, "type"),
        device_id=info.get("deviceID"),
        source=source,
    )


async def _probe_hosts(hosts: List[str], concurrency: int = 64) -> List[DiscoveredDevice]:
    semaphore = asyncio.Semaphore(concurrency)

    async def probe(host: str) -> Optional[DiscoveredDevice]:
        async with semaphore:
            return await _probe_host(host)

    results = await asyncio.gather(*(probe(host) for host in hosts))
    return [device for device in results if device is not None]


def _text_field(payload: Dict[str, object], key: str) -> Optional[str]:
    value = payload.get(key)
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str):
            return text
    return None


def is_blocked_host(host: str) -> bool:
    return host in settings.soundtouch_blocklist


async def _run_in_thread(function, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: function(*args))
