import csv
from collections import defaultdict
from itertools import groupby

from django.db import transaction
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.contrib import messages
from django.core.mail import send_mass_mail
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views import View, generic
from django.views.generic import TemplateView, CreateView

from competitions.models import Competition, AthleteCompetition, Division, WeightClass, AthleteEventNote, \
    LaneAssignment, CompetitionRunOrder, Event, Result
from competitions.forms import EditWeightClassesForm, CustomWeightClassForm, CustomDivisionForm, \
    CombineWeightClassesForm
from competitions.views import calculate_points_and_rankings


class OrganizerCompetitionsView(TemplateView):
    template_name = "competitions/organizer_competitions.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        organizer = self.request.user

        # Get competitions organized by the user
        all_competitions = Competition.objects.filter(organizer=organizer)
        upcoming_competitions = all_competitions.filter(comp_date__gte=timezone.now(), status__in=['upcoming', 'limited', 'full']).order_by('comp_date')
        completed_competitions = all_competitions.filter(status='completed').order_by('-comp_date')

        # Prepare sections
        sections = [
            {"title": "Upcoming Competitions", "competitions": upcoming_competitions, "badge_class": "bg-success"},
            {"title": "Completed Competitions", "competitions": completed_competitions, "badge_class": "bg-secondary"},
            {"title": "All Competitions", "competitions": all_competitions, "badge_class": "bg-primary"},
        ]

        context.update({
            "sections": sections,
        })
        return context

def toggle_email_notifications(request, competition_pk):
    competition = get_object_or_404(Competition, pk=competition_pk)

    if competition.organizer != request.user:
        messages.error(request, "You are not authorized to perform this action.")
        return redirect('competitions:manage_competition', competition_pk)

    competition.email_notifications = not competition.email_notifications
    competition.save()

    if competition.email_notifications:
        messages.success(request, "Email notifications enabled. You will now receive an email every time an athlete signs up.")
    else:
        messages.success(request, "Email notifications disabled. You will no longer receive sign-up emails.")

    return redirect('competitions:manage_competition', competition_pk)

def download_athlete_table(request, competition_pk):
    competition = Competition.objects.get(pk=competition_pk)
    athletes = AthleteCompetition.objects.filter(competition=competition).select_related('athlete__user', 'weight_class', 'division', 'tshirt_size')

    # Create the HTTP response object with CSV content
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{competition.name}_athletes.csv"'

    writer = csv.writer(response)
    # Write the header row
    writer.writerow([
        'Name', 'Email', 'Gender', 'Division', 'Weight Class',
        'T-shirt Size', 'Registration Date'
    ])

    # Write athlete rows
    for athlete_competition in athletes:
        athlete = athlete_competition.athlete
        writer.writerow([
            athlete.user.get_full_name(),
            athlete.user.email,
            athlete.gender,
            athlete_competition.division.name if athlete_competition.division else 'N/A',
            f"{athlete_competition.weight_class.weight_d}{athlete_competition.weight_class.name}" if athlete_competition.weight_class else 'N/A',
            athlete_competition.tshirt_size.size if athlete_competition.tshirt_size else 'N/A',
            athlete_competition.registration_date.strftime('%B %d, %Y'),
        ])

    return response

def send_email_to_athletes(request, competition_pk):
    competition = get_object_or_404(Competition, pk=competition_pk)

    # Check if the user is the organizer
    if request.user != competition.organizer:
        messages.error(request, "You are not authorized to send emails for this competition.")
        return HttpResponseRedirect(
            reverse('competitions:manage_competition', kwargs={'competition_pk': competition_pk}))

    if request.method == 'POST':
        subject = request.POST.get('subject')
        message = request.POST.get('message')

        # Fetch emails of all registered athletes
        athlete_emails = competition.athletecompetition_set.values_list('athlete__user__email', flat=True)

        # Create a list of tuples for send_mass_mail
        email_data = [
            (subject, message, 'no-reply@Atlascompetition.com', [email]) for email in athlete_emails
        ]

        # Send the emails
        send_mass_mail(email_data, fail_silently=False)
        messages.success(request, "Emails sent successfully to all registered athletes.")
        return HttpResponseRedirect(
            reverse('competitions:manage_competition', kwargs={'competition_pk': competition_pk}))

    messages.error(request, "Invalid request method.")
    return HttpResponseRedirect(reverse('competitions:manage_competition', kwargs={'competition_pk': competition_pk}))

