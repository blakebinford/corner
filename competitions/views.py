import math
from datetime import date

from asgiref.sync import async_to_sync
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Prefetch
from django.forms import modelformset_factory
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy, reverse
from django.views import generic
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from channels.layers import get_channel_layer
from django.views.generic import FormView, CreateView, UpdateView

from accounts.models import AthleteProfile
from .models import Competition, EventOrder, AthleteCompetition, DivisionWeightClass, Result, CommentatorNote, Sponsor, \
    Event, EventBase, EventImplement, ZipCode
from .forms import CompetitionForm, EventForm, AthleteCompetitionForm, EventImplementFormSet, ResultForm, \
    SponsorLogoForm, create_event_implement_formset, EventImplementForm, CompetitionFilter

from collections import defaultdict
from chat.models import OrganizerChatMessage, OrganizerChatRoom


def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great-circle distance between two points on a sphere
    given their longitudes and latitudes.
    """
    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    # Haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
    c = 2 * math.asin(math.sqrt(a))

    # Radius of earth in miles
    r = 3956

    # Calculate the result
    return c * r

class CompetitionListView(generic.ListView):
    model = Competition
    template_name = 'competitions/competition_list.html'
    context_object_name = 'competitions'

    def get_queryset(self):
        queryset = super().get_queryset()

        # Apply filtering using the filterset
        self.filterset = CompetitionFilter(self.request.GET, queryset=queryset)

        # Return the filtered and sorted queryset
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        zip_code = self.request.GET.get('zip_code')

        if zip_code:
            try:
                user_zip_code = ZipCode.objects.get(zip_code=zip_code)
            except ZipCode.DoesNotExist:
                # Handle invalid zip code
                print(f"Invalid zip code provided: {zip_code}")  # Log the invalid zip code
                return context

            # Calculate distances and add distance attribute to each competition
            for competition in context['competitions']:
                try:
                    competition_zip_code = ZipCode.objects.get(zip_code=competition.zip_code)
                    distance = haversine_distance(
                        user_zip_code.latitude, user_zip_code.longitude,
                        competition_zip_code.latitude, competition_zip_code.longitude
                    )
                    competition.distance = distance
                except ZipCode.DoesNotExist:
                    # Handle missing zip code for competition
                    print(f"Missing zip code for competition: {competition.pk}")  # Log the missing zip code
                    competition.distance = float('inf')  # Set a high distance for sorting

            # Sort the competitions by distance
            context['competitions'] = sorted(context['competitions'], key=lambda x: x.distance)

        # Add filterset to context
        queryset = super().get_queryset()
        self.filterset = CompetitionFilter(self.request.GET, queryset=queryset)
        context['filterset'] = self.filterset

        return context

class CompetitionDetailView(generic.DetailView):
    model = Competition
    template_name = 'competitions/competition_detail.html'
    context_object_name = 'competition'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        competition = self.get_object()

        if self.request.user.is_authenticated:
            context['is_signed_up'] = AthleteCompetition.objects.filter(
                competition=competition,
                athlete__user=self.request.user  # Traverse AthleteProfile to User
            ).exists()

        # Fetch messages for the organizer chat room
        try:
            organizer_chat_room = OrganizerChatRoom.objects.get(competition=competition)
            organizer_messages = OrganizerChatMessage.objects.filter(room=organizer_chat_room).order_by('timestamp')
        except OrganizerChatRoom.DoesNotExist:
            organizer_messages = []

        context['organizer_messages'] = organizer_messages

        # Check if the current user is an organizer or registered athlete
        is_organizer_or_athlete = False
        if self.request.user.is_authenticated:
            is_organizer_or_athlete = (
                self.request.user == competition.organizer or
                competition.athletecompetition_set.filter(athlete__user=self.request.user).exists()
            )

        context['is_organizer_or_athlete'] = is_organizer_or_athlete
        # Fetch and organize event implement data
        division_tables = {}
        for event in competition.events.all():
            event_implements = event.implements.select_related('division_weight_class').all()
            for implement in event_implements:
                division = implement.division_weight_class.division.name
                weight_class = implement.division_weight_class.weight_class.name
                gender = implement.division_weight_class.gender

                if division not in division_tables:
                    division_tables[division] = []

                # Find or create a row for the weight class and gender
                row = next(
                    (r for r in division_tables[division]
                     if r['weight_class'] == weight_class and r['gender'] == gender),
                    None
                )
                if not row:
                    row = {'weight_class': weight_class, 'gender': gender}
                    division_tables[division].append(row)

                # Add the event weight
                row[event.name] = f"{implement.weight} {implement.weight_unit}"

        context['division_tables'] = division_tables
        context['events'] = competition.events.all()
        return context

class CompetitionScoreView(LoginRequiredMixin, generic.DetailView):  # New view for score management
    model = Competition
    template_name = 'competitions/competition_score.html'  # Create this template
    context_object_name = 'competition'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['ordered_events'] = EventOrder.objects.filter(
            competition=self.object
        ).select_related('event')
        # Prepare a list of division-weight class combinations
        div_weight_classes = []
        for division in self.object.allowed_divisions.all():
            for weight_class in self.object.allowed_weight_classes.all():
                div_weight_classes.append(f"{weight_class.name} - {division.name}")
        context['div_weight_classes'] = div_weight_classes
        return context

class CompetitionScorecardView(generic.DetailView):  # New view for scorecard
    model = Competition
    template_name = 'competitions/competition_scorecard.html'
    context_object_name = 'competition'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        competition = self.object  # Get the Competition object
        ordered_events = competition.eventorder_set.all().order_by('order')
        athlete_competitions = competition.athletecompetition_set.all().order_by('rank')

        # Group athletes by Gender, Division, and Weight Class
        grouped_athletes = {}
        for ac in athlete_competitions:
            group_key = (ac.athlete.gender, ac.division, ac.weight_class)
            if group_key not in grouped_athletes:
                grouped_athletes[group_key] = []
            grouped_athletes[group_key].append(ac)

        # Prepare a list of division-weight class combinations
        div_weight_classes = []
        for division in competition.allowed_divisions.all():
            for weight_class in competition.allowed_weight_classes.all():
                div_weight_classes.append(f"{weight_class.name} - {division.name}")

        # Fetch chat messages for this competition
        try:
            from chat.models import ChatRoom
            chat_room = ChatRoom.objects.get(competition=competition)
            from chat.models import ChatMessage
            messages = ChatMessage.objects.filter(room=chat_room).order_by('timestamp')
        except ChatRoom.DoesNotExist:
            messages = []

        context['ordered_events'] = ordered_events
        context['grouped_athletes'] = grouped_athletes
        context['div_weight_classes'] = div_weight_classes
        context['messages'] = messages
        return context

class CompetitionCreateView(LoginRequiredMixin, generic.CreateView):
    model = Competition
    form_class = CompetitionForm
    template_name = 'competitions/competition_form.html'
    success_url = reverse_lazy('competitions:competition_list')

    def form_valid(self, form):
        # Set the organizer of the competition to the currently logged-in user
        form.instance.organizer = self.request.user

        # Save the competition instance without committing to handle many-to-many fields
        competition = form.save(commit=False)

        # Save the main competition instance
        competition.save()

        # Handle many-to-many fields explicitly
        if form.cleaned_data.get('tags'):
            competition.tags.set(form.cleaned_data['tags'])
        if form.cleaned_data.get('allowed_divisions'):
            competition.allowed_divisions.set(form.cleaned_data['allowed_divisions'])
        if form.cleaned_data.get('allowed_weight_classes'):
            competition.allowed_weight_classes.set(form.cleaned_data['allowed_weight_classes'])

        # Save the competition again to ensure everything is persisted
        competition.save()

        # Redirect to the success URL
        return redirect(self.success_url)

    def form_invalid(self, form):
        # Debugging for form invalid cases
        print("Form is invalid")
        print(form.errors)  # Print errors to console for debugging
        return super().form_invalid(form)

    def save(self, commit=True):
        competition = super().save(commit=False)
        competition.scoring_system = 'strongman'  # Default scoring system
        if competition.comp_date > date.today():
            competition.status = 'upcoming'  # Default to upcoming if in the future
        elif competition.comp_date < date.today():
            competition.status = 'completed'

        # Handle capacity-based status
        signed_up_athletes_count = AthleteCompetition.objects.filter(
            competition=competition,
            signed_up=True
        ).count()
        if signed_up_athletes_count >= competition.capacity:
            competition.status = 'full'
        elif signed_up_athletes_count >= 0.9 * competition.capacity:
            competition.status = 'limited'

        if commit:
            competition.save()
            # Save many-to-many fields
            self.save_m2m()

        return competition

class SponsorLogoUploadView(LoginRequiredMixin, UserPassesTestMixin, FormView):
    form_class = SponsorLogoForm
    template_name = 'competitions/sponsor_logo_form.html'  # Create this template
    success_url = reverse_lazy('competitions:competition_list')

    def test_func(self):
        """
        Checks if the logged-in user is the organizer of the competition.
        """
        competition_pk = self.kwargs['competition_pk']
        competition = get_object_or_404(Competition, pk=competition_pk)
        return self.request.user == competition.organizer

    def form_valid(self, form):
        """
        Handles the form submission for uploading sponsor logos.
        """
        competition_pk = self.kwargs['competition_pk']
        competition = get_object_or_404(Competition, pk=competition_pk)

        if self.request.FILES.getlist('sponsor_logos'):
            for logo in self.request.FILES.getlist('sponsor_logos'):
                sponsor = Sponsor.objects.create(
                    name=logo.name,  # Or a more descriptive name
                    logo=logo
                )
                competition.sponsor_logos.add(sponsor)

        return super().form_valid(form)

class CompetitionUpdateView(LoginRequiredMixin, UserPassesTestMixin, generic.UpdateView):
    model = Competition
    form_class = CompetitionForm
    template_name = 'competitions/competition_form.html'
    success_url = reverse_lazy('competitions:competition_list')

    def test_func(self):
        competition = self.get_object()
        return self.request.user == competition.organizer

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_update'] = True
        return context

class CompetitionDeleteView(LoginRequiredMixin, UserPassesTestMixin, generic.DeleteView):
    model = Competition
    template_name = 'competitions/competition_confirm_delete.html'
    success_url = reverse_lazy('competitions:competition_list')

    def test_func(self):
        competition = self.get_object()
        return self.request.user == competition.organizer

class EventCreateView(CreateView):
    model = Event
    form_class = EventForm
    template_name = 'competitions/event_form.html'  # Create this template

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        competition_pk = self.kwargs['competition_pk']
        competition = get_object_or_404(Competition, pk=competition_pk)
        context['competition'] = competition
        context['is_update'] = False

        allowed_division_weight_classes = DivisionWeightClass.objects.filter(
            division__in=competition.allowed_divisions.all(),
            weight_class__in=competition.allowed_weight_classes.all()
        )

        # Create the formset using modelformset_factory
        EventImplementFormSet = modelformset_factory(
            EventImplement,
            form=EventImplementForm,
            extra=len(allowed_division_weight_classes)  # Set extra to the number of allowed DivisionWeightClass objects
        )

        # Get the allowed division_weight_class IDs for this competition
        allowed_division_weight_class_ids = DivisionWeightClass.objects.filter(
            division__in=competition.allowed_divisions.all(),
            weight_class__in=competition.allowed_weight_classes.all()
        ).values_list('id', flat=True)

        if self.request.POST:
            context['formset'] = EventImplementFormSet(
                self.request.POST,  # Update the existing formset with POST data
            )
        else:
            # Create initial data for the formset
            initial_data = [{'division_weight_class': dwc.id} for dwc in allowed_division_weight_classes]
            context['formset'] = EventImplementFormSet(
                queryset=EventImplement.objects.none(),  # Use an empty queryset to avoid extra forms
                initial=initial_data
            )

        context['event_bases'] = EventBase.objects.all().order_by('name')
        return context

    def save_event_implements(request, event):
        implements = []
        for key, value in request.POST.items():
            if key.startswith('implement_name_'):
                parts = key.split('_')
                weight_class_id = int(parts[2])
                implement_order = int(parts[3])

                implement_name = value
                weight = request.POST.get(f'weight_{weight_class_id}_{implement_order}')
                weight_unit = request.POST.get(f'weight_unit_{weight_class_id}_{implement_order}')

                implements.append(EventImplement(
                    event=event,
                    division_weight_class_id=weight_class_id,
                    implement_name=implement_name,
                    implement_order=implement_order,
                    weight=weight,
                    weight_unit=weight_unit
                ))
        EventImplement.objects.bulk_create(implements)

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']
        competition = context['competition']

        if formset.is_valid() and form.is_valid():  # Check if both form and formset are valid
            event = form.save()
            for form in formset:
                if form.cleaned_data:  # Check if the form has data
                    event_implement = form.save(commit=False)
                    event_implement.event = event  # Explicitly set the event
                    event_implement.save()

            formset.save()

            EventOrder.objects.create(competition=competition, event=event)
            return redirect('competitions:competition_detail', pk=competition.pk)
        else:

            return redirect('competitions:competition_detail', pk=competition.pk)

class EventUpdateView(LoginRequiredMixin, UserPassesTestMixin, generic.UpdateView):
    model = Event
    form_class = EventForm
    template_name = 'competitions/event_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        event = self.get_object()
        event_order = get_object_or_404(EventOrder, event=event)
        competition = event_order.competition
        context['competition'] = competition
        context['is_update'] = True

        queryset = EventImplement.objects.filter(event=event)
        print("Queryset for Formset:", queryset)

        allowed_division_weight_classes = DivisionWeightClass.objects.filter(
            division__in=competition.allowed_divisions.all(),
            weight_class__in=competition.allowed_weight_classes.all()
        )

        EventImplementFormSet = modelformset_factory(
            EventImplement,
            form=EventImplementForm,
            extra=0,
            can_delete=True  # Allow deletion of existing objects if needed
        )

        if self.request.POST:
            context['formset'] = EventImplementFormSet(self.request.POST, queryset=queryset)
        else:
            context['formset'] = EventImplementFormSet(queryset=queryset)

        return context

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']

        print("Formset Data:", self.request.POST)  # Print the POST data
        print("Formset Errors Before Validation:", formset.errors)  # Print errors before validation

        if formset.is_valid() and form.is_valid():
            event = form.save()
            for form in formset:
                if form.cleaned_data:
                    event_implement = form.save(commit=False)
                    event_implement.event = event
                    event_implement.save()

            formset.save()
            return redirect(self.get_success_url())
        else:
            print("Formset Errors:", formset.errors)
            return self.form_invalid(form)

    def get_success_url(self):
        event_order = get_object_or_404(EventOrder, event=self.object)
        return reverse_lazy('competitions:competition_detail', kwargs={'pk': event_order.competition.pk})

    def test_func(self):
        event = self.get_object()
        event_order = get_object_or_404(EventOrder, event=event)
        return self.request.user == event_order.competition.organizer

class EventDeleteView(LoginRequiredMixin, UserPassesTestMixin, generic.DeleteView):
    model = EventOrder
    template_name = 'competitions/event_confirm_delete.html'

    def get_success_url(self):
        return reverse_lazy('competitions:competition_detail', kwargs={'pk': self.object.competition.pk})

    def test_func(self):
        event = self.get_object()
        return self.request.user == event.competition.organizer

# views.py
class AthleteCompetitionCreateView(LoginRequiredMixin, generic.CreateView):
    model = AthleteCompetition
    form_class = AthleteCompetitionForm
    template_name = 'competitions/registration_form.html'

    def get_form(self, *args, **kwargs):
        form = super().get_form(*args, **kwargs)
        competition = get_object_or_404(Competition, pk=self.kwargs['competition_pk'])

        # Filter the fields based on the competition
        form.fields['weight_class'].queryset = competition.allowed_weight_classes.all()
        form.fields['division'].queryset = competition.allowed_divisions.all()
        return form

    def form_valid(self, form):
        form.instance.athlete = self.request.user.athlete_profile
        form.instance.competition = get_object_or_404(Competition, pk=self.kwargs['competition_pk'])

        # Check if competition is full
        competition = form.instance.competition
        if competition.athletecompetition_set.count() >= competition.capacity:
            return render(self.request, 'competitions/registration_full.html', {'competition': competition})

        # Save the AthleteCompetition object
        athlete_competition = form.save()

        return render(self.request, 'competitions/registration_success.html',
                      {'competition': competition, 'athlete_competition': athlete_competition})

class AthleteCompetitionUpdateView(LoginRequiredMixin, UserPassesTestMixin, generic.UpdateView):
    model = AthleteCompetition
    form_class = AthleteCompetitionForm
    template_name = 'competitions/athletecompetition_form.html'

    def get_success_url(self):
        return reverse_lazy('competitions:competition_detail', kwargs={'pk': self.object.competition.pk})

    def test_func(self):
        registration = self.get_object()
        return self.request.user == registration.athlete.user  # Check if the logged-in user is the athlete

class AthleteCompetitionDeleteView(LoginRequiredMixin, UserPassesTestMixin, generic.DeleteView):
    model = AthleteCompetition
    template_name = 'competitions/athletecompetition_confirm_delete.html'

    def get_success_url(self):
        return reverse_lazy('competitions:competition_detail', kwargs={'pk': self.object.competition.pk})

    def test_func(self):
        registration = self.get_object()
        return self.request.user == registration.athlete.user  # Check if the logged-in user is the athlete

def home(request):
    upcoming_competitions = Competition.objects.filter(status='upcoming')
    return render(request, 'home.html', {'upcoming_competitions': upcoming_competitions})

def event_create(request, competition_pk):  # This is the view to update
    competition = get_object_or_404(Competition, pk=competition_pk)
    if request.method == 'POST':
        event_form = EventForm(request.POST)
        formset = EventImplementFormSet(request.POST)  # Initialize the formset
        if event_form.is_valid() and formset.is_valid():
            event = event_form.save()
            formset.instance = event
            formset.save()
            EventOrder.objects.create(competition=competition, event=event)
            return redirect('competitions:competition_detail', competition_pk)
    else:
        event_form = EventForm()
        formset = EventImplementFormSet()  # Initialize the formset
    return render(request, 'competitions/event_form.html', {
        'event_form': event_form,
        'formset': formset,  # Pass the formset to the template
        'competition': competition
    })

@login_required
def update_score(request, competition_pk, athletecompetition_pk, eventorder_pk):
    athlete_competition = get_object_or_404(AthleteCompetition, pk=athletecompetition_pk)
    event_order = get_object_or_404(EventOrder, pk=eventorder_pk)
    competition = athlete_competition.competition

    # Get or create the Result object
    result, created = Result.objects.get_or_create(athlete_competition=athlete_competition, event_order=event_order)
    if request.method == 'POST':
        form = ResultForm(request.POST, instance=result)
        print(f"Request.POST: {request.POST}")
        try:
            if form.is_valid():
                print("Form is valid")
                result = form.save()
                print(f"Result saved: {result}")

                # Calculate points and rankings
                calculate_points_and_rankings(competition.pk, event_order.pk)  # Call scoring logic

                # Send score update message through WebSocket
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    f'competition_{competition_pk}',
                    {
                        'type': 'score_update',
                        'message': {
                            'type': 'score',
                            'athlete_id': athletecompetition_pk,
                            'event_id': eventorder_pk,
                            'value': result.value,
                            'points_earned': result.points_earned,
                            'total_points': athlete_competition.total_points,
                        }
                    }
                )
                print(
                    f"Sent score update: athlete_id={athletecompetition_pk}, event_id={eventorder_pk}, value={result.value}, points_earned={result.points_earned}, total_points={athlete_competition.total_points}",
                    flush=True)
                print(
                    f"Sent score update: athlete_id={athletecompetition_pk}, event_id={eventorder_pk}, value={result.value}, points_earned={result.points_earned}, total_points={athlete_competition.total_points}",
                    flush=True)
                print("WebSocket message sent")

                return redirect('competitions:competition_score', pk=competition_pk)  # Redirect after processing
            else:
                print(f"Form errors: {form.errors}")
        except Exception as e:
            print(f"Error during form processing: {e}", flush=True)
    else:
        form = ResultForm(instance=result)

    return render(request, 'competitions/score_update_form.html', {
        'form': form,
        'athlete_competition': athlete_competition,
        'event_order': event_order,
        'competition': competition
    })


def calculate_points_and_rankings(competition_pk, eventorder_pk):
    competition = Competition.objects.get(pk=competition_pk)
    event_order = EventOrder.objects.get(pk=eventorder_pk)
    results = Result.objects.filter(event_order=event_order)

    # 1. Group results by division, weight class, and gender
    grouped_results = defaultdict(list)
    for result in results:
        key = (result.athlete_competition.athlete.gender,
               result.athlete_competition.division,
               result.athlete_competition.weight_class)
        grouped_results[key].append(result)

    # 2. Sort and assign points within each group
    for key, group_results in grouped_results.items():
        # Sort results based on event type within the group
        event_type = event_order.event.weight_type
        if event_type == 'time':
            # For time-based events, extract time and sort in ascending order
            group_results.sort(key=lambda x: extract_time_from_result(x))  # Use helper function
        elif event_type in ('reps', 'distance', 'height', 'max'):
            # For other event types, sort by value in ascending order (assuming lower is better)
            group_results.sort(key=lambda x: int(x.value) if x.value and x.value.isdigit() else float('-inf'))
        else:
            # For unknown event types, sort by value in descending order (you might need to adjust this)
            group_results.sort(key=lambda x: -int(x.value) if x.value and x.value.isdigit() else float('-inf'))

        # Assign points within the group, handling ties
        num_competitors = len(group_results)
        current_points = -1  # Start from 0, so first place gets 1 point
        tied_results = []
        for i, result in enumerate(group_results):
            if tied_results and result.value == tied_results[-1].value:
                tied_results.append(result)  # Add to tied group
            else:
                # Process previous tied group (if any)
                if len(tied_results) > 1:
                    # Calculate average points for tied results
                    total_tied_points = sum(range(current_points + 1, current_points + len(tied_results) + 1))  # Add 1 to start from the correct point value
                    avg_points = total_tied_points / len(tied_results)
                    for tied_result in tied_results:
                        tied_result.points_earned = avg_points
                        tied_result.save()
                    current_points += len(tied_results)  # Increment points for the next position after the tie
                else:
                    # Not a tie, assign points normally
                    if tied_results:  # Assign points to the single result
                        tied_results[0].points_earned = current_points + 1  # Add 1 to get the correct point value
                        tied_results[0].save()
                    current_points += 1  # Increment for next position

                tied_results = [result]  # Start a new tied group

        # Handle any remaining tied results at the end of the group
        if len(tied_results) > 1:
            total_tied_points = sum(range(current_points + 1, current_points + len(tied_results) + 1))  # Add 1 to start from the correct point value
            avg_points = total_tied_points / len(tied_results)
            for tied_result in tied_results:
                tied_result.points_earned = avg_points
                tied_result.save()
            current_points += len(tied_results)  # Increment points after the tie
        else:
            if tied_results:
                tied_results[0].points_earned = current_points + 1  # Add 1 to get the correct point value
                tied_results[0].save()

    # After calculating points for the event, update overall rankings
    update_overall_rankings(competition)

def extract_time_from_result(result):
    """Helper function to extract time from result.value for sorting."""
    try:
        time_part = result.value.split('+')[1]  # Assuming format is 'implements+HH:MM:SS'
        hours, minutes, seconds = map(int, time_part.split(':'))
        return hours * 3600 + minutes * 60 + seconds  # Return total seconds for easier comparison
    except (IndexError, ValueError):
        return float('inf')  # Return infinity for invalid formats, placing them last


def update_overall_rankings(competition):
    # 1. Fetch all AthleteCompetition objects for the competition
    athlete_competitions = AthleteCompetition.objects.filter(
        competition=competition)

    # 2. Calculate total points for each athlete
    for athlete_competition in athlete_competitions:
        total_points = athlete_competition.results.aggregate(
            total_points=Sum('points_earned'))['total_points'] or 0
        athlete_competition.total_points = total_points
        athlete_competition.save()

    # 3. Group athletes by gender, division, and weight class
    grouped_athletes = defaultdict(list)
    for athlete_competition in athlete_competitions:
        key = (athlete_competition.athlete.gender,
               athlete_competition.division, athlete_competition.weight_class)
        grouped_athletes[key].append(athlete_competition)

    # 4. Sort and assign ranks within each group
    for key, group_athletes in grouped_athletes.items():
        # Sort athletes by total points (descending)
        group_athletes.sort(key=lambda x: -x.total_points)

        # Assign ranks within the group, handling ties
        current_rank = 1
        tied_athletes = []
        for athlete_competition in group_athletes:
            if tied_athletes and athlete_competition.total_points == tied_athletes[
                    -1].total_points:
                tied_athletes.append(athlete_competition)  # Add to tied group
            else:
                # Process previous tied group (if any)
                if len(tied_athletes) > 1:
                    for tied_athlete in tied_athletes:
                        tied_athlete.rank = current_rank  # Assign same rank to tied athletes
                        tied_athlete.save()
                    current_rank += len(tied_athletes)  # Increment rank based on number of tied athletes
                else:
                    # Not a tie, assign rank normally
                    if tied_athletes:
                        tied_athletes[
                            0].rank = current_rank  # Assign rank to the single athlete
                        tied_athletes[0].save()
                        current_rank += 1

                tied_athletes = [
                    athlete_competition
                ]  # Start a new tied group

        # Handle any remaining tied athletes at the end of the group
        if len(tied_athletes) > 1:
            for tied_athlete in tied_athletes:
                tied_athlete.rank = current_rank
                tied_athlete.save()
        else:
            if tied_athletes:
                tied_athletes[0].rank = current_rank
                tied_athletes[0].save()

def update_multiple_scores(request, competition_id):
    competition = get_object_or_404(Competition, pk=competition_id)

    if request.method == 'POST':
        for key, value in request.POST.items():
            if key.startswith('result_'):
                try:
                    athlete_competition_id, event_order_id = map(int, key.replace('result_', '').split('_'))
                    athlete_competition = AthleteCompetition.objects.get(pk=athlete_competition_id)
                    event_order = EventOrder.objects.get(pk=event_order_id)

                    # Update or create the Result object
                    result, created = Result.objects.get_or_create(
                        athlete_competition=athlete_competition,
                        event_order=event_order,
                        defaults={'value': value}
                    )
                    if not created:
                        result.value = value
                        result.save()

                except (ValueError, AthleteCompetition.DoesNotExist, EventOrder.DoesNotExist):
                    # Handle invalid input or missing objects
                    pass

        # Get all event order IDs for this competition
        event_order_ids = list(EventOrder.objects.filter(competition=competition).values_list('pk', flat=True))

        # Call your existing function for each event order
        for eventorder_pk in event_order_ids:
            calculate_points_and_rankings(competition.pk, eventorder_pk)

        return redirect('competitions:competition_score', pk=competition.pk)

    return HttpResponse("Invalid request method")

def athlete_profile(request, athlete_id):
    athlete = get_object_or_404(AthleteProfile, pk=athlete_id)
    competition_history = AthleteCompetition.objects.filter(athlete=athlete)
    print(athlete.__dict__)
    context = {
        'athlete': athlete,
        'competition_history': competition_history
    }
    return render(request, 'registration/athlete_profile.html', context)


from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from competitions.models import Competition
from accounts.models import AthleteProfile


@login_required
def commentator_comp_card(request, competition_id):
    competition = get_object_or_404(Competition, pk=competition_id)

    # Check if the user is the organizer of this competition
    if not competition.organizer == request.user:
        # Handle unauthorized access (e.g., redirect or 403 error)
        return render(request, 'unauthorized.html')  # Replace 'unauthorized.html' with your unauthorized template

    # Get the athletes registered for the competition, optimized with prefetch_related
    athletes = AthleteProfile.objects.filter(
        athletecompetition__competition=competition
    ).select_related(
        'user'
    ).prefetch_related(
        'athletecompetition_set__competition'
    )

    if request.method == 'POST':
        if 'delete_note' in request.POST:
            note_id = request.POST.get('note_id')
            note = get_object_or_404(CommentatorNote, pk=note_id, commentator=request.user)
            note.delete()
            # Optionally return a success message or redirect
            return JsonResponse({'status': 'success'})
        else:
            athlete_id = request.POST.get('athlete_id')
            note_text = request.POST.get('note_text')
            athlete = get_object_or_404(AthleteProfile, pk=athlete_id)

            CommentatorNote.objects.create(
                competition=competition,
                athlete=athlete,
                commentator=request.user,
                note=note_text
            )

        # Optionally return a success message or redirect
        return HttpResponseRedirect(reverse('competitions:commentator_comp_card', kwargs={'competition_id': competition.id}))

    context = {
        'competition': competition,
        'athletes': athletes,
    }
    return render(request, 'competitions/commentator_compcard.html', context)

from django.http import JsonResponse
from accounts.models import WeightClass

def get_weight_classes(request):
    federation_id = request.GET.get('federation_id')
    if not federation_id:
        return JsonResponse({'error': 'Federation ID is required'}, status=400)

    # Fetch weight classes for the selected federation
    weight_classes = WeightClass.objects.filter(federation_id=federation_id)
    weight_class_data = [{'id': wc.id, 'name': str(wc)} for wc in weight_classes]

    return JsonResponse({'weight_classes': weight_class_data})


