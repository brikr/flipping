from flipping.tax import ge_tax, post_tax_margin


def test_two_percent_rounded_down():
    assert ge_tax(1000) == 20
    assert ge_tax(1049) == 20


def test_under_50_is_free():
    assert ge_tax(49) == 0
    assert ge_tax(50) == 1


def test_capped_at_5m():
    assert ge_tax(2_000_000_000) == 5_000_000


def test_exempt_items():
    assert ge_tax(10_000_000, "Old school bond") == 0
    assert ge_tax(10_000_000, "Abyssal whip") == 200_000


def test_post_tax_margin():
    assert post_tax_margin(buy=100, sell=110) == 110 - 2 - 100