class EditWeightClassesView(View):
    template_name = 'competitions/edit_weight_classes.html'

    def get(self, request, competition_pk):
        competition = get_object_or_404(Competition, pk=competition_pk)
        form = EditWeightClassesForm(competition=competition)
        return render(request, self.template_name, {'form': form, 'competition': competition})

    def post(self, request, competition_pk):
        competition = get_object_or_404(Competition, pk=competition_pk)
        form = EditWeightClassesForm(request.POST, competition=competition)
        if form.is_valid():
            # Save the selected weight classes
            competition.allowed_weight_classes.set(form.cleaned_data['weight_classes'])
            return redirect('competitions:manage_competition', competition.pk)
        return render(request, self.template_name, {'form': form, 'competition': competition})


class AthleteCheckInView(View):
    template_name = 'competitions/checkin_athletes.html'

    def get(self, request, competition_pk):
        competition = get_object_or_404(Competition, pk=competition_pk)
        events = competition.events.all().order_by('order')

        athletes = AthleteCompetition.objects.filter(competition=competition) \
            .select_related('athlete__user', 'division', 'weight_class', 'tshirt_size') \
            .order_by('athlete__gender', 'weight_class__name', 'weight_class__weight_d', 'athlete__user__last_name',
                      'athlete__user__first_name')

        # Prefetch event notes to avoid N+1 queries
        athlete_notes = AthleteEventNote.objects.filter(
            athlete_competition__competition=competition
        ).select_related('event').prefetch_related('athlete_competition')

        # Prefetch lane assignments
        lane_assignments = LaneAssignment.objects.filter(
            athlete_competition__competition=competition
        ).select_related('event')

        # Initialize empty dictionaries for all athletes and events
        notes_map = {}
        lanes_map = {}

        # Initialize maps with empty dicts for each athlete and event
        for athlete in athletes:
            athlete_id = athlete.pk
            notes_map[athlete_id] = {}
            lanes_map[athlete_id] = {}

            for event in events:
                notes_map[athlete_id][event.pk] = {}  # Initialize with empty dict

        # Group notes by athlete_competition and event
        for note in athlete_notes:
            if note.event_id not in notes_map[note.athlete_competition_id]:
                notes_map[note.athlete_competition_id][note.event_id] = {}
            notes_map[note.athlete_competition_id][note.event_id][note.note_type] = note.note_value

        # Group lane assignments by athlete_competition and event
        for lane in lane_assignments:
            lanes_map[lane.athlete_competition_id][lane.event_id] = {
                'lane': lane.lane_number,
                'heat': lane.heat_number
            }

        # Group athletes
        grouped_athletes = {}
        for gender, gender_group in groupby(athletes, key=lambda x: x.athlete.gender):
            grouped_athletes[gender] = {}
            for weight_class, weight_class_group in groupby(list(gender_group), key=lambda x: x.weight_class):
                grouped_athletes[gender][weight_class] = list(weight_class_group)

        return render(request, self.template_name, {
            'competition': competition,
            'grouped_athletes': grouped_athletes,
            'events': events,
            'notes_map': notes_map,
            'lanes_map': lanes_map,
        })

    def post(self, request, competition_pk):
        competition = get_object_or_404(Competition, pk=competition_pk)
        athletes = AthleteCompetition.objects.filter(competition=competition)

        if "save_check_in" in request.POST:
            for athlete in athletes:
                showed_up = request.POST.get(f"showed_up_{athlete.pk}") == "on"
                weight_in = request.POST.get(f"weight_in_{athlete.pk}")

                athlete.signed_up = showed_up
                if weight_in:
                    athlete.weigh_in = weight_in
                athlete.save()

                # Process event notes
                for event in competition.events.all():
                    note_types = request.POST.getlist(f"note_type_{athlete.pk}_{event.pk}")
                    note_values = request.POST.getlist(f"note_value_{athlete.pk}_{event.pk}")

                    # Clear existing notes not in the submission
                    AthleteEventNote.objects.filter(
                        athlete_competition=athlete,
                        event=event
                    ).exclude(note_type__in=note_types).delete()

                    # Update or create notes
                    for i, note_type in enumerate(note_types):
                        if note_type and i < len(note_values):  # Ensure there's a corresponding value
                            note_value = note_values[i]
                            if note_value:  # Only save non-empty notes
                                AthleteEventNote.objects.update_or_create(
                                    athlete_competition=athlete,
                                    event=event,
                                    note_type=note_type,
                                    defaults={'note_value': note_value}
                                )

                    if event.number_of_lanes > 1:
                        lane_number = request.POST.get(f"lane_{athlete.pk}_{event.pk}")
                        heat_number = request.POST.get(f"heat_{athlete.pk}_{event.pk}", 1)

                        if lane_number and lane_number.isdigit():
                            LaneAssignment.objects.update_or_create(
                                athlete_competition=athlete,
                                event=event,
                                defaults={
                                    'lane_number': int(lane_number),
                                    'heat_number': int(heat_number) if heat_number and heat_number.isdigit() else 1
                                }
                            )
                        else:
                            # If lane is cleared, delete the assignment
                            LaneAssignment.objects.filter(
                                athlete_competition=athlete,
                                event=event
                            ).delete()

            messages.success(request, "Athlete check-in data and notes saved successfully.")

        elif "finalize_check_in" in request.POST:
            for athlete in athletes:
                showed_up = request.POST.get(f"showed_up_{athlete.pk}") == "on"
                if not showed_up:
                    # Delete athlete's notes before deleting athlete
                    AthleteEventNote.objects.filter(athlete_competition=athlete).delete()
                    LaneAssignment.objects.filter(athlete_competition=athlete).delete()
                    athlete.delete()
                    messages.success(request, "Athletes who did not check in have been removed.")

        return redirect('competitions:manage_competition', competition.pk)

