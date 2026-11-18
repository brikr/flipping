"""Background loops that keep the local DB in sync with the wiki API.

- mapping: item names / buy limits, refreshed daily
- latest:  instabuy/instasell prices, every FLIPPING_LATEST_INTERVAL seconds
- 5m:      volume + average prices per 5-minute window, with gap filling so a
           restart or NAS reboot doesn't leave holes in the history. Gaps are
           filled at FLIPPING_BACKFILL_STEP granularity (see plan_backfill).
- prune:   drops 5m rows older than FLIPPING_RETENTION_DAYS, daily
"""

import asyncio
import logging
import time

from . import db
from .config import settings
from .wiki import WikiClient

log = logging.getLogger("flipping.collector")

FIVE_MIN = 300
HOUR = 3600
DAY = 86400


def plan_backfill(
    newest_5m: int,
    horizon: int,
    covered: set[int],
    step: int,
    latest_hour: int | None = None,
) -> list[tuple[int, int]]:
    """Windows to fetch, newest first, as (start ts, step) pairs.

    covered: start times of 5m slots already stored (an hourly row covers 12).
    step=300: every uncovered 5m slot back to `horizon`.
    step=3600: whole hours with no coverage at all, back to `horizon`, using
      the /1h endpoint (newest available: `latest_hour`). /1h lags real time
      by ~2h, so the stretch between the newest hour and the live 5m data is
      filled with 5m windows. Hours that are partly covered are left alone.
    """
    if step == FIVE_MIN:
        return [(t, FIVE_MIN) for t in range(newest_5m - FIVE_MIN, horizon - 1, -FIVE_MIN) if t not in covered]

    assert latest_hour is not None
    hourly_end = latest_hour + HOUR
    tail = [
        (t, FIVE_MIN)
        for t in range(newest_5m - FIVE_MIN, max(hourly_end, horizon) - 1, -FIVE_MIN)
        if t not in covered
    ]
    hours = [
        (h, HOUR)
        for h in range(latest_hour, horizon - HOUR, -HOUR)
        if not any(t in covered for t in range(h, h + HOUR, FIVE_MIN))
    ]
    return tail + hours


async def _forever(name: str, interval: float, fn) -> None:
    while True:
        started = time.monotonic()
        try:
            await fn()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("%s failed; retrying next cycle", name)
        await asyncio.sleep(max(5.0, interval - (time.monotonic() - started)))


class Collector:
    def __init__(self) -> None:
        self.wiki = WikiClient()
        self.status: dict[str, float | int | None] = {
            "latest_fetched_at": None,
            "last_5m_window": None,
            "backfill_remaining": 0,
            "backfill_step": settings.backfill_step,
        }
        self._hour_cache: tuple[float, int, dict] | None = None
        self._tasks: list[asyncio.Task] = []

    async def refresh_mapping(self) -> None:
        last = float(await asyncio.to_thread(db.get_meta, "mapping_fetched_at") or 0)
        if time.time() - last < DAY:
            return
        items = await self.wiki.mapping()
        await asyncio.to_thread(db.save_mapping, items)
        await asyncio.to_thread(db.set_meta, "mapping_fetched_at", time.time())
        log.info("mapping refreshed: %d items", len(items))

    async def poll_latest(self) -> None:
        data = await self.wiki.latest()
        await asyncio.to_thread(db.save_latest, data)
        self.status["latest_fetched_at"] = time.time()

    async def sync_5m(self) -> None:
        newest_ts, data = await self.wiki.window(FIVE_MIN)
        await asyncio.to_thread(db.save_window, newest_ts, FIVE_MIN, data)
        self.status["last_5m_window"] = newest_ts
        await self.backfill(newest_ts)

    async def _latest_hour(self) -> tuple[int, dict]:
        """Newest available /1h window, cached for an hour (it lags ~2h anyway)."""
        if self._hour_cache is None or time.time() - self._hour_cache[0] > HOUR:
            ts, data = await self.wiki.window(HOUR)
            self._hour_cache = (time.time(), ts, data)
        return self._hour_cache[1], self._hour_cache[2]

    async def backfill(self, newest_5m: int) -> None:
        horizon = newest_5m - settings.backfill_hours * HOUR
        covered = await asyncio.to_thread(db.covered_slots, horizon)
        if not any(t not in covered for t in range(newest_5m, horizon, -FIVE_MIN)):
            return
        step = FIVE_MIN if settings.backfill_step == "5m" else HOUR
        latest_hour, latest_hour_data = (None, None)
        if step == HOUR:
            latest_hour, latest_hour_data = await self._latest_hour()
        todo = plan_backfill(newest_5m, horizon, covered, step, latest_hour)
        self.status["backfill_remaining"] = len(todo)
        if todo:
            log.info(
                "backfilling %d windows (%d hourly, %d 5m)",
                len(todo),
                sum(s == HOUR for _, s in todo),
                sum(s == FIVE_MIN for _, s in todo),
            )
        for ts, win in todo:
            if win == HOUR and ts == latest_hour:
                data = latest_hour_data  # already fetched
            else:
                ts, data = await self.wiki.window(win, ts)
                await asyncio.sleep(1)  # be polite to the wiki
            await asyncio.to_thread(db.save_window, ts, win, data)
            self.status["backfill_remaining"] -= 1

    async def _5m_loop(self) -> None:
        # Windows close on 5-minute boundaries; poll ~30s after each one.
        while True:
            try:
                await self.sync_5m()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("5m sync failed; retrying next window")
            now = time.time()
            await asyncio.sleep(FIVE_MIN - (now % FIVE_MIN) + 30)

    async def _prune(self) -> None:
        n = await asyncio.to_thread(db.prune, settings.retention_days)
        if n:
            log.info("pruned %d old 5m rows", n)

    async def start(self) -> None:
        try:
            await self.refresh_mapping()  # screener needs names/limits first
        except Exception:
            log.exception("initial mapping fetch failed; will retry hourly")
        self._tasks = [
            asyncio.create_task(_forever("mapping", 3600, self.refresh_mapping)),
            asyncio.create_task(_forever("latest", settings.latest_interval_s, self.poll_latest)),
            asyncio.create_task(self._5m_loop()),
            asyncio.create_task(_forever("prune", DAY, self._prune)),
        ]

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        await self.wiki.aclose()
