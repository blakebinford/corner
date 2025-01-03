from django import template

register = template.Library()

@register.filter
def format_weight_class(weight_class):
    """
    Format the weight class number based on the weight_d field.
    """
    if hasattr(weight_class, 'weight_d'):  # Check if weight_d exists
        if weight_class.weight_d == 'u':
            return f"u{weight_class.name}"
        elif weight_class.weight_d == '+':
            return f"{weight_class.name}+"
    return str(weight_class)