@method_decorator(login_required, name="dispatch")
class AssignWeightClassesView(View):
    """
    View for assigning weight classes to divisions within a competition.
    """
    template_name = "competitions/assign_weight_classes.html"

    def get(self, request, *args, **kwargs):
        """
        Displays the available divisions and weight classes for assignment.
        """
        competition_id = self.kwargs.get("pk")
        competition = get_object_or_404(Competition, pk=competition_id)

        # Fetch divisions and available weight classes based on the competition's federation
        allowed_divisions = competition.allowed_divisions.all()
        division_weight_classes = {
            division: WeightClass.objects.filter(federation=competition.federation)
            for division in allowed_divisions
        }

        return render(
            request,
            self.template_name,
            {
                "competition": competition,
                "division_weight_classes": division_weight_classes,
            },
        )

    def post(self, request, *args, **kwargs):
        """
        Processes the weight class assignment to divisions in the competition.
        """
        competition = get_object_or_404(Competition, pk=self.kwargs.get("pk"))

        for key, weight_class_ids in request.POST.lists():
            if key.startswith("division_"):
                division_id = key.replace("division_", "")
                division = get_object_or_404(Division, pk=division_id)

                # Assign selected weight classes to the division
                WeightClass.objects.filter(pk__in=weight_class_ids).update(division=division)

        messages.success(request, "Weight classes were successfully assigned to divisions!")
        return redirect("competitions:manage_competition", competition_pk=competition.pk)

