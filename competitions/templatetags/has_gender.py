# templatetags/custom_filters.py
from django import template

register = template.Library()

@register.filter
def has_gender(rows, gender):
    return any(row['gender'] == gender for row in rows)
