from django import template
from django.utils import timezone
from datetime import timedelta

register = template.Library()

@register.filter(name='time_ago')
def time_ago(timestamp):
    """
    Calculates the time elapsed since the given timestamp and returns a human-readable string.
    """
    now = timezone.now()
    time_difference = now - timestamp

    if time_difference < timedelta(minutes=1):
        return "just now"
    elif time_difference < timedelta(hours=1):
        minutes = int(time_difference.total_seconds() / 60)
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
    elif time_difference < timedelta(days=1):
        hours = int(time_difference.total_seconds() / 3600)
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    elif time_difference < timedelta(days=7):
        days = time_difference.days
        return f"{days} day{'s' if days > 1 else ''} ago"
    elif time_difference < timedelta(days=30):
        weeks = int(time_difference.days / 7)
        return f"{weeks} week{'s' if weeks > 1 else ''} ago"
    elif time_difference < timedelta(days=365):
        months = int(time_difference.days / 30)
        return f"{months} month{'s' if months > 1 else ''} ago"
    else:
        years = int(time_difference.days / 365)
        return f"{years} year{'s' if years > 1 else ''} ago"