from asgiref.sync import async_to_sync
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views import generic
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from channels.layers import get_channel_layer
from .models import Competition, EventOrder, AthleteCompetition, DivisionWeightClass, Result
from .forms import CompetitionForm, EventForm, AthleteCompetitionForm, EventImplementFormSet, ResultForm
from .filters import CompetitionFilter
from collections import defaultdict
from chat.models import OrganizerChatMessage, OrganizerChatRoom
class CompetitionListView(generic.ListView):
    model = Competition
    template_name = 'competitions/competition_list.html'
    context_object_name = 'competitions'
    def get_queryset(self):
        queryset = super().get_queryset()
        self.filterset = CompetitionFilter(self.request.GET, queryset=queryset)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filterset'] = self.filterset
        return context

class CompetitionDetailView(generic.DetailView):
    model = Competition
    template_name = 'competitions/competition_detail.html'
    context_object_name = 'competition'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        competition = self.get_object()

        context['ordered_events'] = EventOrder.objects.filter(
            competition=competition
        ).select_related('event').prefetch_related(
            'event__implements', 'event__implements__division_weight_class'
        ).order_by('order')

        context['div_weight_classes'] = DivisionWeightClass.objects.filter(
            eventimplement__event__competitions=competition
        ).distinct()

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
        form.instance.organizer = self.request.user
        return super().form_valid(form)

class CompetitionUpdateView(LoginRequiredMixin, UserPassesTestMixin, generic.UpdateView):
    model = Competition
    form_class = CompetitionForm
    template_name = 'competitions/competition_form.html'
    success_url = reverse_lazy('competitions:competition_list')

    def test_func(self):
        competition = self.get_object()
        return self.request.user == competition.organizer

class CompetitionDeleteView(LoginRequiredMixin, UserPassesTestMixin, generic.DeleteView):
    model = Competition
    template_name = 'competitions/competition_confirm_delete.html'
    success_url = reverse_lazy('competitions:competition_list')

    def test_func(self):
        competition = self.get_object()
        return self.request.user == competition.organizer

class EventCreateView(LoginRequiredMixin, generic.CreateView):
    model = EventOrder
    form_class = EventForm
    template_name = 'competitions/event_form.html'

    def get_success_url(self):
        return reverse_lazy('competitions:competition_detail', kwargs={'pk': self.kwargs['competition_pk']})

    def form_valid(self, form):
        competition = get_object_or_404(Competition, pk=self.kwargs['competition_pk'])
        event = form.cleaned_data['event']
        EventOrder.objects.create(competition=competition, event=event, order=form.cleaned_data['order'])
        return redirect(self.get_success_url())


class EventUpdateView(LoginRequiredMixin, UserPassesTestMixin, generic.UpdateView):
    model = EventOrder
    form_class = EventForm
    template_name = 'competitions/event_form.html'

    def get_success_url(self):
        return reverse_lazy('competitions:competition_detail', kwargs={'pk': self.object.competition.pk})

    def test_func(self):
        event = self.get_object()
        return self.request.user == event.competition.organizer

    def form_valid(self, form):
        return super().form_valid(form)


class EventDeleteView(LoginRequiredMixin, UserPassesTestMixin, generic.DeleteView):
    model = EventOrder
    template_name = 'competitions/event_confirm_delete.html'

    def get_success_url(self):
        return reverse_lazy('competitions:competition_detail', kwargs={'pk': self.object.competition.pk})

    def test_func(self):
        event = self.get_object()
        return self.request.user == event.competition.organizer

class AthleteCompetitionCreateView(LoginRequiredMixin, generic.CreateView):
    model = AthleteCompetition
    form_class = AthleteCompetitionForm
    template_name = 'competitions/registration_form.html'

    def get_success_url(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['competition'] = get_object_or_404(Competition, pk=self.kwargs['competition_pk'])
        return context

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
        key = (result.athlete_competition.athlete.gender, result.athlete_competition.division,
               result.athlete_competition.weight_class)
        grouped_results[key].append(result)

    # 2. Sort and assign points within each group
    for key, group_results in grouped_results.items():
        # Sort results based on event type within the group
        event_type = event_order.event.weight_type
        if event_type == 'time':
            # For time-based events, sort by time (ascending)
            group_results.sort(key=lambda x: x.time if x.time is not None else float('inf'))
        elif event_type in ('reps', 'distance', 'height', 'max'):
            # For other event types, sort by value (descending)
            group_results.sort(key=lambda x: -int(x.value) if x.value and x.value.isdigit() else float('-inf'))

        # Assign points within the group
        num_competitors = len(group_results)
        current_points = num_competitors
        previous_result = None
        for i, result in enumerate(group_results):
            if previous_result and result.value == previous_result.value:
                # Tie: assign points for the current position minus 0.5
                result.points_earned = current_points - 0.5
                previous_result.points_earned = current_points - 0.5  # Adjust previous result's points
            else:
                # Not a tie: assign points for the current position
                result.points_earned = current_points
                current_points -= 1
            previous_result = result
            result.save()

    # After calculating points for the event, update overall rankings
    update_overall_rankings(competition)

def update_overall_rankings(competition):
    # 1. Fetch all AthleteCompetition objects for the competition
    athlete_competitions = AthleteCompetition.objects.filter(competition=competition)

    # 2. Calculate total points for each athlete
    for athlete_competition in athlete_competitions:
        total_points = athlete_competition.results.aggregate(total_points=Sum('points_earned'))['total_points'] or 0
        athlete_competition.total_points = total_points
        athlete_competition.save()

    # 3. Group athletes by gender, division, and weight class
    grouped_athletes = defaultdict(list)
    for athlete_competition in athlete_competitions:
        key = (athlete_competition.athlete.gender, athlete_competition.division, athlete_competition.weight_class)
        grouped_athletes[key].append(athlete_competition)

    # 4. Sort and assign ranks within each group
    for key, group_athletes in grouped_athletes.items():
        # Sort athletes by total points (descending)
        group_athletes.sort(key=lambda x: -x.total_points)

        # Assign ranks within the group
        current_rank = 1
        previous_athlete = None
        for athlete_competition in group_athletes:
            if previous_athlete and athlete_competition.total_points == previous_athlete.total_points:
                # Tie: assign the same rank as the previous athlete
                athlete_competition.rank = current_rank
            else:
                # Not a tie: assign the current rank
                athlete_competition.rank = current_rank
                current_rank += 1
            previous_athlete = athlete_competition
            athlete_competition.save()

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