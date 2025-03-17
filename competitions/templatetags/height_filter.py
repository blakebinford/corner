from django import template
from django.utils.safestring import mark_safe

register = template.Library()

@register.filter
def height(height):
    """
    Convert height in inches to feet and inches format.
    Returns 'N/A' if height is None or not a valid number.
    """
    if height is None or not isinstance(height, (int, float)) or str(height).strip() == "N/A":
        return "N/A"
    try:
        inches = int(float(height))  # Convert to integer inches
        feet = inches // 12
        remaining_inches = inches % 12
        if remaining_inches == 0:
            return mark_safe(f"{feet}'")
        return mark_safe(f"{feet}'{remaining_inches}\"")
    except (ValueError, TypeError):
        return "N/A"