class CombineWeightClassesView(LoginRequiredMixin, UserPassesTestMixin, generic.FormView):
    template_name = "competitions/combine_weight_classes.html"
    form_class = CombineWeightClassesForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        competition = get_object_or_404(Competition, pk=self.kwargs['competition_pk'])
        kwargs['competition'] = competition
        print("✅ Form kwargs initialized:", kwargs)
        return kwargs

    def form_valid(self, form):
        print("✅ Form is valid")
        competition = get_object_or_404(Competition, pk=self.kwargs['competition_pk'])
        division = form.cleaned_data['division']
        from_weight_class = form.cleaned_data['from_weight_class']
        to_weight_class = form.cleaned_data['to_weight_class']

        print(f"📌 Division: {division}")
        print(f"📌 From Weight Class: {from_weight_class}")
        print(f"📌 To Weight Class: {to_weight_class}")

        if from_weight_class == to_weight_class:
            print("❌ Cannot combine the same weight class")
            messages.error(self.request, "You cannot combine a weight class with itself.")
            return redirect('competitions:combine_weight_classes', competition_pk=competition.pk)

        try:
            # Update all athletes in the 'from' weight class to the 'to' weight class
            print("🔄 Reassigning athletes to new weight class...")
            AthleteCompetition.objects.filter(
                competition=competition,
                division=division,
                weight_class=from_weight_class
            ).update(weight_class=to_weight_class)

            # Delete the old weight class if it's no longer needed
            print(f"🔍 Checking if {from_weight_class} can be removed...")
            if not AthleteCompetition.objects.filter(weight_class=from_weight_class).exists():
                print("🗑️ Deleting unused weight class...")
                from_weight_class.delete()

            print("✅ Combination successful")
            messages.success(
                self.request,
                f"Successfully combined {from_weight_class} into {to_weight_class}."
            )
        except Exception as e:
            print(f"🔥 Error during combination: {e}")  # Debugging error
            messages.error(self.request, f"An error occurred: {e}")  # Show actual error to user

        return redirect('competitions:manage_competition', competition_pk=competition.pk)

    def form_invalid(self, form):
        print("❌ Form is invalid")
        print("🚨 Errors:", form.errors)
        return super().form_invalid(form)

    def test_func(self):
        competition = get_object_or_404(Competition, pk=self.kwargs['competition_pk'])
        print(f"🔍 Test function called. Organizer: {competition.organizer}")
        return self.request.user == competition.organizer

class CustomDivisionCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Division
    form_class = CustomDivisionForm
    template_name = "competitions/custom_division_form.html"

    def form_valid(self, form):
        # Get the competition instance
        competition = get_object_or_404(Competition, pk=self.kwargs['competition_pk'])

        # Assign the competition to the division being created
        form.instance.competition = competition

        # Save the form (create the division)
        response = super().form_valid(form)

        # Add the newly created division to the competition's allowed divisions
        competition.allowed_divisions.add(form.instance)

        return response

    def get_success_url(self):
        return reverse('competitions:manage_competition', kwargs={'competition_pk': self.kwargs['competition_pk']})

    def test_func(self):
        competition = get_object_or_404(Competition, pk=self.kwargs['competition_pk'])
        return self.request.user == competition.organizer

def add_custom_weight_class(request, competition_pk):
    """
    View to add a custom weight class to a competition.
    """
    competition = get_object_or_404(Competition, pk=competition_pk)

    if request.method == "POST":
        form = CustomWeightClassForm(request.POST, competition=competition)
        if form.is_valid():
            weight_class = form.save(commit=False)
            weight_class.competition = competition
            weight_class.is_custom = True
            weight_class.federation = competition.federation  # ✅ Assign federation from competition
            weight_class.save()
            return redirect("competitions:manage_competition", competition_pk=competition.pk)
    else:
        form = CustomWeightClassForm(competition=competition)

    return render(request, "competitions/custom_weight_class_form.html", {"form": form, "competition": competition})


