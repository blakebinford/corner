from django import template

register = template.Library()

@register.filter(name='lookup')
def lookup(obj, key):
    try:
        value = getattr(obj, key)
        return value
    except AttributeError:
        return ''