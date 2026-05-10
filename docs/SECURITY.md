# Security Notes

SoundTouch Local Radio is designed for private LAN/WLAN use only.

## Recommended

- Run it only on your home network.
- Use `APP_AUTH_PASSWORD` if other people can access your LAN.
- Use Tailscale or WireGuard for remote access.
- Keep `.env` and `data/config.json` out of git.
- Use `SOUNDTOUCH_BLOCKLIST` if you have speakers that must not be contacted.

## Avoid

- Do not expose the app with router port forwarding.
- Do not put it directly on the public internet.
- Do not commit real speaker IPs, device IDs, passwords, or local hostnames.

## Authentication Limitation

The `/stream/...` endpoints are intentionally not protected by Basic Auth because the Bose speaker must fetch these URLs directly. Treat the app as a local network service.
