from django.shortcuts import get_object_or_404, render
from django.views import View
from competitions.models import Competition, CompetitionRunOrder, Result, Event, WeightClass
from competitions.models import AthleteCompetition

class CompetitionBroadcastView(View):
    template_name = 'competitions/competition_broadcast.html'

    def get(self, request, competition_pk):
        competition = get_object_or_404(Competition, pk=competition_pk)
        current_event = competition.current_event

        # Initialize context data
        current_lifter = None
        on_deck = None
        current_lane = None
        event_weight = None
        mini_scorecard = []
        all_results = []

        if current_event:
            # Get all current lifters
            current_ros = CompetitionRunOrder.objects.filter(
                competition=competition,
                event=current_event,
                status='current'
            ).select_related('athlete_competition__athlete__user', 'athlete_competition__division', 'athlete_competition__weight_class')

            if current_ros.exists():
                current_lifter = current_ros.first()
                current_lane = current_lifter.lane_number or 1

                # On-deck is the next pending in the same lane
                pending = CompetitionRunOrder.objects.filter(
                    competition=competition,
                    event=current_event,
                    status='pending',
                    lane_number=current_lane
                ).order_by('order').first()
                on_deck = pending

                # Get event weight for lifter's division + class
                wc = current_lifter.athlete_competition.weight_class
                if wc:
                    event_weight_qs = current_event.implements.filter(weight_class=wc)
                    if event_weight_qs.exists():
                        event_weight = event_weight_qs.first().weight

                # Pull athletes from same division and class
                ac = current_lifter.athlete_competition
                mini_scorecard = AthleteCompetition.objects.filter(
                    competition=competition,
                    division=ac.division,
                    weight_class=ac.weight_class
                ).select_related('athlete__user').order_by('rank')

                all_results = Result.objects.filter(
                    event__competition=competition,
                    athlete_competition__in=mini_scorecard
                ).select_related('event')

        context = {
            'competition': competition,
            'current_event': current_event,
            'current_lifter': current_lifter,
            'on_deck': on_deck,
            'event_weight': event_weight,
            'mini_scorecard': mini_scorecard,
            'results': all_results,
        }
        return render(request, self.template_name, context)
