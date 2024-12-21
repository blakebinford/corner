from django import template

from competitions.models import AthleteCompetition

register = template.Library()

@register.filter
def group_implements(implements):
    """Groups implements by name and returns a list of dictionaries."""
    grouped_implements = {}
    for implement in implements:
        name = implement.implement_name or "Implement"  # Use "Implement" if name is empty
        if name not in grouped_implements:
            grouped_implements[name] = []
        grouped_implements[name].append(implement)
    return [{'name': name, 'implements': implements} for name, implements in grouped_implements.items()]

@register.filter
def is_registered_for_competition(user, competition_pk):
    """
    Checks if a user is registered for a given competition.
    """
    if not user.is_authenticated:
        return False
    return AthleteCompetition.objects.filter(athlete=user.athlete, competition_id=competition_pk).exists()