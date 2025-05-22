from collections import defaultdict
import logging

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views import generic
from django.contrib.auth.mixins import LoginRequiredMixin
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from competitions.models import Competition, AthleteCompetition, Result, Event, WeightClass
from competitions.forms import ResultForm

logger = logging.getLogger(__name__)


class CompetitionScoreView(LoginRequiredMixin, generic.DetailView):
    model = Competition
    template_name = 'competitions/competition_score.html'
    context_object_name = 'competition'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        competition = self.get_object()
        context['ordered_events'] = competition.events.all()
        div_weight_classes = []
        for division in competition.allowed_divisions.all():
            weight_classes = WeightClass.objects.filter(competition=competition)
            for weight_class in weight_classes:
                div_weight_classes.append(f"{weight_class.name} - {division.name}")
        context['div_weight_classes'] = div_weight_classes
        return context

class CompetitionScorecardView(generic.DetailView):
    model = Competition
    template_name = 'competitions/competition_scorecard.html'
    context_object_name = 'competition'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        competition = self.object
        ordered_events = competition.events.all().order_by('order')
        athlete_competitions = competition.athletecompetition_set.all().order_by('rank')
        grouped_athletes = {}
        for ac in athlete_competitions:
            group_key = (
                self.get_division_display(ac.division),
                ac.athlete.gender,
                self.get_weight_class_display(ac.weight_class),
            )
            if group_key not in grouped_athletes:
                grouped_athletes[group_key] = []
            grouped_athletes[group_key].append(ac)
        div_weight_classes = []
        for division in competition.allowed_divisions.all():
            for weight_class in WeightClass.objects.filter(division=division):
                div_weight_classes.append(
                    f"{self.get_division_display(division)} - {self.get_weight_class_display(weight_class)}"
                )
        try:
            from chat.models import ChatRoom, ChatMessage
            chat_room = ChatRoom.objects.get(competition=competition)
            messages = ChatMessage.objects.filter(room=chat_room).order_by('timestamp')
        except ChatRoom.DoesNotExist:
            messages = []
        context['ordered_events'] = ordered_events
        context['grouped_athletes'] = grouped_athletes
        context['div_weight_classes'] = div_weight_classes
        context['messages'] = messages
        return context

    @staticmethod
    def get_weight_class_display(weight_class):
        if weight_class and weight_class.weight_d == 'u':
            return f"{weight_class.weight_d}{weight_class.name}"
        elif weight_class and weight_class.weight_d == '+':
            return f"{weight_class.name}{weight_class.weight_d}"
        return str(weight_class.name) if weight_class else "N/A"

    @staticmethod
    def get_division_display(division):
        return division.name.capitalize() if division else "N/A"

@login_required
def update_score(request, competition_pk, athletecompetition_pk, event_pk):
    athlete_competition = get_object_or_404(AthleteCompetition, pk=athletecompetition_pk)
    event = get_object_or_404(Event, pk=event_pk)
    competition = athlete_competition.competition
    result, created = Result.objects.get_or_create(athlete_competition=athlete_competition, event=event)

    if request.method == 'POST':
        form = ResultForm(request.POST, instance=result)
        if form.is_valid():
            result = form.save()
            calculate_points_and_rankings(competition.pk, event.pk)
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f'competition_{competition_pk}',
                {
                    'type': 'score_update',
                    'message': {
                        'type': 'score',
                        'athlete_id': athletecompetition_pk,
                        'event_id': event_pk,
                        'value': result.value,
                        'points_earned': result.points_earned,
                        'total_points': athlete_competition.total_points,
                    }
                }
            )
            return redirect('competitions:competition_score', pk=competition_pk)
    else:
        form = ResultForm(instance=result)

    return render(request, 'competitions/score_update_form.html', {
        'form': form,
        'athlete_competition': athlete_competition,
        'event': event,
        'competition': competition
    })

