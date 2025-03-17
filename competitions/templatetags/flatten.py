from django import template
from itertools import chain

register = template.Library()

@register.filter
def flatten(list_of_lists):
    """Flatten a list of lists into a single list."""
    if list_of_lists:
        return list(chain.from_iterable(list_of_lists))
    return []