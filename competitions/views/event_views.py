from collections import defaultdict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views import generic
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.forms import modelformset_factory

from competitions.models import Competition, AthleteCompetition, Result, Event, EventImplement, WeightClass, Division
from competitions.forms import EventImplementForm, EventCreationForm
from competitions.views.scoring_views import calculate_points_and_rankings


def create_event(request, competition_pk):
    """
    Handles the creation of an event linked to a competition.
    """
    competition = get_object_or_404(Competition, pk=competition_pk)

    if request.method == 'POST':
        form = EventCreationForm(request.POST)

        if form.is_valid():
            # Save the event instance without committing
            event = form.save(commit=False)

            # ✅ Explicitly assign the competition before saving
            event.competition = competition

            # Determine the next event order within the competition
            max_order = competition.events.aggregate(Max('order'))['order__max']
            event.order = (max_order or 0) + 1  # Assign next order number

            # ✅ Save the event after setting competition
            event.save()

            # Save many-to-many relationships
            form.save_m2m()

            # Redirect to implement assignment if the event has multiple implements
            return redirect('competitions:assign_implements', event_pk=event.pk)
    else:
        form = EventCreationForm()

    return render(request, 'competitions/event_form.html', {
        'form': form,
        'competition': competition,
        'action_url': 'competitions:create_event',
        'action_kwargs': {'competition_pk': competition.pk},
    })


@login_required
def assign_implements(request, event_pk):
    import logging
    logger = logging.getLogger(__name__)

    event = get_object_or_404(Event, pk=event_pk)
    competition = get_object_or_404(Competition, events=event)
    divisions = competition.allowed_divisions.all()
    weight_classes = WeightClass.objects.filter(division__competition=competition)
    existing_implements = EventImplement.objects.filter(event=event)
    initial_data = []

    logger.debug(f"Event: {event.pk}, Existing implements: {existing_implements.count()}")

    # Generate initial data
    if not existing_implements.exists():
        for division in divisions:
            division_weight_classes = weight_classes.filter(division=division)
            for weight_class in division_weight_classes:
                if not event.has_multiple_implements:
                    initial_data.append({
                        'event': event.id,
                        'division': division.id,
                        'weight_class': weight_class.id,
                        'implement_order': 1,  # Always set to 1
                        'weight': 0,
                        'weight_unit': 'lbs',
                    })
                else:
                    # For multiple implements, create entries for each implement
                    num_implements = event.number_of_implements
                    for order in range(1, num_implements + 1):
                        initial_data.append({
                            'event': event.id,
                            'division': division.id,
                            'weight_class': weight_class.id,
                            'implement_order': order,
                            'weight': 0,
                            'weight_unit': 'lbs',
                        })
        logger.debug(f"Initial data created: {len(initial_data)} entries")

    EventImplementFormSet = modelformset_factory(
        EventImplement,
        form=EventImplementForm,
        extra=len(initial_data) if not existing_implements.exists() else 0,
        can_delete=True,
        fields=(
        'id', 'event', 'division', 'weight_class', 'implement_order', 'implement_name', 'weight', 'weight_unit')
    )

    if request.method == 'POST':
        formset = EventImplementFormSet(request.POST, queryset=existing_implements)
        logger.debug(f"POST data: {request.POST.dict()}")
        if formset.is_valid():
            existing_implements.delete()
            for form in formset:
                if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                    instance = form.save(commit=False)
                    instance.event = event

                    # Make sure division and weight_class are properly set
                    if not instance.division_id and 'division' in form.initial:
                        instance.division_id = form.initial['division']

                    if not instance.weight_class_id and 'weight_class' in form.initial:
                        instance.weight_class_id = form.initial['weight_class']

                    if not instance.implement_order:
                        instance.implement_order = 1

                    if instance.division_id and instance.weight_class_id:
                        instance.save()
                    else:
                        logger.error(f"Cannot save implement: missing division or weight_class")

            messages.success(request, "Implements saved successfully!")
            return redirect('competitions:manage_competition', competition_pk=competition.pk)
        else:
            logger.debug(f"Formset errors: {formset.errors}")
            messages.error(request, "There was an error saving the implements. Please check the form.")
    else:
        formset = EventImplementFormSet(queryset=existing_implements, initial=initial_data)
        logger.debug(f"Formset created with {len(formset)} forms")

    # Manually group forms by division and gender
    grouped_forms = {}
    for form in formset:
        division_id = form.initial.get('division')
        weight_class_id = form.initial.get('weight_class')
        try:
            division = divisions.get(id=division_id) if division_id else None
            weight_class = weight_classes.get(id=weight_class_id) if weight_class_id else None
            if division and weight_class:
                gender = weight_class.gender
                if division not in grouped_forms:
                    grouped_forms[division] = {}
                if gender not in grouped_forms[division]:
                    grouped_forms[division][gender] = []
                grouped_forms[division][gender].append({
                    'form': form,
                    'weight_class_label': weight_class.name,
                })
        except (Division.DoesNotExist, WeightClass.DoesNotExist):
            logger.warning(f"Invalid division_id {division_id} or weight_class_id {weight_class_id} in form initial data")

    logger.debug(f"Grouped forms: {grouped_forms.keys()}")

    return render(request, 'competitions/event_implements_form.html', {
        'formset': formset,
        'event': event,
        'grouped_forms': grouped_forms,
    })

