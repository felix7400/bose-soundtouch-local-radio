# SoundTouch Local Radio

Local web controller for Bose SoundTouch speakers after official SoundTouch support ended. The goal is to keep existing speakers useful on a private home network without depending on Bose cloud services, public internet exposure, port forwarding, or Docker.

This project was published because SoundTouch support ended and the speakers can still be controlled through their local LAN/WLAN APIs.

## Features

- Local-only FastAPI backend and React/TypeScript frontend.
- Speaker discovery or manual speaker IP configuration.
- Basic speaker controls: play/stop toggle, volume, standby, status.
- Local internet radio station library with name, stream URL, image, and tags.
- Favorites and station filters for fast mobile use.
- Local stream proxy for HTTPS or otherwise unreachable radio streams.
- DLNA/UPnP playback fallback for SoundTouch firmware that rejects free radio URLs through `/select`.
- Dark mode by default with a light mode switch.
- Optional Basic Auth for the local web UI/API.
- Raspberry Pi-friendly setup; Docker is not required.

## What This Is Not

- Not a cloud service.
- Not a public remote-access service.
- Not a replacement for Bose account features, Spotify, Amazon Music, or TuneIn cloud services.
- Not a reliable way to reprogram the physical preset buttons on every SoundTouch model. Some firmware accepts stored local presets, some does not.

## Requirements

- Python 3.8+
- Node.js 18+ and npm
- A Bose SoundTouch speaker reachable from the same LAN/WLAN
- No port forwarding

## Quick Start

```bash
git clone <repo-url> soundtouch-local-radio
cd soundtouch-local-radio
scripts/setup.sh
scripts/run_app.sh
```

Open on the same machine:

```text
http://127.0.0.1:8000
```

Open from a phone on the same Wi-Fi:

```text
http://YOUR_COMPUTER_LAN_IP:8000
```

The app shows the detected LAN URL in the footer. If mDNS/Avahi is available, you can also configure a local name such as:

```text
http://soundtouch.local:8000
```

## Configuration

`scripts/setup.sh` creates `.env` from `.env.example`. Edit `.env` for local settings:

```bash
APP_HOST=0.0.0.0
APP_PORT=8000
APP_ALIAS_HOST=soundtouch.local

SOUNDTOUCH_HOST=
SOUNDTOUCH_PORT=8090
SOUNDTOUCH_DLNA_PORT=8091

APP_AUTH_USERNAME=admin
APP_AUTH_PASSWORD=

APP_STREAM_BASE_URL=
```

Important local values:

- `SOUNDTOUCH_HOST`: set this to the speaker IP if discovery does not find it.
- `APP_STREAM_BASE_URL`: set this to `http://YOUR_COMPUTER_LAN_IP:8000` if the speaker cannot fetch proxied streams through the browser hostname.
- `APP_AUTH_PASSWORD`: optional local Basic Auth password.
- `SOUNDTOUCH_BLOCKLIST`: comma-separated speaker IPs/hosts that must never be contacted.
- `SOUNDTOUCH_ENABLE_SSDP=false`: useful when you have another SoundTouch speaker in the same network that should not answer multicast discovery.

`.env`, generated local config, virtual environments, node modules, and builds are intentionally ignored by git.

## Speaker Diagnostic

Run this before using the full app:

```bash
source .venv/bin/activate
python scripts/diagnose_soundtouch.py
```

If discovery fails:

```bash
python scripts/diagnose_soundtouch.py --host SPEAKER_IP
```

The diagnostic should print the speaker name, model, device ID, volume, and current source.

## Radio Playback Notes

Many SoundTouch speakers still accept local control on port `8090`, but cloud-backed station presets may stop working when Bose/TuneIn support is unavailable. This app avoids that path for browser playback:

- The app stores station definitions locally in `data/stations.json`.
- The speaker gets a LAN URL such as `/stream/STATION_ID` when proxy playback is needed.
- For SoundTouch 10 firmware that rejects custom radio via `/select`, the app uses DLNA/UPnP URL playback on port `8091`.
- The proxy forwards stream bytes. It does not transcode audio.

If a stream does not play, try another MP3/AAC stream URL first. A future transcoding fallback would require `ffmpeg` and is deliberately not part of the default setup.

## Manual Test

1. Run `scripts/setup.sh`.
2. Run `python scripts/diagnose_soundtouch.py --host SPEAKER_IP`.
3. Run `scripts/run_app.sh`.
4. Open `http://127.0.0.1:8000`.
5. Configure or discover the speaker.
6. Start a known working station.
7. Move the volume slider.
8. Open the LAN URL from a phone on the same Wi-Fi and repeat a playback action.

## Raspberry Pi

```bash
sudo apt update
sudo apt install -y python3 python3-venv nodejs npm
git clone <repo-url> ~/soundtouch-local-radio
cd ~/soundtouch-local-radio
scripts/setup.sh
scripts/run_app.sh
```

If the OS package manager provides an old Node.js version, install a current LTS Node.js release before running `scripts/setup.sh`.

Optional systemd unit:

```bash
sudo cp docs/soundtouch-local.service /etc/systemd/system/soundtouch-local.service
sudo systemctl daemon-reload
sudo systemctl enable --now soundtouch-local
```

Edit the service file first if your checkout path or Linux user differs from `/home/pi/soundtouch-local-radio`.

## Safe Remote Access

Do not expose this app with port forwarding.

If you need remote access, use a private network overlay:

- Tailscale
- WireGuard

For remote access, enable `APP_AUTH_PASSWORD`.

## Development

Backend tests:

```bash
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests
```

Frontend build:

```bash
cd frontend
npm run build
```

Development server:

```bash
scripts/run_dev.sh
```

## Privacy

Do not commit `.env` or `data/config.json`. They may contain local IP addresses, hostnames, blocklists, and speaker configuration. The repository includes only source code, scripts, docs, and reusable station definitions.
