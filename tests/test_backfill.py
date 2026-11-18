from flipping.collector import plan_backfill
from flipping.screener import hourly_volume

H = 3600
NOW_5M = 100 * H + 1500  # newest live 5m window starts at hh:25


def test_5m_mode_fills_every_missing_slot():
    horizon = NOW_5M - 2 * H
    plan = plan_backfill(NOW_5M, horizon, {NOW_5M}, step=300)
    assert len(plan) == 24
    assert plan[0] == (NOW_5M - 300, 300)
    assert plan[-1] == (horizon, 300)


def test_1h_mode_uses_hours_plus_5m_tail():
    horizon = NOW_5M - 24 * H
    latest_hour = 98 * H  # /1h lags: newest hour is 98:00-99:00
    plan = plan_backfill(NOW_5M, horizon, {NOW_5M}, step=H, latest_hour=latest_hour)
    tail = [p for p in plan if p[1] == 300]
    hours = [p for p in plan if p[1] == H]
    # 5m slots from 99:00 up to the live window (exclusive): 99:00..100:20 = 17
    assert len(tail) == 17 and tail[-1] == (99 * H, 300)
    assert hours[0] == (98 * H, H)
    assert all(t > horizon - H for t, _ in hours)
    assert len(plan) < 50  # vs 288 in 5m mode


def test_1h_mode_skips_hours_with_any_coverage():
    covered = {NOW_5M, 97 * H + 600}  # one 5m slot inside the 97:00 hour
    plan = plan_backfill(NOW_5M, NOW_5M - 5 * H, covered, step=H, latest_hour=98 * H)
    hours = [t for t, s in plan if s == H]
    assert 97 * H not in hours
    assert 98 * H in hours and 96 * H in hours


def test_hourly_volume_is_comparable_across_window_sizes():
    now = 10 * H
    five_min = [(1, now - H + i * 300, 300, 10, 20) for i in range(12)]  # 120 bought/h
    assert hourly_volume(five_min, now) == {1: 120}
    one_hour = [(1, now - H, H, 120, 300)]
    assert hourly_volume(one_hour, now) == {1: 120}
    # Only 30 minutes covered -> extrapolated to an hourly rate
    assert hourly_volume(five_min[6:], now) == {1: 120}
    # Hourly window half inside the lookback contributes half
    assert hourly_volume([(1, now - H - 1800, H, 120, 120)], now) == {1: 120}
