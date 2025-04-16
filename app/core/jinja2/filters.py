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


def price_format(price: Decimal | str, currency: str):
    if isinstance(price, str):
        try:
            price = Decimal(price)
        except InvalidOperation:
            return

    symbol = get_currency_symbol(currency)
    return f"{symbol}{price}"
