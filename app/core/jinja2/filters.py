from datetime import datetime
from decimal import Decimal, InvalidOperation
from django.utils.dateparse import parse_datetime

from babel.numbers import get_currency_symbol


__all__ = [
    "strftime",
    "price_format",
]


def strftime(dt: datetime | str | None, format: str):
    if not dt:
        return dt

    if isinstance(dt, str):
        dt = parse_datetime(dt)
    return dt.strftime(format)


def price_format(amount: Decimal | str, currency: str):
    if isinstance(amount, str):
        try:
            amount = Decimal(amount)
        except InvalidOperation:
            return

    symbol = get_currency_symbol(currency)
    return f"{symbol}{amount:.2f}"