def calculate_points_and_rankings(competition_pk, event_pk):
    competition = get_object_or_404(Competition, pk=competition_pk)
    event = get_object_or_404(Event, pk=event_pk)
    results = Result.objects.filter(event=event)

    grouped_results = defaultdict(list)
    for result in results:
        key = (
            result.athlete_competition.athlete.gender,
            result.athlete_competition.division,
            result.athlete_competition.weight_class,
        )
        grouped_results[key].append(result)

    for key, group_results in grouped_results.items():
        event_type = event.weight_type
        total_athletes = len(group_results)

        # Sorting logic
        if event_type == 'time':
            group_results.sort(key=lambda x: extract_time_from_result(x))
        elif event_type == 'reps':
            group_results.sort(key=lambda x: int(x.value) if x.value and x.value.isdigit() else 0, reverse=True)
        elif event_type in ('distance', 'height', 'max'):
            group_results.sort(key=lambda x: float(x.value) if x.value and x.value.strip() else float('-inf'), reverse=True)
        else:
            group_results.sort(key=lambda x: float(x.value) if x.value and x.value.strip() else float('-inf'), reverse=True)

        logger.debug(f"Group {key}: {[(r.athlete_competition.athlete.user.get_full_name(), r.value) for r in group_results]}")

        # Assign points and ranks
        current_rank = 1
        tied_results = []
        for i, result in enumerate(group_results):
            if not result.value or result.value.strip() == '' or (result.value.isdigit() and int(result.value) == 0):
                result.points_earned = 0
                result.event_rank = total_athletes
                result.save()
                logger.debug(f"No score: {result.athlete_competition.athlete.user.get_full_name()}, Rank: {total_athletes}, Points: 0")
                continue

            # Build tied group
            tied_results.append(result)

            # Check if this is the last result or next value differs
            if i == len(group_results) - 1 or result.value != group_results[i + 1].value:
                start_rank = current_rank
                end_rank = current_rank + len(tied_results) - 1
                if len(tied_results) > 1:
                    total_points = sum(total_athletes - r + 1 for r in range(start_rank, end_rank + 1))
                    avg_points = total_points / len(tied_results)
                    for tied_result in tied_results:
                        tied_result.event_rank = start_rank
                        tied_result.points_earned = avg_points
                        tied_result.save()
                        logger.debug(f"Tie: {tied_result.athlete_competition.athlete.user.get_full_name()}, Value: {tied_result.value}, Rank: {start_rank}, Points: {avg_points}")
                else:
                    tied_result = tied_results[0]
                    tied_result.event_rank = current_rank
                    tied_result.points_earned = total_athletes - current_rank + 1
                    tied_result.save()
                    logger.debug(f"Single: {tied_result.athlete_competition.athlete.user.get_full_name()}, Value: {tied_result.value}, Rank: {current_rank}, Points: {tied_result.points_earned}")
                current_rank = end_rank + 1
                tied_results = []

    update_overall_rankings(competition)

def extract_time_from_result(result):
    """Extract implements and time (MM:SS) from result.value for sorting."""
    try:
        if not result.value:
            return (0, float('inf'))  # No implements, infinite time
        parts = result.value.split('+')
        if len(parts) != 2:
            return (0, float('inf'))  # Invalid format
        implements = int(parts[0])  # Number of implements
        minutes, seconds = map(int, parts[1].split(':'))
        total_seconds = minutes * 60 + seconds
        return (-implements, total_seconds)  # Negative implements for descending order, then time
    except (ValueError, IndexError):
        return (0, float('inf'))  # Invalid format ranks last

def update_overall_rankings(competition):
    athlete_competitions = AthleteCompetition.objects.filter(competition=competition)
    for athlete_competition in athlete_competitions:
        total_points = athlete_competition.results.aggregate(total_points=Sum('points_earned'))['total_points'] or 0
        athlete_competition.total_points = total_points
        athlete_competition.save()

    grouped_athletes = defaultdict(list)
    for athlete_competition in athlete_competitions:
        key = (athlete_competition.athlete.gender, athlete_competition.division, athlete_competition.weight_class)
        grouped_athletes[key].append(athlete_competition)

    for key, group_athletes in grouped_athletes.items():
        group_athletes.sort(key=lambda x: -x.total_points)
        current_rank = 1
        tied_athletes = []
        for athlete_competition in group_athletes:
            if tied_athletes and athlete_competition.total_points == tied_athletes[-1].total_points:
                tied_athletes.append(athlete_competition)
            else:
                if len(tied_athletes) > 1:
                    for tied_athlete in tied_athletes:
                        tied_athlete.rank = current_rank
                        tied_athlete.save()
                    current_rank += len(tied_athletes)
                elif tied_athletes:
                    tied_athletes[0].rank = current_rank
                    tied_athletes[0].save()
                    current_rank += 1
                tied_athletes = [athlete_competition]
        if len(tied_athletes) > 1:
            for tied_athlete in tied_athletes:
                tied_athlete.rank = current_rank
                tied_athlete.save()
        elif tied_athletes:
            tied_athletes[0].rank = current_rank
            tied_athletes[0].save()

def update_multiple_scores(request, competition_id):
    competition = get_object_or_404(Competition, pk=competition_id)
    if request.method == 'POST':
        event_ids_to_update = set()
        for key, value in request.POST.items():
            if key.startswith('result_'):
                try:
                    athlete_competition_id, event_id = map(int, key.replace('result_', '').split('_'))
                    athlete_competition = AthleteCompetition.objects.get(pk=athlete_competition_id)
                    event = Event.objects.get(pk=event_id)
                    event_ids_to_update.add(event.pk)
                    result, created = Result.objects.get_or_create(
                        athlete_competition=athlete_competition,
                        event=event,
                        defaults={'value': value}
                    )
                    if not created:
                        result.value = value
                        result.save()
                except (ValueError, AthleteCompetition.DoesNotExist, Event.DoesNotExist):
                    pass
        for event_pk in event_ids_to_update:
            calculate_points_and_rankings(competition.pk, event_pk)
        return redirect('competitions:competition_score', pk=competition.pk)
    return HttpResponse("Invalid request method", status=400)