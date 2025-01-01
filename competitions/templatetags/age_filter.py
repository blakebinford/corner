from datetime import date

from django import template
from django.utils import timezone

register = template.Library()

@register.filter(name='age')
def calculate_age(born):
    today = timezone.now().date()  # Use timezone.now() to get the current date in the correct time zone
    try:
        birthday = born.replace(year=today.year)
    except ValueError:
        birthday = born.replace(year=today.year, month=born.month + 1, day=1)
    if birthday > today:
        return today.year - born.year - 1
    else:
        return today.year - born.year