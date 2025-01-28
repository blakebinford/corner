# competitions/templatetags/competition_filters.py
from django import template

register = template.Library()

@register.filter
def dictfilter(items, key_value):
    key, value = key_value.split(":")
    return [item for item in items if getattr(item, key, None) == value]
