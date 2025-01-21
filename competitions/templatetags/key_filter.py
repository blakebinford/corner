from django import template

register = template.Library()

@register.filter
def get_key_two(dictionary, key):
    try:
        keys = tuple(map(int, key.split(",")))  # Use a comma for splitting
        return dictionary.get(keys, 0)
    except Exception as e:
        return 0
