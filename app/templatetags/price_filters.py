from django import template
register = template.Library()

@register.filter
def vnd(value):
    try:
        return f"{int(value):,}".replace(",", ".")
    except (ValueError, TypeError):
        return str(value)
