from django import template

register = template.Library()

@register.filter
def get_range(value):
    """
    Generate a range from 1 to the given value (inclusive).
    """
    try:
        value = int(value)
        return range(1, value + 1)
    except (ValueError, TypeError):
        return range(0)