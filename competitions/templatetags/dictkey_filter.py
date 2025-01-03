from django import template

register = template.Library()

@register.filter
def dictkey(d, key):
    """Access a dictionary value by key in a Django template."""
    if isinstance(d, dict):
        return d.get(key)
    return None