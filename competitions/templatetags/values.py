from django import template


register = template.Library()

@register.filter
def values(dictionary):
    """Return the values of a dictionary."""
    if dictionary:
        return dictionary.values()
    return []
