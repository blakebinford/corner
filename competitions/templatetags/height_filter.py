from django import template

register = template.Library()

@register.filter(name='height')
def display_height(inches):
    if inches:
        feet = inches // 12
        inches = inches % 12
        return f"{feet}'{inches:02d}\""
    else:
        return ""  # Return an empty string if height is not available