def update_event(request, event_pk):
    """
    Handles the update of an existing event.
    """
    event = get_object_or_404(Event, pk=event_pk)
    competition = event.competition

    if request.method == 'POST':
        form = EventCreationForm(request.POST, instance=event)  # Pass the instance to the form
        if form.is_valid():
            form.save()
            return redirect('competitions:assign_implements', event_pk=event.pk)
    else:
        form = EventCreationForm(instance=event)

    return render(request, 'competitions/event_form.html', {
        'form': form,
        'competition': competition,
        'event': event,
        'action_url': 'competitions:update_event',  # Dynamically set the form action
        'action_kwargs': {'event_pk': event.pk},  # Pass event_pk for editing
    })

class EventDeleteView(LoginRequiredMixin, UserPassesTestMixin, generic.DeleteView):
    """
    View for deleting an event from a competition.
    """
    model = Event
    template_name = 'competitions/event_confirm_delete.html'

    def get_success_url(self):
        """
        Redirect to the competition detail page after deleting the event.
        """
        return reverse_lazy('competitions:competition_detail', kwargs={'pk': self.object.competitions.first().pk})

    def test_func(self):
        """
        Ensure that only the competition organizer can delete events.
        """
        event = self.get_object()
        competition = event.competitions.first()  # ✅ Retrieve related competition
        return self.request.user == competition.organizer if competition else False

@login_required
def event_list(request, competition_pk):
    """
    View to list all events in a given competition.
    """
    competition = get_object_or_404(Competition, pk=competition_pk)

    return render(request, 'competitions/event_list.html', {
        'competition': competition,
        'events': competition.events.all(),  # Fetches events directly
    })

@login_required
def event_scores(request, competition_pk, event_pk):
    """
    View to manage event scores for a specific competition event.
    """
    competition = get_object_or_404(Competition, pk=competition_pk)
    event = get_object_or_404(Event, pk=event_pk)
    athlete_competitions = AthleteCompetition.objects.filter(competition=competition)

    # Group athletes by gender, then by division, then by weight class
    grouped_athletes = defaultdict(lambda: defaultdict(list))
    for athlete_competition in athlete_competitions:
        gender = athlete_competition.athlete.gender
        division_name = athlete_competition.division.name if athlete_competition.division else "Unknown Division"
        weight_class = athlete_competition.weight_class

        # Retrieve or create a result for each athlete
        result, created = Result.objects.get_or_create(
            athlete_competition=athlete_competition,
            event=event
        )

        grouped_athletes[gender][division_name].append({
            'athlete_competition': athlete_competition,
            'weight_class': {
                'name': weight_class.name if weight_class else "Unknown Weight Class",
                'weight_d': weight_class.weight_d if weight_class else None,
            },
            'result': result,
        })

    # Sort grouped athletes
    grouped_athletes = {
        gender: {
            division: sorted(athletes, key=lambda x: (x['weight_class']['weight_d'], x['weight_class']['name']))
            for division, athletes in divisions.items()
        }
        for gender, divisions in sorted(grouped_athletes.items())
    }

    if request.method == 'POST':
        for key, value in request.POST.items():
            if key.startswith('result_'):
                try:
                    athlete_competition_id, event_id = map(int, key.replace('result_', '').split('_'))
                    result = Result.objects.get(
                        athlete_competition_id=athlete_competition_id,
                        event_id=event_id
                    )
                    result.value = value
                    result.save()
                except (ValueError, Result.DoesNotExist):
                    pass

        # Recalculate points and rankings after score update
        calculate_points_and_rankings(competition.pk, event.pk)

        # Add a success message
        messages.success(request, "Scores updated successfully!")
        return redirect('competitions:event_scores', competition_pk=competition_pk, event_pk=event_pk)

    return render(request, 'competitions/event_score_update.html', {
        'competition': competition,
        'event': event,
        'grouped_athletes': grouped_athletes,
    })
