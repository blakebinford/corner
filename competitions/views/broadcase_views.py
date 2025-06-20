from math import prod
from django.shortcuts import get_object_or_404, render
from django.views import View
from competitions.models import (
    Competition,
    CompetitionRunOrder,
    Result,
    Event,
    WeightClass,
    AthleteCompetition
)

class CompetitionBroadcastView(View):
    template_name = 'competitions/competition_broadcast.html'

    def get(self, request, competition_pk):
        competition = get_object_or_404(Competition, pk=competition_pk)
        current_event = competition.current_event

        current_lifter = None
        on_deck = None
        current_lane = None
        event_weight = None
        mini_scorecard = []
        all_results = []
        ordered_events = competition.events.all().order_by('order')

        if current_event:
            # Get current lifter(s)
            current_ros = CompetitionRunOrder.objects.filter(
                competition=competition,
                event=current_event,
                status='current'
            ).select_related(
                'athlete_competition__athlete__user',
                'athlete_competition__division',
                'athlete_competition__weight_class'
            )

            if current_ros.exists():
                current_lifter = current_ros.first()
                current_lane = current_lifter.lane_number or 1

                # Get on-deck
                on_deck = CompetitionRunOrder.objects.filter(
                    competition=competition,
                    event=current_event,
                    status='pending',
                    lane_number=current_lane
                ).order_by('order').first()

                # Get event implement weight for current lifter's weight class
                wc = current_lifter.athlete_competition.weight_class
                if wc:
                    ew_qs = current_event.implements.filter(weight_class=wc)
                    if ew_qs.exists():
                        event_weight = ew_qs.first().weight

                # Mini scorecard (division + class only)
                ac = current_lifter.athlete_competition
                mini_scorecard = AthleteCompetition.objects.filter(
                    competition=competition,
                    division=ac.division,
                    weight_class=ac.weight_class
                ).select_related('athlete__user').prefetch_related('results').order_by('rank')

                all_results = Result.objects.filter(
                    event__competition=competition,
                    athlete_competition__in=mini_scorecard
                ).select_related('event')

        # Full grouped scorecard data
        grouped_athletes = {}
        all_athletes = AthleteCompetition.objects.filter(competition=competition).select_related(
            'athlete__user',
            'division',
            'weight_class'
        ).prefetch_related('results')

        for ac in all_athletes:
            group_key = (
                ac.division.name if ac.division else "Unassigned",
                getattr(ac.athlete, 'gender', "Unspecified"),
                f"{ac.weight_class.weight_d}{ac.weight_class.name}" if ac.weight_class else "Unassigned"
            )
            grouped_athletes.setdefault(group_key, []).append(ac)

        context = {
            'competition': competition,
            'current_event': current_event,
            'current_lifter': current_lifter,
            'on_deck': on_deck,
            'event_weight': event_weight,
            'mini_scorecard': mini_scorecard,
            'results': all_results,
            'ordered_events': ordered_events,
            'grouped_athletes': grouped_athletes,
            'even_col_span': len(ordered_events) * 3,
        }
        return render(request, self.template_name, context)
