from django import template

register = template.Library()

@register.filter
def filter_implements(implements, div_weight_class):
  return [implement for implement in implements if implement.division_weight_class == div_weight_class]