from django import template
from collections import defaultdict
import re
import logging

register = template.Library()
logger = logging.getLogger(__name__)

def extract_weight_value(weight_class):
    match = re.search(r'(\d+\.\d+|\d+)', str(weight_class))
    return float(match.group()) if match else 0

@register.filter
def group_by_division(formset):
    grouped_data = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    logger.debug(f"Processing formset with {len(formset)} forms")
    for form in formset:
        initial = form.initial or {}
        instance = form.instance

        logger.debug(f"Form initial: {initial}, Instance: {instance.__dict__}")

        weight_class_id = initial.get('weight_class')
        if weight_class_id:
            from competitions.models import WeightClass
            try:
                weight_class_instance = WeightClass.objects.get(id=weight_class_id)
            except WeightClass.DoesNotExist:
                logger.warning(f"WeightClass {weight_class_id} not found")
                continue
        elif instance.pk and hasattr(instance, 'weight_class') and instance.weight_class:
            weight_class_instance = instance.weight_class
        else:
            logger.debug("No weight_class found, skipping form")
            continue

        division_id = initial.get('division')
        if division_id:
            from competitions.models import Division
            try:
                division_instance = Division.objects.get(id=division_id)
            except Division.DoesNotExist:
                logger.warning(f"Division {division_id} not found")
                continue
        elif instance.pk and hasattr(instance, 'division') and instance.division:
            division_instance = instance.division
        else:
            logger.debug("No division found, skipping form")
            continue

        division = division_instance.name
        weight_class = (f"{weight_class_instance.weight_d}{weight_class_instance.name}" if weight_class_instance.weight_d == 'u' else
                        f"{weight_class_instance.name}{weight_class_instance.weight_d}" if weight_class_instance.weight_d == '+' else
                        f"{weight_class_instance.name}")
        gender = weight_class_instance.get_gender_display()
        implement_order = initial.get('implement_order', 1) if not instance.pk else instance.implement_order

        # Store weight_class_id for sorting
        entry = {
            'form': form,
            'weight_class_label': weight_class,
            'weight_class_id': weight_class_id,
            'weight_value': extract_weight_value(weight_class)
        }
        grouped_data[division][gender][weight_class_id].append((implement_order, entry))
        logger.debug(f"Added entry: Division={division}, Gender={gender}, WeightClass={weight_class}, Order={implement_order}")

    # Sort and restructure the grouped data
    sorted_grouped_data = defaultdict(lambda: defaultdict(list))
    for division, gender_groups in grouped_data.items():
        for gender, weight_class_groups in gender_groups.items():
            # Sort weight classes by weight_value
            sorted_weight_classes = sorted(
                weight_class_groups.items(),
                key=lambda x: min(entry[1]['weight_value'] for entry in x[1])
            )
            for weight_class_id, entries in sorted_weight_classes:
                # Sort entries by implement_order
                sorted_entries = sorted(entries, key=lambda x: x[0])
                for order, entry in sorted_entries:
                    sorted_grouped_data[division][gender].append(entry)
                    logger.debug(f"Sorted entry: Division={division}, Gender={gender}, WeightClassID={weight_class_id}, Order={order}")

    logger.debug("Final grouped data:")
    for division, gender_groups in sorted_grouped_data.items():
        for gender, entries in gender_groups.items():
            logger.debug(f"Division: {division}, Gender: {gender}, Entries: {len(entries)}")
            for entry in entries:
                logger.debug(f"  Entry: {entry}")

    return sorted_grouped_data.items()