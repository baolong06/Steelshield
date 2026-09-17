"""Local configuration for the server-configured LLM gateway.

Secrets are read from backend/.env or process environment and are never logged.
The gateway URL is operator-configured server side; clients cannot supply a target URL.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_LLM_HOST = "modelapi.vn"


def _load_dotenv(path: Path) -> None:
    """Load simple KEY=VALUE records without adding a runtime config dependency."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str
    model: str
    review_model: str
    reasoning_effort: str
    store: bool
    timeout_s: float
    live_llm_enabled: bool
    redis_url: str
    worker_lock_ttl_sec: int

    @property
    def egress_host(self) -> str:
        return urlsplit(self.base_url).hostname or ""

    def assert_allowed_gateway(self) -> None:
        parsed = urlsplit(self.base_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError(
                f"STEELSHIELD_LLM_BASE_URL must be an https URL; got {self.base_url!r}"
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    settings = Settings(
        api_key=os.environ.get("STEELSHIELD_LLM_API_KEY", "").strip(),
        base_url=os.environ.get(
            "STEELSHIELD_LLM_BASE_URL", f"https://{DEFAULT_LLM_HOST}/v1"
        ).rstrip("/"),
        model=os.environ.get("STEELSHIELD_LLM_MODEL", "gpt-5.6-sol").strip(),
        review_model=os.environ.get("STEELSHIELD_LLM_REVIEW_MODEL", "gpt-5.6-sol").strip(),
        reasoning_effort=os.environ.get("STEELSHIELD_LLM_REASONING_EFFORT", "xhigh").strip(),
        store=os.environ.get("STEELSHIELD_LLM_STORE", "false").lower() == "true",
        timeout_s=float(os.environ.get("STEELSHIELD_LLM_TIMEOUT_S", "60")),
        live_llm_enabled=os.environ.get("STEELSHIELD_LIVE_LLM", "0") == "1",
        redis_url=os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0").strip(),
        worker_lock_ttl_sec=int(os.environ.get("STEELSHIELD_WORKER_LOCK_TTL_SEC", "60")),
    )
    settings.assert_allowed_gateway()
    if settings.worker_lock_ttl_sec < 1:
        raise ValueError("STEELSHIELD_WORKER_LOCK_TTL_SEC must be at least 1")
    return settings
