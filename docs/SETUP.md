# Setup Guide

This guide keeps setup local and simple. No Docker, cloud account, or port forwarding is required.

## Laptop

```bash
git clone <repo-url> soundtouch-local-radio
cd soundtouch-local-radio
scripts/setup.sh
scripts/run_app.sh
```

Open:

```text
http://127.0.0.1:8000
```

For phones in the same WLAN, use:

```text
http://YOUR_COMPUTER_LAN_IP:8000
```

## Speaker IP

If discovery fails, find the speaker IP in your router UI and test it:

```bash
source .venv/bin/activate
python scripts/diagnose_soundtouch.py --host SPEAKER_IP
```

Then either enter the IP in the web UI or set:

```bash
SOUNDTOUCH_HOST=SPEAKER_IP
```

## Stream Proxy Base URL

If the web UI starts stations but the speaker stays silent, the speaker may not be able to reach the generated proxy URL. Set:

```bash
APP_STREAM_BASE_URL=http://YOUR_COMPUTER_LAN_IP:8000
```

Restart `scripts/run_app.sh`.

## Optional Password

```bash
APP_AUTH_USERNAME=admin
APP_AUTH_PASSWORD=choose-a-local-password
```

The radio stream proxy remains unauthenticated because the speaker must fetch stream URLs directly. Keep the app on your private LAN.

## Raspberry Pi systemd

Copy the sample unit:

```bash
sudo cp docs/soundtouch-local.service /etc/systemd/system/soundtouch-local.service
```

Edit paths and user if needed:

```text
WorkingDirectory=/home/pi/soundtouch-local-radio
EnvironmentFile=/home/pi/soundtouch-local-radio/.env
User=pi
```

Enable:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now soundtouch-local
sudo systemctl status soundtouch-local
```
