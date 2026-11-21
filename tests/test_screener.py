from flipping.screener import ScreenParams, screen

NOW = 1_800_000_000
ITEMS = {
    1: {"name": "Cheap bulk", "members": 0, "buy_limit": 10_000},
    2: {"name": "Pricey gear", "members": 1, "buy_limit": 8},
    3: {"name": "Dead item", "members": 1, "buy_limit": 100},
}


def latest(low, high, age=60):
    return {"low": low, "high": high, "low_time": NOW - age, "high_time": NOW - age}


LATEST = {1: latest(100, 110), 2: latest(1_000_000, 1_100_000), 3: latest(50, 500)}
VOL = {1: 5_000, 2: 20, 3: 1}


def test_ranks_by_profit_and_caps_qty_by_limit_and_volume():
    out = screen(ITEMS, LATEST, VOL, {}, ScreenParams(), NOW)
    assert [f.id for f in out] == [2, 1]  # item 3 filtered: volume < 10
    gear, bulk = out
    assert gear.margin == 1_100_000 - 22_000 - 1_000_000
    assert gear.qty == 8  # buy limit
    assert bulk.qty == 5_000  # 1h volume < limit
    assert bulk.profit == 8 * 5_000


def test_budget_limits_qty_and_excludes_unaffordable():
    out = screen(ITEMS, LATEST, VOL, {}, ScreenParams(budget=50_000), NOW)
    assert [f.id for f in out] == [1]
    assert out[0].qty == 500


def test_stale_prices_and_f2p_filter():
    stale = {**LATEST, 2: latest(1_000_000, 1_100_000, age=3600)}
    assert [f.id for f in screen(ITEMS, stale, VOL, {}, ScreenParams(), NOW)] == [1]
    assert [f.id for f in screen(ITEMS, LATEST, VOL, {}, ScreenParams(members=False), NOW)] == [1]


def test_stability_from_history():
    hist = {1: [(110, 100), (110, 100), (100, 100), (105, 100)]}  # (avg_high, avg_low)
    bulk = next(f for f in screen(ITEMS, LATEST, VOL, hist, ScreenParams(), NOW) if f.id == 1)
    assert bulk.windows == 4
    assert bulk.stability == 0.75  # 110->8, 110->8, 100->-2, 105->3
    assert bulk.median_margin == 5


def test_real_profit_uses_median_margin_and_floors_traps_at_zero():
    hist = {
        1: [(110, 100)] * 3,  # bulk: median post-tax margin 8
        2: [(1_000_000, 1_100_000)] * 3,  # gear: typically inverted -> negative median
    }
    out = {f.id: f for f in screen(ITEMS, LATEST, VOL, hist, ScreenParams(), NOW)}
    assert out[1].real_profit == 8 * 5_000
    assert out[2].median_margin < 0 and out[2].real_profit == 0
    # Default sort is real profit, so the trap drops below the steady flip.
    assert [f.id for f in screen(ITEMS, LATEST, VOL, hist, ScreenParams(), NOW)] == [1, 2]


def test_real_profit_is_none_without_history():
    out = screen(ITEMS, LATEST, VOL, {}, ScreenParams(), NOW)
    assert all(f.real_profit is None for f in out)


def test_favorites_bypass_filters_sort_first_and_skip_limit():
    # Item 3 fails the volume filter, but it's a favorite.
    out = screen(ITEMS, LATEST, VOL, {}, ScreenParams(limit=1), NOW, favorites={3})
    assert [f.id for f in out] == [3, 2]
    assert out[0].favorite and not out[1].favorite


def test_favorites_sort_among_themselves_by_the_sort_key():
    out = screen(ITEMS, LATEST, VOL, {}, ScreenParams(sort="margin"), NOW, favorites={1, 3})
    assert [f.id for f in out] == [3, 1, 2]  # margins: 3 -> 440, 1 -> 8, then non-fav 2
