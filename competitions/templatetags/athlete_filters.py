from django import template
from collections import defaultdict

register = template.Library()


@register.filter
def group_by_gender_division_weight_class(athlete_competitions):
    grouped_data = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for ac in athlete_competitions:
        gender = ac.athlete.gender
        division = str(ac.division)
        weight_class = str(ac.weight_class)
        grouped_data[gender][division][weight_class].append(ac)

    # Convert the defaultdict to a regular dict and return it
    return dict(grouped_data)