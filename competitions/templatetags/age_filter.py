from datetime import date

from django import template
from django.utils import timezone

register = template.Library()

@register.filter
def age(born):
    """
    Calculate the age based on the date of birth.
    Returns 'N/A' if date_of_birth is None.
    """
    if not born or not isinstance(born, date):
        return "N/A"
    today = date.today()
    birthday = born.replace(year=today.year)
    if birthday > today:
        age = today.year - born.year - 1
    else:
        age = today.year - born.year
    return str(age)