"""FastAPI app: serves the dashboard + JSON API and runs the collector in-process."""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import uvicorn
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse

from . import db, screener
from .collector import Collector
from .config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
STATIC = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    collector = Collector() if settings.collector_enabled else None
    if collector:
        await collector.start()
    app.state.collector = collector
    yield
    if collector:
        await collector.stop()


app = FastAPI(title="OSRS Flipping", lifespan=lifespan)


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/api/status")
async def status():
    c: Collector | None = app.state.collector
    return {
        "now": time.time(),
        "collector": c.status if c else None,
        "db": await asyncio.to_thread(db.stats),
    }


@app.get("/api/flips")
async def flips(
    budget: int | None = Query(None, ge=1),
    min_volume: int = 10,
    min_roi: float = 0.0,
    min_margin: int = 1,
    max_age_min: int = 30,
    members: Literal["all", "members", "f2p"] = "all",
    history_hours: int = Query(6, ge=1, le=72),
    sort: Literal["profit", "margin", "roi", "volume", "stability"] = "profit",
    limit: int = Query(100, ge=1, le=1000),
):
    p = screener.ScreenParams(
        budget=budget,
        min_volume=min_volume,
        min_roi=min_roi,
        min_margin=min_margin,
        max_age_min=max_age_min,
        members={"all": None, "members": True, "f2p": False}[members],
        history_hours=history_hours,
        sort=sort,
        limit=limit,
    )
    return await asyncio.to_thread(screener.run, p)


@app.get("/api/items/{item_id}/history")
async def history(item_id: int, hours: int = Query(24, ge=1, le=24 * 90)):
    return await asyncio.to_thread(db.item_history, item_id, int(time.time()) - hours * 3600)


def main() -> None:
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
