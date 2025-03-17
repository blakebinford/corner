
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from accounts.models import AthleteProfile
from competitions.models import Competition, EventBase, Result, CommentatorNote


@login_required
def commentator_comp_card(request, competition_id):
    competition = get_object_or_404(Competition, pk=competition_id)

    # Check if the user is the organizer of this competition
    if not competition.organizer == request.user:
        return render(request, 'unauthorized.html')  # Replace 'unauthorized.html' with your unauthorized template

    # Get all Event instances for the current competition
    events = competition.events.all()

    # Get all event bases related to the events of this competition
    current_event_bases = EventBase.objects.filter(event__in=events).distinct()

    # Get athletes registered for the competition
    athletes = AthleteProfile.objects.filter(
        athletecompetition__competition=competition
    ).select_related(
        'user'
    ).prefetch_related(
        'athletecompetition_set__competition',
        'commentatornote_set'
    )

    # Populate past performances with weight_type
    athletes_with_performance = []
    for athlete in athletes:
        past_performances = (
            Result.objects.filter(
                athlete_competition__athlete=athlete,
                event__in=events  # Corrected from event_order__event__in=events
            )
            .select_related(
                'event__event_base',
                'event',
                'athlete_competition__competition'
            )
            .order_by('event__event_base__name', '-athlete_competition__competition__comp_date')
        )

        # Add `weight_type` to the past performances
        for result in past_performances:
            result.weight_type = result.event.weight_type

        athlete.past_performances = past_performances
        athletes_with_performance.append(athlete)

    if request.method == 'POST':
        if 'delete_note' in request.POST:
            note_id = request.POST.get('note_id')
            note = get_object_or_404(CommentatorNote, pk=note_id, commentator=request.user)
            note.delete()
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
        return HttpResponseRedirect(reverse('competitions:commentator_comp_card', kwargs={'competition_id': competition.id}))

    context = {
        'competition': competition,
        'athletes': athletes_with_performance,
    }
    return render(request, 'competitions/commentator_compcard.html', context)