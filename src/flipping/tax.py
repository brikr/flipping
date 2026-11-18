"""Grand Exchange tax rules (as of Nov 2026).

2% of the sell price per item, rounded down, capped at 5M per item.
Items selling below 50gp pay nothing, and a handful of items are exempt.
Check https://oldschool.runescape.wiki/w/Grand_Exchange if Jagex changes it.
"""

TAX_RATE = 0.02
TAX_CAP = 5_000_000
TAX_FREE_BELOW = 50

# Bonds + the new-player tools exempted in the original tax update.
EXEMPT_NAMES = frozenset(
    {
        "Old school bond",
        "Chisel",
        "Seed dibber",
        "Gardening trowel",
        "Glassblowing pipe",
        "Hammer",
        "Needle",
        "Saw",
        "Secateurs",
        "Shears",
        "Spade",
        "Watering can",
    }
)


def ge_tax(sell_price: int, item_name: str | None = None) -> int:
    """Tax paid per item when one unit sells at `sell_price`."""
    if sell_price < TAX_FREE_BELOW or item_name in EXEMPT_NAMES:
        return 0
    return min(int(sell_price * TAX_RATE), TAX_CAP)


def post_tax_margin(buy: int, sell: int, item_name: str | None = None) -> int:
    return sell - ge_tax(sell, item_name) - buy
