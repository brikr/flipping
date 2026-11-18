"""Runtime settings, all overridable via environment variables."""

import os
from dataclasses import dataclass
from pathlib import Path


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


@dataclass(frozen=True)
class Settings:
    # The wiki asks every client to send a descriptive User-Agent.
    user_agent: str = os.environ.get(
        "FLIPPING_USER_AGENT", "brik's flipping utilties (@minikori on Discord)"
    )
    api_base: str = os.environ.get(
        "FLIPPING_API_BASE", "https://prices.runescape.wiki/api/v1/osrs"
    )
    db_path: Path = Path(os.environ.get("FLIPPING_DB", "data/flipping.db"))
    host: str = os.environ.get("FLIPPING_HOST", "127.0.0.1")
    port: int = _int("FLIPPING_PORT", 8000)

    latest_interval_s: int = _int("FLIPPING_LATEST_INTERVAL", 60)
    # On an empty DB (or after downtime) backfill up to this many hours.
    backfill_hours: int = _int("FLIPPING_BACKFILL_HOURS", 24)
    # Granularity of that backfill. "1h" is gentle on the API (24h = ~25
    # requests instead of ~290) and is the default for local dev; the Docker
    # deploy sets "5m" for full-resolution history. Live collection is always 5m.
    backfill_step: str = os.environ.get("FLIPPING_BACKFILL_STEP", "1h")

    retention_days: int = _int("FLIPPING_RETENTION_DAYS", 30)
    # Set to 0 to run only the web UI (e.g. a dev copy reading a copied DB).
    collector_enabled: bool = os.environ.get("FLIPPING_COLLECTOR", "1") != "0"

    def __post_init__(self) -> None:
        if self.backfill_step not in ("5m", "1h"):
            raise ValueError("FLIPPING_BACKFILL_STEP must be '5m' or '1h'")


settings = Settings()
