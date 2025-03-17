from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.db.models import Sum

from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views import generic
from django.contrib.auth.mixins import LoginRequiredMixin
from channels.layers import get_channel_layer

from competitions.models import Competition, AthleteCompetition, Result, Event, WeightClass
from competitions.forms import  ResultForm
from asgiref.sync import async_to_sync

class CompetitionScoreView(LoginRequiredMixin, generic.DetailView):
    """
    View for managing competition scores.
    """
    model = Competition
    template_name = 'competitions/competition_score.html'
    context_object_name = 'competition'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        competition = self.get_object()

        # Retrieve all events in the competition
        context['ordered_events'] = competition.events.all()

        # Prepare a list of division-weight class combinations
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
        competition = self.object  # Get the Competition object
        ordered_events = competition.events.all().order_by('order')  # Corrected from eventorder_set
        athlete_competitions = competition.athletecompetition_set.all().order_by('rank')

        # Group athletes by Division, Gender, and Weight Class
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

        # Prepare a list of division-weight class combinations
        div_weight_classes = []
        for division in competition.allowed_divisions.all():
            for weight_class in WeightClass.objects.filter(division=division):  # Corrected to filter by division
                div_weight_classes.append(
                    f"{self.get_division_display(division)} - {self.get_weight_class_display(weight_class)}"
                )

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

    @staticmethod
    def get_weight_class_display(weight_class):
        """
        Returns the formatted weight class name based on `weight_d`.
        """
        if weight_class and weight_class.weight_d == 'u':
            return f"{weight_class.weight_d}{weight_class.name}"
        elif weight_class and weight_class.weight_d == '+':
            return f"{weight_class.name}{weight_class.weight_d}"
        return str(weight_class.name) if weight_class else "N/A"

    @staticmethod
    def get_division_display(division):
        """
        Returns the formatted division name with capitalization.
        """
        return division.name.capitalize() if division else "N/A"

@login_required
def update_score(request, competition_pk, athletecompetition_pk, event_pk):
    """
    Updates the score of an athlete for a specific event within a competition.
    """
    athlete_competition = get_object_or_404(AthleteCompetition, pk=athletecompetition_pk)
    event = get_object_or_404(Event, pk=event_pk)
    competition = athlete_competition.competition

    # Get or create the Result object
    result, created = Result.objects.get_or_create(athlete_competition=athlete_competition, event=event)

    if request.method == 'POST':
        form = ResultForm(request.POST, instance=result)
        print(f"Request.POST: {request.POST}")

        try:
            if form.is_valid():
                print("Form is valid")
                result = form.save()
                print(f"Result saved: {result}")

                # Calculate points and rankings
                calculate_points_and_rankings(competition.pk, event.pk)

                # Send score update message through WebSocket
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

                print(
                    f"Sent score update: athlete_id={athletecompetition_pk}, event_id={event_pk}, "
                    f"value={result.value}, points_earned={result.points_earned}, "
                    f"total_points={athlete_competition.total_points}",
                    flush=True
                )

                return redirect('competitions:competition_score', pk=competition_pk)

            else:
                print(f"Form errors: {form.errors}")

        except Exception as e:
            print(f"Error during form processing: {e}", flush=True)

    else:
        form = ResultForm(instance=result)

    return render(request, 'competitions/score_update_form.html', {
        'form': form,
        'athlete_competition': athlete_competition,
        'event': event,
        'competition': competition
    })

def calculate_points_and_rankings(competition_pk, event_pk):
    """
    Calculates points and rankings for a specific event within a competition.
    """
    competition = get_object_or_404(Competition, pk=competition_pk)
    event = get_object_or_404(Event, pk=event_pk)
    results = Result.objects.filter(event=event)

    # Group results by division, weight class, and gender
    grouped_results = defaultdict(list)
    for result in results:
        key = (
            result.athlete_competition.athlete.gender,
            result.athlete_competition.division,
            result.athlete_competition.weight_class,
        )
        grouped_results[key].append(result)

    # Sort and assign points and ranks within each group
    for key, group_results in grouped_results.items():
        event_type = event.weight_type  # Get scoring type

        # Sorting logic
        if event_type == 'time':
            # For time-based events, sort in ascending order
            group_results.sort(key=lambda x: extract_time_from_result(x))
        elif event_type in ('reps', 'distance', 'height', 'max'):
            # For other event types, sort by value in descending order (higher is better)
            group_results.sort(
                key=lambda x: float(x.value) if x.value else float('-inf'), reverse=True
            )
        else:
            # Default to descending order
            group_results.sort(
                key=lambda x: float(x.value) if x.value else float('-inf'), reverse=True
            )

        # Assign points and ranks within the group
        current_rank = 1
        tied_results = []

        for i, result in enumerate(group_results):
            # Handle zero or no score
            if not result.value or (result.value.isdigit() and int(result.value) == 0):
                result.points_earned = 0
                result.event_rank = len(group_results)  # Lowest rank
                result.save()
                continue

            # Handle ties
            if tied_results and result.value == tied_results[-1].value:
                tied_results.append(result)
            else:
                # Process previous tied group
                if len(tied_results) > 1:
                    for tied_result in tied_results:
                        tied_result.event_rank = current_rank
                        tied_result.save()
                    current_rank += len(tied_results)
                elif tied_results:
                    tied_results[0].event_rank = current_rank
                    tied_results[0].save()
                    current_rank += 1

                # Start a new tied group
                tied_results = [result]

        # Handle remaining tied results
        if len(tied_results) > 1:
            for tied_result in tied_results:
                tied_result.event_rank = current_rank
                tied_result.save()
        elif tied_results:
            tied_results[0].event_rank = current_rank
            tied_results[0].save()

    # Update overall rankings after calculating points
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
    """
    Updates multiple scores for a competition and recalculates rankings.
    """
    competition = get_object_or_404(Competition, pk=competition_id)

    if request.method == 'POST':
        event_ids_to_update = set()

        for key, value in request.POST.items():
            if key.startswith('result_'):
                try:
                    athlete_competition_id, event_id = map(int, key.replace('result_', '').split('_'))
                    athlete_competition = AthleteCompetition.objects.get(pk=athlete_competition_id)
                    event = Event.objects.get(pk=event_id)

                    # Track event IDs to update rankings later
                    event_ids_to_update.add(event.pk)

                    # Update or create the Result object
                    result, created = Result.objects.get_or_create(
                        athlete_competition=athlete_competition,
                        event=event,
                        defaults={'value': value}
                    )
                    if not created:
                        result.value = value
                        result.save()

                except (ValueError, AthleteCompetition.DoesNotExist, Event.DoesNotExist):
                    # Handle invalid input or missing objects
                    pass

        # Call ranking function for each updated event
        for event_pk in event_ids_to_update:
            calculate_points_and_rankings(competition.pk, event_pk)

        return redirect('competitions:competition_score', pk=competition.pk)

    return HttpResponse("Invalid request method", status=400)
