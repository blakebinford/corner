import json
from collections import defaultdict
import logging

from django.views import View
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.views import generic
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.forms import modelformset_factory

from competitions.models import Competition, AthleteCompetition, Result, Event, EventImplement, WeightClass, \
    Division, ImplementDefinition
from competitions.forms import EventImplementForm, EventCreationForm, ImplementDefinitionForm
from competitions.views.scoring_views import calculate_points_and_rankings

logger = logging.getLogger(__name__)

def create_event(request, competition_pk):
    """
    Handles the creation of an event linked to a competition.
    """
    competition = get_object_or_404(Competition, pk=competition_pk)

    if request.method == 'POST':
        form = EventCreationForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False)
            event.competition = competition
            max_order = competition.events.aggregate(Max('order'))['order__max']
            event.order = (max_order or 0) + 1
            event.save()
            form.save_m2m()
            messages.success(request, "Event created — now set up your implements.")
            return redirect('competitions:assign_implements', event_pk=event.pk)

        else:
            logger.error(f"Form validation failed: {form.errors}")
            messages.error(request, "Please correct the errors below.")
    else:
        form = EventCreationForm()

    return render(request, 'competitions/event_form.html', {
        'form': form,
        'competition': competition,
        'action_url': 'competitions:create_event',
        'action_kwargs': {'competition_pk': competition.pk},
    })


