"""SQLite storage. Every call opens its own short-lived connection, so it is
safe to call from worker threads (asyncio.to_thread)."""

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    members     INTEGER NOT NULL,
    buy_limit   INTEGER,
    highalch    INTEGER,
    value       INTEGER
);

-- Current instabuy (high) / instasell (low) price per item. Overwritten each poll.
CREATE TABLE IF NOT EXISTS latest (
    item_id    INTEGER PRIMARY KEY,
    high       INTEGER,
    high_time  INTEGER,
    low        INTEGER,
    low_time   INTEGER
);

-- One row per item per price window. ts = window start (unix seconds), step =
-- window length in seconds: 300 for live 5m data, 3600 for hourly backfill.
-- Windows never overlap: backfill only fetches periods nothing covers yet.
-- ts-first PK makes "all items over the last N hours" (the screener) cheap;
-- the secondary index serves single-item history.
CREATE TABLE IF NOT EXISTS prices (
    ts        INTEGER NOT NULL,
    step      INTEGER NOT NULL,
    item_id   INTEGER NOT NULL,
    avg_high  INTEGER,
    high_vol  INTEGER NOT NULL,
    avg_low   INTEGER,
    low_vol   INTEGER NOT NULL,
    PRIMARY KEY (ts, step, item_id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS prices_item ON prices (item_id, ts);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@contextmanager
def connect(path: Path | None = None):
    path = path or settings.db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init(path: Path | None = None) -> None:
    with connect(path) as c:
        c.executescript(SCHEMA)


def get_meta(key: str) -> str | None:
    with connect() as c:
        row = c.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_meta(key: str, value: str | int | float) -> None:
    with connect() as c:
        c.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )


def save_mapping(items: list[dict]) -> None:
    rows = [
        (
            i["id"],
            i["name"],
            int(i.get("members", False)),
            i.get("limit"),
            i.get("highalch"),
            i.get("value"),
        )
        for i in items
    ]
    with connect() as c:
        c.executemany(
            "INSERT INTO items (id, name, members, buy_limit, highalch, value) "
            "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
            "name=excluded.name, members=excluded.members, buy_limit=excluded.buy_limit, "
            "highalch=excluded.highalch, value=excluded.value",
            rows,
        )


def save_latest(data: dict[str, dict]) -> None:
    rows = [
        (int(k), v.get("high"), v.get("highTime"), v.get("low"), v.get("lowTime"))
        for k, v in data.items()
    ]
    with connect() as c:
        c.executemany(
            "INSERT INTO latest (item_id, high, high_time, low, low_time) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(item_id) DO UPDATE SET "
            "high=excluded.high, high_time=excluded.high_time, "
            "low=excluded.low, low_time=excluded.low_time",
            rows,
        )


def save_window(ts: int, step: int, data: dict[str, dict]) -> int:
    rows = [
        (
            ts,
            step,
            int(k),
            v.get("avgHighPrice"),
            v.get("highPriceVolume") or 0,
            v.get("avgLowPrice"),
            v.get("lowPriceVolume") or 0,
        )
        for k, v in data.items()
    ]
    with connect() as c:
        c.executemany(
            "INSERT OR REPLACE INTO prices "
            "(ts, step, item_id, avg_high, high_vol, avg_low, low_vol) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
    return len(rows)


def covered_slots(since: int) -> set[int]:
    """Start times of every 5m slot (since `since`) that some stored window covers.
    An hourly row covers its 12 slots."""
    with connect() as c:
        rows = c.execute(
            "SELECT DISTINCT ts, step FROM prices WHERE ts + step > ?", (since,)
        ).fetchall()
    return {t for r in rows for t in range(r["ts"], r["ts"] + r["step"], 300)}


def prune(retention_days: int) -> int:
    cutoff = int(time.time()) - retention_days * 86400
    with connect() as c:
        n = c.execute("DELETE FROM prices WHERE ts < ?", (cutoff,)).rowcount
    return n


def item_history(item_id: int, since: int) -> list[dict]:
    with connect() as c:
        rows = c.execute(
            "SELECT ts, step, avg_high, high_vol, avg_low, low_vol FROM prices "
            "WHERE item_id = ? AND ts >= ? ORDER BY ts",
            (item_id, since),
        ).fetchall()
    return [dict(r) for r in rows]


def stats() -> dict:
    with connect() as c:
        row = c.execute(
            "SELECT COUNT(*) AS rows, MIN(ts) AS first_ts, MAX(ts) AS last_ts FROM prices"
        ).fetchone()
        hourly = c.execute("SELECT COUNT(DISTINCT ts) FROM prices WHERE step = 3600").fetchone()[0]
        items = c.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    return {
        "items": items,
        "rows": row["rows"],
        "first_ts": row["first_ts"],
        "last_ts": row["last_ts"],
        "hourly_windows": hourly,
    }
