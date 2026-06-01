from decimal import Decimal, ROUND_HALF_UP


def to_decimal(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def format_currency(amount: Decimal, symbol: str = "$") -> str:
    rounded = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sign = "-" if rounded < 0 else ""
    abs_val = abs(rounded)
    formatted = f"{abs_val:,.2f}"
    return f"{sign}{symbol}{formatted}"


def sum_amounts(amounts) -> Decimal:
    return sum((to_decimal(a) for a in amounts), Decimal("0.00"))
