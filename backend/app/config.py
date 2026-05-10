from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("APP_DATA_DIR", PROJECT_ROOT / "data")).resolve()
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_env_file(PROJECT_ROOT / ".env")


class Settings:
    def __init__(self) -> None:
        self.app_host = os.getenv("APP_HOST", "0.0.0.0")
        self.app_port = int(os.getenv("APP_PORT", "8000"))
        self.app_alias_host = os.getenv("APP_ALIAS_HOST", "").strip() or None
        self.soundtouch_host = os.getenv("SOUNDTOUCH_HOST", "").strip() or None
        self.soundtouch_port = int(os.getenv("SOUNDTOUCH_PORT", "8090"))
        self.soundtouch_dlna_port = int(os.getenv("SOUNDTOUCH_DLNA_PORT", "8091"))
        self.soundtouch_blocklist = _csv_values(os.getenv("SOUNDTOUCH_BLOCKLIST", ""))
        self.soundtouch_enable_ssdp = _truthy(os.getenv("SOUNDTOUCH_ENABLE_SSDP", "true"))
        self.auth_username = os.getenv("APP_AUTH_USERNAME", "admin")
        self.auth_password = os.getenv("APP_AUTH_PASSWORD", "").strip()
        self.app_base_url = normalize_base_url(os.getenv("APP_BASE_URL", "").strip())
        self.app_stream_base_url = normalize_base_url(os.getenv("APP_STREAM_BASE_URL", "").strip())

    @property
    def auth_enabled(self) -> bool:
        return bool(self.auth_password)


def normalize_base_url(value: str) -> Optional[str]:
    if not value:
        return None
    return value.rstrip("/")


def _csv_values(value: str) -> set:
    return {item.strip() for item in value.split(",") if item.strip()}


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


settings = Settings()
DATA_DIR.mkdir(parents=True, exist_ok=True)
