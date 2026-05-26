from decimal import Decimal, InvalidOperation

from django import template


register = template.Library()


@register.filter
def vnd(value):
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return value

    formatted = f"{int(amount):,}".replace(",", ".")
    return f"{formatted}đ"