@method_decorator(login_required, name="dispatch")
class CompetitionRunOrderView(LoginRequiredMixin, View):
    template_name = 'competitions/competition_run_order.html'

    def get(self, request, competition_pk, event_pk=None):
        competition = get_object_or_404(Competition, pk=competition_pk)

        # Check if user is the organizer
        if request.user != competition.organizer:
            messages.error(request, "You are not authorized to view this page.")
            return redirect('competitions:manage_competition', competition_pk=competition.pk)

        # Get all events for this competition
        events = competition.events.all().order_by('order')

        # If no specific event is selected, choose the first event
        if not event_pk and events.exists():
            event_pk = events.first().pk

        # Get the selected event
        current_event = get_object_or_404(Event, pk=event_pk) if event_pk else None

        # Initialize event_notes as an empty dictionary
        event_notes = {}
        # Initialize lanes data structure
        lanes_data = {}
        first_pending_index = 0  # For backward compatibility

        # Get run orders for the current event
        if current_event:
            run_orders = CompetitionRunOrder.objects.filter(
                competition=competition,
                event=current_event
            ).select_related(
                'athlete_competition__athlete__user',
                'athlete_competition__division',
                'athlete_competition__weight_class'
            ).order_by('order')

            # Fetch results for all athletes in this event
            results = Result.objects.filter(
                event=current_event,
                athlete_competition__in=[ro.athlete_competition for ro in run_orders]
            ).select_related('athlete_competition')

            results_map = {result.athlete_competition_id: result for result in results}

            # Fetch event notes for athletes in this event
            athlete_event_notes = AthleteEventNote.objects.filter(
                athlete_competition__competition=competition,
                event=current_event
            ).select_related(
                'athlete_competition__athlete__user',
                'event'
            )

            # Organize notes by athlete competition and event
            for note in athlete_event_notes:
                athlete_id = note.athlete_competition_id
                if athlete_id not in event_notes:
                    event_notes[athlete_id] = {}

                if note.event_id not in event_notes[athlete_id]:
                    event_notes[athlete_id][note.event_id] = {}

                event_notes[athlete_id][note.event_id][note.note_type] = note.note_value

            # Initialize empty dictionary for athlete_competitions with no notes
            for run_order in run_orders:
                athlete_id = run_order.athlete_competition_id
                if athlete_id not in event_notes:
                    event_notes[athlete_id] = {}

                # Group by lane and heat
                lane_number = run_order.lane_number or 1  # Default to lane 1 if not assigned
                heat_number = run_order.heat_number or 1  # Default to heat 1 if not assigned

                # Initialize lane if not exists
                if lane_number not in lanes_data:
                    lanes_data[lane_number] = {
                        'current': None,
                        'on_deck': None,
                        'pending': [],
                        'completed': [],
                        'heats': set()
                    }

                # Add heat to the set of heats for this lane
                lanes_data[lane_number]['heats'].add(heat_number)

                # Categorize run orders by status
                if run_order.status == 'current':
                    lanes_data[lane_number]['current'] = run_order
                elif run_order.status == 'completed':
                    lanes_data[lane_number]['completed'].append(run_order)
                    # Attach score and points
                    athlete_comp_id = run_order.athlete_competition_id
                    if athlete_comp_id in results_map:
                        run_order.score = results_map[athlete_comp_id].value
                        run_order.points = results_map[athlete_comp_id].points_earned
                    else:
                        run_order.score = None
                        run_order.points = 0
                elif run_order.status == 'pending':
                    lanes_data[lane_number]['pending'].append(run_order)

            # Sort pending athletes and find first on-deck athlete for each lane
            for lane_number in lanes_data:
                lanes_data[lane_number]['pending'].sort(key=lambda x: x.order)
                if lanes_data[lane_number]['pending']:
                    lanes_data[lane_number]['on_deck'] = lanes_data[lane_number]['pending'][0]
                    # Remove on-deck from pending to avoid duplication
                    lanes_data[lane_number]['pending'] = lanes_data[lane_number]['pending'][1:]

                # Find index of first pending athlete (for backward compatibility)
                for i, ro in enumerate(run_orders):
                    if ro.status == 'pending':
                        first_pending_index = i
                        break
        else:
            run_orders = []

        # Determine note types based on current event
        note_types = self.get_note_types_for_event(current_event) if current_event else []

        context = {
            'competition': competition,
            'events': events,
            'current_event': current_event,
            'run_orders': run_orders,
            'lanes_data': lanes_data,
            'first_pending_index': first_pending_index,
            'event_notes': event_notes,
            'note_types': note_types,
        }

        return render(request, self.template_name, context)

    def get_note_types_for_event(self, event):
        """
        Determine appropriate note types based on the event's weight type.
        """
        if not event:
            return []

        base_types = ['general', 'equipment', 'custom']

        if event.weight_type == 'max':
            return base_types + ['opening_weight', 'next_attempt', 'rack_height']
        elif event.weight_type == 'time':
            return base_types + ['target_time', 'strategy']
        elif event.weight_type == 'distance':
            return base_types + ['implement_selection']
        elif event.weight_type == 'reps':
            return base_types + ['target_reps']

        return base_types

    def post(self, request, competition_pk, event_pk):
        competition = get_object_or_404(Competition, pk=competition_pk)
        event = get_object_or_404(Event, pk=event_pk)

        # Check if user is the organizer
        if request.user != competition.organizer:
            messages.error(request, "You are not authorized to modify the run order.")
            return redirect('competitions:manage_competition', competition_pk=competition.pk)

        action = request.POST.get('action')
        lane_number = request.POST.get('lane_number')  # Added lane parameter for lane-specific actions

        with transaction.atomic():
            if action == 'generate_run_order':
                # Clear existing run orders for this event
                CompetitionRunOrder.objects.filter(
                    competition=competition,
                    event=event
                ).delete()

                # Get athletes for this event and competition
                athlete_competitions = AthleteCompetition.objects.filter(
                    competition=competition
                ).select_related(
                    'athlete__user',
                    'division',
                    'weight_class'
                ).order_by('athlete__user__last_name', 'athlete__user__first_name')

                # Determine if this event needs lane assignments
                needs_lanes = event.number_of_lanes > 1

                if needs_lanes:
                    # Group athletes by existing lane assignments or create new ones
                    lane_assignments = {}

                    # Get existing lane assignments
                    existing_assignments = LaneAssignment.objects.filter(
                        athlete_competition__in=athlete_competitions,
                        event=event
                    )

                    assigned_athletes = set()
                    for assignment in existing_assignments:
                        lane_assignments.setdefault(assignment.lane_number, {}).setdefault(assignment.heat_number, [])
                        lane_assignments[assignment.lane_number][assignment.heat_number].append(
                            assignment.athlete_competition)
                        assigned_athletes.add(assignment.athlete_competition.id)

                    # Assign remaining athletes evenly across lanes and heats
                    unassigned = [ac for ac in athlete_competitions if ac.id not in assigned_athletes]

                    # Simple assignment logic - distribute evenly
                    lane_counter = 1
                    heat_counter = 1
                    athletes_per_heat = event.number_of_lanes  # We'll put this many athletes in each heat

                    for athlete in unassigned:
                        lane_assignments.setdefault(lane_counter, {}).setdefault(heat_counter, [])
                        lane_assignments[lane_counter][heat_counter].append(athlete)

                        # Create the lane assignment record
                        LaneAssignment.objects.update_or_create(
                            athlete_competition=athlete,
                            event=event,
                            defaults={
                                'lane_number': lane_counter,
                                'heat_number': heat_counter
                            }
                        )

                        # Move to next lane
                        lane_counter += 1
                        if lane_counter > event.number_of_lanes:
                            lane_counter = 1
                            if len(lane_assignments[1][heat_counter]) >= athletes_per_heat:
                                heat_counter += 1

                    # Create run orders based on lane assignments
                    order_counter = 1
                    for lane in range(1, event.number_of_lanes + 1):
                        if lane in lane_assignments:
                            for heat in sorted(lane_assignments[lane].keys()):
                                for athlete_comp in lane_assignments[lane][heat]:
                                    status = 'pending'
                                    # First athlete in first heat of each lane starts as current
                                    if heat == min(lane_assignments[lane].keys()) and athlete_comp == \
                                            lane_assignments[lane][heat][0]:
                                        status = 'current'

                                    CompetitionRunOrder.objects.create(
                                        competition=competition,
                                        event=event,
                                        athlete_competition=athlete_comp,
                                        order=order_counter,
                                        lane_number=lane,
                                        heat_number=heat,
                                        status=status,
                                        started_at=timezone.now() if status == 'current' else None
                                    )
                                    order_counter += 1

                else:
                    # Create run order without lanes (original logic)
                    for order, athlete_comp in enumerate(athlete_competitions, 1):
                        status = 'pending'
                        if order == 1:  # First athlete starts as current
                            status = 'current'

                        CompetitionRunOrder.objects.create(
                            competition=competition,
                            event=event,
                            athlete_competition=athlete_comp,
                            order=order,
                            lane_number=1,  # All in lane 1 for single-lane events
                            heat_number=1,  # All in heat 1 for single-lane events
                            status=status,
                            started_at=timezone.now() if status == 'current' else None
                        )

                messages.success(request, f"Run order generated for {event.name}")

            elif action == 'update_current_lifter':
                run_order_id = request.POST.get('run_order_id')
                run_order = get_object_or_404(CompetitionRunOrder, pk=run_order_id)

                # Reset current lifter for the specific lane only
                CompetitionRunOrder.objects.filter(
                    competition=competition,
                    event=event,
                    lane_number=run_order.lane_number,
                    status='current'
                ).update(status='pending')

                # Set the selected lifter as current
                run_order.status = 'current'
                run_order.started_at = timezone.now()
                run_order.save()

                messages.success(request,
                                 f"Current lifter updated to {run_order.athlete_competition.athlete.user.get_full_name()} in Lane {run_order.lane_number}")

            elif action == 'save_event_note':
                # Save or update an event note
                athlete_competition_id = request.POST.get('athlete_competition_id')
                note_type = request.POST.get('note_type')
                note_value = request.POST.get('note_value')

                athlete_competition = get_object_or_404(AthleteCompetition, pk=athlete_competition_id)

                # Update or create the note
                AthleteEventNote.objects.update_or_create(
                    athlete_competition=athlete_competition,
                    event=event,
                    note_type=note_type,
                    defaults={'note_value': note_value}
                )

                messages.success(request, f"Note saved for {athlete_competition.athlete.user.get_full_name()}")

            elif action == 'complete_current_lifter':
                run_order_id = request.POST.get('run_order_id')
                score_value = request.POST.get('score_value')  # New field for score input
                current_run_order = get_object_or_404(CompetitionRunOrder, pk=run_order_id, status='current')
                lane_number = current_run_order.lane_number

                # Mark current lifter as completed
                current_run_order.status = 'completed'
                current_run_order.completed_at = timezone.now()
                current_run_order.save()

                # Save the score to the Result model if provided
                if score_value:
                    athlete_competition = current_run_order.athlete_competition
                    event = current_run_order.event
                    result, created = Result.objects.get_or_create(
                        athlete_competition=athlete_competition,
                        event=event,
                        defaults={'value': score_value}
                    )
                    if not created and result.value != score_value:
                        result.value = score_value
                        result.save()
                    # Recalculate points and rankings
                    calculate_points_and_rankings(competition.pk, event.pk)
                    # Debugging: Verify the result was saved
                    updated_result = Result.objects.get(athlete_competition=athlete_competition, event=event)
                    print(f"Saved score for {athlete_competition.athlete.user.get_full_name()}: {updated_result.value}")

                # Find the pending lifters in the same lane
                pending_lifters = CompetitionRunOrder.objects.filter(
                    competition=competition,
                    event=event,
                    lane_number=lane_number,
                    status='pending'
                ).order_by('heat_number', 'order')

                if pending_lifters.exists():
                    # Move first pending to current
                    next_lifter = pending_lifters.first()
                    next_lifter.status = 'current'
                    next_lifter.started_at = timezone.now()
                    next_lifter.save()

                    # Check if there's a second pending lifter to become on-deck
                    if pending_lifters.count() > 1:
                        on_deck_lifter = pending_lifters[1]  # Get the second pending lifter

                        # Update success message to include score info if provided
                        if score_value:
                            messages.success(
                                request,
                                f"Lift completed in Lane {lane_number}. {current_run_order.athlete_competition.athlete.user.get_full_name()} "
                                f"marked as completed with score {score_value}. "
                                f"{next_lifter.athlete_competition.athlete.user.get_full_name()} is now the current lifter. "
                                f"{on_deck_lifter.athlete_competition.athlete.user.get_full_name()} is on deck."
                            )
                        else:
                            messages.success(
                                request,
                                f"Lift completed in Lane {lane_number}. {current_run_order.athlete_competition.athlete.user.get_full_name()} "
                                f"marked as completed. "
                                f"{next_lifter.athlete_competition.athlete.user.get_full_name()} is now the current lifter. "
                                f"{on_deck_lifter.athlete_competition.athlete.user.get_full_name()} is on deck."
                            )
                    else:
                        if score_value:
                            messages.success(
                                request,
                                f"Lift completed in Lane {lane_number}. {current_run_order.athlete_competition.athlete.user.get_full_name()} "
                                f"marked as completed with score {score_value}. "
                                f"{next_lifter.athlete_competition.athlete.user.get_full_name()} is now the current lifter. "
                                f"No more lifters in this lane's queue."
                            )
                        else:
                            messages.success(
                                request,
                                f"Lift completed in Lane {lane_number}. {current_run_order.athlete_competition.athlete.user.get_full_name()} "
                                f"marked as completed. "
                                f"{next_lifter.athlete_competition.athlete.user.get_full_name()} is now the current lifter. "
                                f"No more lifters in this lane's queue."
                            )
                else:
                    if score_value:
                        messages.success(
                            request,
                            f"Lift completed in Lane {lane_number}. {current_run_order.athlete_competition.athlete.user.get_full_name()} "
                            f"marked as completed with score {score_value}. No more lifters in this lane's queue."
                        )
                    else:
                        messages.success(
                            request,
                            f"Lift completed in Lane {lane_number}. {current_run_order.athlete_competition.athlete.user.get_full_name()} "
                            f"marked as completed. No more lifters in this lane's queue."
                        )

            elif action == 'reactivate_lifter':
                run_order_id = request.POST.get('run_order_id')
                completed_run_order = get_object_or_404(CompetitionRunOrder, pk=run_order_id, status='completed')

                # Change the status back to pending
                completed_run_order.status = 'pending'
                completed_run_order.completed_at = None
                completed_run_order.save()

                messages.success(
                    request,
                    f"{completed_run_order.athlete_competition.athlete.user.get_full_name()} reactivated and moved back to upcoming lifters in Lane {completed_run_order.lane_number}."
                )

        return redirect('competitions:competition_run_order',
                        competition_pk=competition.pk,
                        event_pk=event.pk)