#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.discovery import discover_soundtouch_devices, probe_soundtouch_host  # noqa: E402
from app.soundtouch import SoundTouchClient, SoundTouchError  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser(description="Probe Bose SoundTouch speakers on the local network.")
    parser.add_argument("--host", help="Speaker IP address or hostname. If omitted, discovery is attempted.")
    parser.add_argument("--port", type=int, default=8090, help="SoundTouch HTTP API port.")
    args = parser.parse_args()

    if args.host:
        device = await probe_soundtouch_host(args.host, args.port)
        if not device:
            print(f"No SoundTouch API response from {args.host}:{args.port}")
            return 2
        devices = [device]
    else:
        print("Searching for SoundTouch speakers with SSDP and a local /24 port 8090 probe...")
        devices = await discover_soundtouch_devices()

    if not devices:
        print("No SoundTouch speakers found.")
        print("Try: python scripts/diagnose_soundtouch.py --host SPEAKER_IP")
        return 1

    for device in devices:
        print(f"Found: {device.name or 'Unknown SoundTouch'} at {device.host}:{device.port}")
        if device.model:
            print(f"Model: {device.model}")
        client = SoundTouchClient(device.host, device.port)
        try:
            info = await client.get_info()
            volume = await client.get_volume()
            now_playing = await client.get_now_playing()
        except SoundTouchError as exc:
            print(f"Connected, but a status request failed: {exc}")
            return 3
        print(f"Device ID: {info.get('deviceID', 'unknown')}")
        print(f"Volume: {volume.get('actualvolume') or volume.get('targetvolume') or volume}")
        print(f"Now playing source: {now_playing.get('source', 'unknown')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

