"""Grand Exchange tax rules (as of Nov 2026).

2% of the sell price per item, rounded down, capped at 5M per item.
Items selling below 50gp pay nothing, and a handful of items are exempt.
Check https://oldschool.runescape.wiki/w/Grand_Exchange if Jagex changes it.

Bonds are tax-exempt but carry their own cost: a bond bought on the GE arrives
untradeable, and converting it back costs 10% of the bond's GE guide price,
rounded to the nearest coin (https://oldschool.runescape.wiki/w/Old_school_bond).
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


BOND_NAME = "Old school bond"
BOND_CONVERSION_RATE = 0.10


def conversion_fee(price: int, item_name: str | None = None) -> int:
    """Coins to make a GE-bought bond tradeable again; 0 for every other item.

    The real fee uses the GE guide price, which we don't store. Callers pass
    the current sell price instead, which tracks recent trades closely.
    """
    if item_name != BOND_NAME:
        return 0
    return round(price * BOND_CONVERSION_RATE)


def flip_fees(sell: int, item_name: str | None = None) -> int:
    """Everything a flip loses per item besides the buy price."""
    return ge_tax(sell, item_name) + conversion_fee(sell, item_name)


def post_tax_margin(buy: int, sell: int, item_name: str | None = None) -> int:
    return sell - flip_fees(sell, item_name) - buy
