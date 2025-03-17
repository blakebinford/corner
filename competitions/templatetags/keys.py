from django import template


register = template.Library()

@register.filter
def keys(dictionary):
    """Return the keys of a dictionary."""
    if dictionary:
        return dictionary.keys()
    return []