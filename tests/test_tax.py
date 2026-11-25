from flipping.tax import conversion_fee, ge_tax, post_tax_margin


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


def test_bond_conversion_fee():
    # Wiki example: guide price 10,588,866 -> fee 1,058,887.
    assert conversion_fee(10_588_866, "Old school bond") == 1_058_887
    assert conversion_fee(10_588_866, "Abyssal whip") == 0


def test_bond_margin_includes_conversion_fee_but_no_tax():
    assert post_tax_margin(buy=10_000_000, sell=10_500_000, item_name="Old school bond") == (
        10_500_000 - 1_050_000 - 10_000_000
    )
