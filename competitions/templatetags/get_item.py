from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """
    Get an item from a dictionary safely.
    Returns empty dict if dictionary is None or key is not found.
    """
    if dictionary is None:
        return {}

    if not isinstance(dictionary, dict):
        return {}

    # Try to convert key to int if it looks like a number
    try:
        if isinstance(key, str) and key.isdigit():
            key = int(key)
    except (ValueError, TypeError):
        pass

    return dictionary.get(key, {})