def assign_implements(request, event_pk):
    logger = logging.getLogger(__name__)

    event = get_object_or_404(Event, pk=event_pk)
    competition = get_object_or_404(Competition, events=event)
    divisions = competition.allowed_divisions.all()
    weight_classes = WeightClass.objects.filter(division__in=divisions).distinct()
    existing_implements = EventImplement.objects.filter(event=event)

    # Build a set of existing (division, weight_class, order) tuples
    existing_keys = {
        (ei.division_id, ei.weight_class_id, ei.implement_order)
        for ei in existing_implements
    }

    # Prepare initial_data for any missing combos
    initial_data = []
    num_impl = event.number_of_implements if event.has_multiple_implements else 1
    for division in divisions:
        for wc in weight_classes.filter(division=division):
            for order in range(1, num_impl + 1):
                key = (division.id, wc.id, order)
                if key not in existing_keys:
                    initial_data.append({
                        'event':           event.id,
                        'division':        division.id,
                        'weight_class':    wc.id,
                        'implement_order': order,
                        'weight':          0,
                        'weight_unit':     'lbs',
                    })

    EventImplementFormSet = modelformset_factory(
        EventImplement,
        form=EventImplementForm,
        extra=len(initial_data),
        can_delete=True,
        fields=('id', 'event', 'division', 'weight_class', 'implement_order', 'implement_name', 'weight', 'weight_unit')
    )

    if request.method == 'POST':
        formset = EventImplementFormSet(request.POST, queryset=existing_implements)
        logger.debug(f"POST data: {request.POST.dict()}")
        if formset.is_valid():
            # Remove old records and save all submitted ones
            existing_implements.delete()
            for form in formset:
                if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                    instance = form.save(commit=False)
                    instance.event = event
                    # Fallback to initial if not on form instance
                    instance.division_id = instance.division_id or form.initial.get('division')
                    instance.weight_class_id = instance.weight_class_id or form.initial.get('weight_class')
                    instance.implement_order = instance.implement_order or 1
                    if instance.division_id and instance.weight_class_id:
                        instance.save()
                    else:
                        logger.error("Cannot save implement: missing division or weight_class")
            messages.success(request, "Implements saved successfully!")
            return redirect('competitions:manage_competition', competition_pk=competition.pk)
        else:
            logger.debug(f"Formset errors: {formset.errors}")
            messages.error(request, "There was an error saving the implements. Please check the form.")
    else:
        formset = EventImplementFormSet(queryset=existing_implements, initial=initial_data)
        logger.debug(f"Formset created with {len(formset)} forms")

    # Group forms by division and gender for rendering
    grouped_forms = {}
    for form in formset:
        division_id = form.initial.get('division')
        weight_class_id = form.initial.get('weight_class')
        try:
            division = divisions.get(id=division_id) if division_id else None
            wc = weight_classes.get(id=weight_class_id) if weight_class_id else None
            if division and wc:
                gender = wc.gender
                grouped_forms.setdefault(division, {}).setdefault(gender, []).append({
                    'form': form,
                    'weight_class_label': wc.name,
                })
        except (Division.DoesNotExist, WeightClass.DoesNotExist):
            logger.warning(f"Invalid division_id {division_id} or weight_class_id {weight_class_id} in form initial data")

    logger.debug(f"Grouped forms: {grouped_forms.keys()}")

    return render(request, 'competitions/event_implements_form.html', {
        'formset':      formset,
        'event':        event,
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
        return reverse_lazy('competitions:competition_detail', kwargs={'pk': self.object.competition.pk})

    def test_func(self):
        """
        Ensure that only the competition organizer can delete events.
        """
        event = self.get_object()
        competition = event.competition
        return self.request.user == competition.organizer if competition else False

class EditEventOrderView(LoginRequiredMixin, UserPassesTestMixin, View):
    template_name = 'competitions/edit_event_order.html'

    def get(self, request, competition_pk):
        competition = get_object_or_404(Competition, pk=competition_pk)
        events = competition.events.all()
        return render(request, self.template_name, {'competition': competition, 'events': events})

    def post(self, request, competition_pk):
        order_list = request.POST.getlist('order[]')
        for index, event_id in enumerate(order_list):
            Event.objects.filter(pk=event_id, competition__pk=competition_pk).update(order=index)

        # Redirect to management dashboard after saving
        return redirect('competitions:manage_competition', competition_pk=competition_pk)

    def test_func(self):
        competition = get_object_or_404(Competition, pk=self.kwargs['competition_pk'])
        return self.request.user == competition.organizer

@login_required
def event_list(request, competition_pk):
    """
    View to list all events in a given competition.
    """
    competition = get_object_or_404(Competition, pk=competition_pk)
    event_orders = competition.events.all().order_by('order')  # Order by 'order' field
    return render(request, 'competitions/event_list.html', {
        'competition': competition,
        'event_orders': event_orders,
    })

@login_required
def event_scores(request, competition_pk, eventorder_pk):
    competition = get_object_or_404(Competition, pk=competition_pk)
    event = get_object_or_404(Event, pk=eventorder_pk)
    athlete_competitions = AthleteCompetition.objects.filter(competition=competition)

    grouped_athletes = defaultdict(lambda: defaultdict(list))
    for athlete_competition in athlete_competitions:
        gender = athlete_competition.athlete.gender
        division_name = athlete_competition.division.name if athlete_competition.division else "Unknown Division"
        weight_class = athlete_competition.weight_class
        result, created = Result.objects.get_or_create(
            athlete_competition=athlete_competition,
            event=event,
            defaults={'value': ''}  # Ensure a default value
        )
        grouped_athletes[gender][division_name].append({
            'athlete_competition': athlete_competition,
            'weight_class': {
                'name': weight_class.name if weight_class else "Unknown Weight Class",
                'weight_d': weight_class.weight_d if weight_class else None,
            },
            'result': result,
        })

    grouped_athletes = {
        gender: {
            division: sorted(athletes, key=lambda x: (x['weight_class']['weight_d'] or '', x['weight_class']['name']))
            for division, athletes in divisions.items()
        }
        for gender, divisions in sorted(grouped_athletes.items())
    }

    if request.method == 'POST':
        logger.debug(f"POST data: {request.POST}")
        for key, value in request.POST.items():
            if key.startswith('result_'):
                logger.debug(f"Processing key: {key}, value: {value}")
                try:
                    athlete_competition_id, event_id = map(int, key.replace('result_', '').split('_'))
                    result = Result.objects.get(
                        athlete_competition_id=athlete_competition_id,
                        event_id=event_id
                    )
                    if value.strip():  # Only update if non-empty
                        result.value = value.strip()
                        result.save()
                        logger.debug(f"Saved result: {result.value} for {result.athlete_competition.athlete.user.get_full_name()}")
                    else:
                        logger.warning(f"Empty value for {key}, not saved")
                except (ValueError, Result.DoesNotExist) as e:
                    logger.error(f"Error saving result for {key}: {e}")
                    continue

        calculate_points_and_rankings(competition.pk, event.pk)
        messages.success(request, "Scores updated successfully!")
        return redirect('competitions:event_scores', competition_pk=competition_pk, eventorder_pk=eventorder_pk)

    return render(request, 'competitions/event_score_update.html', {
        'competition': competition,
        'event': event,
        'grouped_athletes': grouped_athletes,
    })

class OrganizerOnlyMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.role == 'organizer'

class ImplementListView(LoginRequiredMixin, OrganizerOnlyMixin, ListView):
    model = ImplementDefinition
    template_name = 'competitions/implement_list.html'
    context_object_name = 'implements'

    def get_queryset(self):
        return ImplementDefinition.objects.filter(organizer=self.request.user)

class ImplementCreateView(LoginRequiredMixin, OrganizerOnlyMixin, CreateView):
    model = ImplementDefinition
    form_class = ImplementDefinitionForm
    template_name = 'competitions/partials/implement_form.html'

    def form_valid(self, form):
        self.object = form.save()
        if self.request.headers.get('HX-Request'):
            implements = ImplementDefinition.objects.filter(organizer=self.request.user)
            html = render_to_string('competitions/partials/implement_table.html', {'implements': implements})
            return JsonResponse({
                "html": html,
                "close_modal": True
            })

        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('competitions:organizer_implements')

class ImplementUpdateView(LoginRequiredMixin, OrganizerOnlyMixin, UpdateView):
    model = ImplementDefinition
    form_class = ImplementDefinitionForm
    template_name = 'competitions/partials/implement_form.html'

    def get_queryset(self):
        return ImplementDefinition.objects.filter(organizer=self.request.user)

    def form_valid(self, form):
        self.object = form.save()
        if self.request.headers.get('HX-Request'):
            implements = ImplementDefinition.objects.filter(organizer=self.request.user)
            html = render_to_string('competitions/partials/implement_table.html', {'implements': implements})
            return JsonResponse({
                "html": html,
                "close_modal": True
            })

        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('competitions:organizer_implements')

class ImplementDeleteView(LoginRequiredMixin, OrganizerOnlyMixin, DeleteView):
    model = ImplementDefinition
    template_name = 'competitions/partials/implement_confirm_delete.html'

    def get_queryset(self):
        return ImplementDefinition.objects.filter(organizer=self.request.user)

    def get_success_url(self):
        return reverse_lazy('competitions:organizer_implements')