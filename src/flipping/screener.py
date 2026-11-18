"""Rank items by estimated flip profit.

For each item:
  buy     = latest instasell price ("low")  -> where a patient buy offer fills
  sell    = latest instabuy price ("high")  -> where a patient sell offer fills
  margin  = sell - GE tax - buy
  vol_1h  = min(units bought, units sold) per hour, measured over the last
            hour of stored windows (see hourly_volume)
  qty     = min(buy limit, what the budget affords, vol_1h)
            (one hour of real volume is a deliberately conservative proxy for
            how much of a 4h buy limit you can realistically fill)
  profit  = margin * qty  -> estimated gp per 4h buy-limit window

Stability comes from stored history: of the windows (5m, or 1h where the
history was backfilled hourly) in the lookback where
the item traded on both sides, how many had a positive post-tax margin, and
what the median margin was. A big margin that only appeared in the last few
minutes scores low.
"""

import statistics
import time
from dataclasses import asdict, dataclass

from . import db
from .tax import ge_tax, post_tax_margin


@dataclass
class ScreenParams:
    budget: int | None = None  # gp available; None = unlimited
    min_volume: int = 10  # min 1h matched volume
    min_roi: float = 0.0  # percent
    min_margin: int = 1
    max_age_min: int = 30  # ignore prices older than this
    members: bool | None = None  # None = both, False = F2P only
    history_hours: int = 6
    sort: str = "profit"  # profit | margin | roi | volume | stability
    limit: int = 100


@dataclass
class Flip:
    id: int
    name: str
    members: bool
    buy: int
    sell: int
    tax: int
    margin: int
    roi: float
    buy_limit: int | None
    vol_1h: int
    qty: int
    profit: int
    stability: float | None  # 0-1, share of recent windows with a positive margin
    median_margin: int | None
    windows: int  # how many history windows the stability is based on
    age_min: float  # age of the older of the two latest prices


def screen(
    items: dict[int, dict],
    latest: dict[int, dict],
    vol_1h: dict[int, int],
    history: dict[int, list[tuple[int, int]]],
    p: ScreenParams,
    now: float,
) -> list[Flip]:
    out: list[Flip] = []
    for item_id, lp in latest.items():
        it = items.get(item_id)
        buy, sell = lp.get("low"), lp.get("high")
        if not it or not buy or not sell:
            continue
        if p.members is not None and bool(it["members"]) != p.members:
            continue
        oldest = min(lp.get("low_time") or 0, lp.get("high_time") or 0)
        age_min = (now - oldest) / 60
        if age_min > p.max_age_min:
            continue

        name = it["name"]
        margin = post_tax_margin(buy, sell, name)
        roi = 100 * margin / buy
        vol = vol_1h.get(item_id, 0)
        if margin < p.min_margin or roi < p.min_roi or vol < p.min_volume:
            continue
        if p.budget is not None and buy > p.budget:
            continue

        limit = it["buy_limit"]
        qty = vol if limit is None else min(limit, vol)
        if p.budget is not None:
            qty = min(qty, p.budget // buy)

        hist = [post_tax_margin(lo, hi, name) for hi, lo in history.get(item_id, [])]
        out.append(
            Flip(
                id=item_id,
                name=name,
                members=bool(it["members"]),
                buy=buy,
                sell=sell,
                tax=ge_tax(sell, name),
                margin=margin,
                roi=round(roi, 2),
                buy_limit=limit,
                vol_1h=vol,
                qty=qty,
                profit=margin * qty,
                stability=round(sum(m > 0 for m in hist) / len(hist), 2) if hist else None,
                median_margin=int(statistics.median(hist)) if hist else None,
                windows=len(hist),
                age_min=round(age_min, 1),
            )
        )

    key = {
        "profit": lambda f: f.profit,
        "margin": lambda f: f.margin,
        "roi": lambda f: f.roi,
        "volume": lambda f: f.vol_1h,
        "stability": lambda f: (f.stability or 0, f.profit),
    }.get(p.sort, lambda f: f.profit)
    out.sort(key=key, reverse=True)
    return out[: p.limit]


def hourly_volume(rows, now: float, lookback: int = 3600) -> dict[int, int]:
    """Matched volume per hour for each item.

    rows: (item_id, ts, step, high_vol, low_vol) for windows overlapping the
    lookback. A window partly inside the lookback contributes pro rata, and the
    total is scaled by how much of the lookback stored windows actually cover,
    so hourly backfill, 5m data, and gaps all give comparable per-hour numbers.
    """
    start = now - lookback
    hi: dict[int, float] = {}
    lo: dict[int, float] = {}
    windows: dict[int, float] = {}
    for item_id, ts, step, hv, lv in rows:
        overlap = max(0.0, min(ts + step, now) - max(ts, start))
        if overlap <= 0:
            continue
        windows[ts] = overlap
        f = overlap / step
        hi[item_id] = hi.get(item_id, 0) + hv * f
        lo[item_id] = lo.get(item_id, 0) + lv * f
    covered = sum(windows.values())
    if not covered:
        return {}
    scale = 3600 / covered
    return {i: int(min(hi[i], lo[i]) * scale) for i in hi}


def run(p: ScreenParams, now: float | None = None) -> list[dict]:
    """Load everything the screener needs from the DB and run it."""
    now = now or time.time()
    with db.connect() as c:
        items = {
            r["id"]: dict(r)
            for r in c.execute("SELECT id, name, members, buy_limit FROM items")
        }
        latest = {r["item_id"]: dict(r) for r in c.execute("SELECT * FROM latest")}
        vol_1h = hourly_volume(
            c.execute(
                "SELECT item_id, ts, step, high_vol, low_vol FROM prices WHERE ts + step > ?",
                (int(now) - 3600,),
            ),
            now,
        )
        history: dict[int, list[tuple[int, int]]] = {}
        for r in c.execute(
            "SELECT item_id, avg_high, avg_low FROM prices "
            "WHERE ts >= ? AND avg_high IS NOT NULL AND avg_low IS NOT NULL",
            (int(now) - p.history_hours * 3600,),
        ):
            history.setdefault(r[0], []).append((r[1], r[2]))
    return [asdict(f) for f in screen(items, latest, vol_1h, history, p, now)]
