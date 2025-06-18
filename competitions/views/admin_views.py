import csv
import json
from collections import defaultdict
from itertools import groupby
from decimal import Decimal
from django.db import transaction
from django.db.models import Max
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
    LaneAssignment, CompetitionRunOrder, Event, Result, EventImplement
from competitions.forms import EditWeightClassesForm, CustomWeightClassForm, CustomDivisionForm, \
    CombineWeightClassesForm
from competitions.utils import get_onboarding_status
from competitions.views import calculate_points_and_rankings


class OrganizerCompetitionsView(TemplateView):
    template_name = "competitions/organizer_competitions.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        organizer = self.request.user

        # Get competitions organized by the user
        all_competitions = Competition.objects.filter(organizer=organizer)
        upcoming_competitions = all_competitions.filter(comp_date__gte=timezone.now(),
                                                        status__in=['upcoming', 'limited', 'full']).order_by(
            'comp_date')
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
        messages.success(request,
                         "Email notifications enabled. You will now receive an email every time an athlete signs up.")
    else:
        messages.success(request, "Email notifications disabled. You will no longer receive sign-up emails.")

    return redirect('competitions:manage_competition', competition_pk)


def download_athlete_table(request, competition_pk):
    competition = Competition.objects.get(pk=competition_pk)
    athletes = AthleteCompetition.objects.filter(competition=competition).select_related('athlete__user',
                                                                                         'weight_class', 'division',
                                                                                         'tshirt_size')

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

        # Get all registered athletes
        athletes = AthleteCompetition.objects.filter(competition=competition) \
            .select_related('athlete__user', 'division', 'weight_class', 'tshirt_size') \
            .order_by(
            'athlete__gender',
            'weight_class__name',
            'weight_class__weight_d',
            'athlete__user__last_name',
            'athlete__user__first_name'
        )

        # Prefetch maps for event notes and lane assignments
        notes_map = defaultdict(lambda: defaultdict(dict))
        lanes_map = defaultdict(lambda: defaultdict(dict))

        for note in AthleteEventNote.objects.filter(athlete_competition__competition=competition):
            notes_map[note.athlete_competition_id][note.event_id][note.note_type] = note.note_value

        for lane in LaneAssignment.objects.filter(athlete_competition__competition=competition):
            lanes_map[lane.athlete_competition_id][lane.event_id] = {
                'lane': lane.lane_number,
                'heat': lane.heat_number
            }

        # Group athletes: gender > weight class (as string label)
        grouped_athletes = defaultdict(lambda: defaultdict(list))
        for athlete in athletes:
            gender = athlete.athlete.gender or "Unknown"
            weight_class = athlete.weight_class
            if weight_class:
                wc_key = str(weight_class)
            else:
                # Include division in key to avoid grouping across divisions
                wc_key = f"Single Class – {athlete.division.name}"

            grouped_athletes[gender][wc_key].append(athlete)

        # Optional debug output
        print("Grouped Athletes:")
        for gender, wc_dict in grouped_athletes.items():
            print(f" Gender: {gender}")
            for wc_key, group in wc_dict.items():
                print(f"   - Weight Class: {wc_key} -> {len(group)} athletes")

        return render(request, self.template_name, {
            'competition': competition,
            'grouped_athletes': {k: dict(v) for k, v in grouped_athletes.items()},
            'events': events,
            'notes_map': notes_map,
            'lanes_map': lanes_map,
        })

    def post(self, request, competition_pk):
        competition = get_object_or_404(Competition, pk=competition_pk)
        athletes = AthleteCompetition.objects.filter(competition=competition)

        # --- Save Check-In (present, weigh-in, notes) ---
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

                    # Remove any notes the user deleted
                    AthleteEventNote.objects.filter(
                        athlete_competition=athlete,
                        event=event
                    ).exclude(note_type__in=note_types).delete()

                    # Update or create the submitted notes
                    for i, note_type in enumerate(note_types):
                        if note_type and i < len(note_values):
                            note_val = note_values[i]
                            if note_val:
                                AthleteEventNote.objects.update_or_create(
                                    athlete_competition=athlete,
                                    event=event,
                                    note_type=note_type,
                                    defaults={'note_value': note_val}
                                )

            messages.success(request, "Athlete check-in data and notes saved successfully.")

        # --- Finalize Check-In (lanes + remove no-shows) ---
        if "finalize_check_in" in request.POST:
            for athlete in athletes:
                showed_up = request.POST.get(f"showed_up_{athlete.pk}") == "on"

                if showed_up:
                    # Persist lane & heat for multi-lane events
                    for event in competition.events.all():
                        if event.number_of_lanes > 1:
                            lane_val = request.POST.get(f"lane_{athlete.pk}_{event.pk}")
                            heat_val = request.POST.get(f"heat_{athlete.pk}_{event.pk}") or "1"

                            if lane_val and lane_val.isdigit():
                                LaneAssignment.objects.update_or_create(
                                    athlete_competition=athlete,
                                    event=event,
                                    defaults={
                                        'lane_number': int(lane_val),
                                        'heat_number': int(heat_val) if heat_val.isdigit() else 1
                                    }
                                )
                            else:
                                # Delete if user cleared the lane select
                                LaneAssignment.objects.filter(
                                    athlete_competition=athlete,
                                    event=event
                                ).delete()
                else:
                    # Remove all notes, lanes, and the athlete record for no-shows
                    AthleteEventNote.objects.filter(athlete_competition=athlete).delete()
                    LaneAssignment.objects.filter(athlete_competition=athlete).delete()
                    athlete.delete()

            messages.success(request, "Check-in finalized and non-show athletes removed.")

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
        competition = get_object_or_404(Competition, pk=kwargs['pk'])

        # Clear existing weight classes for this competition
        WeightClass.objects.filter(competition=competition).delete()

        for key in request.POST:
            if not key.startswith("division_"):
                continue

            try:
                division_id = int(key.split("_")[1])
            except (IndexError, ValueError):
                continue

            division = Division.objects.filter(pk=division_id, competition=competition).first()
            if not division:
                continue

            weight_class_ids = request.POST.getlist(key)
            for wc_id in weight_class_ids:
                base_wc = get_object_or_404(WeightClass, pk=wc_id)

                # Check if one already exists with these values to avoid duplicate insert
                if WeightClass.objects.filter(
                        name=base_wc.name,
                        gender=base_wc.gender,
                        division=division,
                        competition=competition
                ).exists():
                    continue

                # Clone into this competition
                WeightClass.objects.create(
                    name=base_wc.name,
                    gender=base_wc.gender,
                    federation=base_wc.federation,
                    weight_d=base_wc.weight_d,
                    category=base_wc.category,
                    division=division,
                    competition=competition,
                    is_custom=False
                )

        messages.success(request, "Weight classes successfully assigned.")
        return redirect('competitions:manage_competition', competition_pk=competition.pk)


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
    print("➡️ Entered add_custom_weight_class")
    print("   HTTP method:", request.method)
    print("   competition_pk:", competition_pk)

    competition = get_object_or_404(Competition, pk=competition_pk)
    print("   Loaded Competition:", competition)

    if request.method == "POST":
        print("✉️  POST data:", dict(request.POST))

        form = CustomWeightClassForm(request.POST, competition=competition)
        print("   Form bound?", form.is_bound)

        is_valid = form.is_valid()
        print("   form.is_valid() =>", is_valid)
        if not is_valid:
            print("   form.errors:", form.errors)

        if is_valid:
            wc = form.save(commit=False)
            print("   Form.save(commit=False) =>", wc)
            wc.competition = competition
            wc.is_custom = True
            wc.federation = competition.federation
            wc.save()
            print("✅ WeightClass saved, now redirecting")
            return redirect("competitions:manage_competition", competition_pk=competition_pk)
    else:
        print("🔍 GET request, instantiating empty form")
        form = CustomWeightClassForm(competition=competition)

    print("🖼️ Rendering template, form.errors:", form.errors)
    return render(request,
                  "competitions/custom_weight_class_form.html",
                  {"form": form, "competition": competition})


@method_decorator(login_required, name="dispatch")
class CompetitionRunOrderView(LoginRequiredMixin, View):
    template_name = 'competitions/competition_run_order.html'

    def get(self, request, competition_pk, event_pk=None):
        competition = get_object_or_404(Competition, pk=competition_pk)

        if request.user != competition.organizer:
            messages.error(request, "You are not authorized to view this page.")
            return redirect('competitions:manage_competition', competition_pk=competition.pk)

        events = competition.events.all().order_by('order')
        if not event_pk and events.exists():
            event_pk = events.first().pk
        current_event = get_object_or_404(Event, pk=event_pk) if event_pk else None

        event_notes = {}
        first_pending_index = 0

        if current_event:
            run_orders = CompetitionRunOrder.objects.filter(
                competition=competition,
                event=current_event
            ).select_related(
                'athlete_competition__athlete__user',
                'athlete_competition__division',
                'athlete_competition__weight_class'
            ).order_by('order')

            results = Result.objects.filter(
                event=current_event,
                athlete_competition__competition=competition
            ).select_related('athlete_competition')
            results_map = {r.athlete_competition_id: r for r in results}

            notes_qs = AthleteEventNote.objects.filter(
                athlete_competition__competition=competition,
                event=current_event
            )

            event_notes = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
            for note in notes_qs:
                ac_id = note.athlete_competition_id
                event_id = note.event_id
                note_type = note.note_type
                event_notes[ac_id][event_id][note_type].append({
                    "id": note.id,
                    "value": note.note_value,
                    "attempt": note.attempt_number or 1
                })

            # NEW: pull lane assignments to override lane/heat from run_order
            lane_map = {
                (la.athlete_competition_id, la.event_id): la
                for la in LaneAssignment.objects.filter(
                    athlete_competition__competition=competition,
                    event=current_event
                )
            }

            # Initialize lanes_data for all possible lanes
            lanes_data = {
                lane_num: {'current': None, 'on_deck': None, 'pending': [], 'completed': [], 'heats': set()}
                for lane_num in range(1, (current_event.number_of_lanes or 1) + 1)
            }

            for ro in run_orders:
                ac_id = ro.athlete_competition_id
                event_notes.setdefault(ac_id, {})

                # Get lane/heat from LaneAssignment if it exists
                assignment = lane_map.get((ac_id, current_event.id))
                lane = assignment.lane_number if assignment else (ro.lane_number or 1)
                heat = assignment.heat_number if assignment else (ro.heat_number or 1)

                lanes_data[lane]['heats'].add(heat)

                if ro.status == 'current':
                    lanes_data[lane]['current'] = ro
                elif ro.status == 'completed':
                    ro.score = results_map.get(ac_id, None) and results_map[ac_id].value
                    ro.points = results_map.get(ac_id, None) and results_map[ac_id].points_earned or 0
                    lanes_data[lane]['completed'].append(ro)
                else:
                    lanes_data[lane]['pending'].append(ro)

            for lane, data in lanes_data.items():
                # Force correct order sequence per lane
                data['pending'].sort(key=lambda x: x.order)
                for idx, ro in enumerate(data['pending'], start=1):
                    ro.order = idx  # Fix display order
                if data['pending']:
                    data['on_deck'] = data['pending'].pop(0)

            for i, ro in enumerate(run_orders):
                if ro.status == 'pending':
                    first_pending_index = i
                    break

            load_chart = {}
            for ro in run_orders:
                ac_pk = ro.athlete_competition_id
                load_chart.setdefault(ac_pk, [])
                # You can populate load_chart here later if needed

        else:
            run_orders = []
            load_chart = {}
            lanes_data = {}

        note_types = self.get_note_types_for_event(current_event) if current_event else []

        for ac_id, evs in event_notes.items():
            for ev_id, notes_dict in evs.items():
                notes_dict.pop('', None)
        active_tab = request.GET.get('tab', '')

        context = {
            'competition': competition,
            'events': events,
            'current_event': current_event,
            'run_orders': run_orders,
            'lanes_data': lanes_data,
            'first_pending_index': first_pending_index,
            'event_notes': event_notes,
            'note_types': note_types,
            'load_chart': load_chart,
            'active_tab': active_tab,
        }

        return render(request, self.template_name, context)

    def get_note_types_for_event(self, event):
        if not event:
            return []
        base = ['general', 'equipment', 'custom']
        w = event.weight_type
        if w == 'max':
            return base + ['opening_weight', 'next_attempt', 'rack_height']
        if w == 'time':
            return base + ['target_time', 'strategy']
        if w == 'distance':
            return base + ['implement_selection']
        if w == 'reps':
            return base + ['target_reps']
        return base

    def post(self, request, competition_pk, event_pk):
        competition = get_object_or_404(Competition, pk=competition_pk)
        event = get_object_or_404(Event, pk=event_pk)

        if request.user != competition.organizer:
            messages.error(request, "You are not authorized to modify the run order.")
            return redirect('competitions:manage_competition', competition_pk=competition.pk)

        action = request.POST.get('action')

        with transaction.atomic():
            if action == 'generate_run_order':
                run_order_method = request.POST.get("run_order_method", "division_signup")

                CompetitionRunOrder.objects.filter(competition=competition, event=event).delete()

                if run_order_method == "last_man_standing":
                    CompetitionRunOrder.objects.filter(competition=competition, event=event).delete()

                    # Fetch all athlete notes relevant to this event
                    notes = (
                        AthleteEventNote.objects
                        .filter(event=event, note_type__in=['opening_weight', 'next_attempt'])
                        .exclude(note_value__isnull=True)
                        .select_related('athlete_competition', 'athlete_competition__athlete__user')
                    )

                    # Parse weights and group by athlete_competition
                    weight_map = {}
                    for note in notes:
                        try:
                            weight = float(note.note_value)
                            ac_id = note.athlete_competition_id
                            weight_map.setdefault(ac_id, []).append(weight)
                        except (TypeError, ValueError):
                            continue

                    # Compute the lowest relevant weight per athlete
                    run_list = []
                    for ac_id, weights in weight_map.items():
                        try:
                            ac = AthleteCompetition.objects.select_related('athlete__user').get(pk=ac_id)
                            run_list.append((min(weights), ac))
                        except AthleteCompetition.DoesNotExist:
                            continue

                    run_list.sort(key=lambda x: x[0])  # ascending by weight

                    for order, (weight, ac) in enumerate(run_list, start=1):
                        status = 'current' if order == 1 else 'pending'
                        CompetitionRunOrder.objects.create(
                            competition=competition,
                            event=event,
                            athlete_competition=ac,
                            order=order,
                            lane_number=1,
                            heat_number=1,
                            status=status,
                            started_at=timezone.now() if status == 'current' else None
                        )

                    messages.success(request, f"Last Man Standing run order generated for {event.name}")
                else:
                    # FETCH all registered athletes grouped by division and sorted by registration
                    athlete_comps = AthleteCompetition.objects.filter(
                        competition=competition
                    ).select_related('division', 'athlete__user', 'athlete', 'weight_class').order_by('athlete__gender',
                                                                                                      'division__predefined_name',
                                                                                                      'weight_class__name',
                                                                                                      'registration_date')

                    # BUILD and save new run order entries
                    grouped = defaultdict(list)
                    for ac in athlete_comps:
                        division_label = ac.division.predefined_name or ac.division.custom_name or "Unassigned"
                        gender = ac.athlete.gender
                        weight_class = ac.weight_class.name if ac.weight_class else "Unassigned"
                        group_key = (gender, division_label, weight_class)
                        grouped[group_key].append(ac)

                    order = 1
                    for (gender, division_label, weight_class), group in grouped.items():
                        for ac in group:
                            status = 'current' if order == 1 else 'pending'
                            CompetitionRunOrder.objects.create(
                                competition=competition,
                                event=event,
                                athlete_competition=ac,
                                order=order,
                                lane_number=1,
                                heat_number=1,
                                status=status,
                                started_at=timezone.now() if status == 'current' else None
                            )
                            order += 1

                    messages.success(request, f"Run order generated by division and signup time for {event.name}")



            elif action == 'update_current_lifter':
                ro = get_object_or_404(CompetitionRunOrder, pk=request.POST.get('run_order_id'))
                CompetitionRunOrder.objects.filter(
                    competition=competition, event=event, lane_number=ro.lane_number, status='current'
                ).update(status='pending')
                ro.status, ro.started_at = 'current', timezone.now()
                ro.save()
                messages.success(
                    request,
                    f"Current lifter updated to {ro.athlete_competition.athlete.user.get_full_name()} in Lane {ro.lane_number}"
                )

            elif action == 'save_event_note':
                ac = get_object_or_404(AthleteCompetition, pk=request.POST.get('athlete_competition_id'))
                note_type = request.POST.get('note_type')
                note_value = request.POST.get('note_value')

                if not note_type or not note_value:
                    messages.error(request, "Both note type and value are required.")
                    return redirect('competitions:competition_run_order', competition_pk=competition.pk,
                                    event_pk=event.pk)

                # Try parsing float if applicable
                try:
                    note_value_float = float(note_value) if note_type in ['opening_weight', 'next_attempt'] else None
                except (ValueError, TypeError):
                    note_value_float = None

                AthleteEventNote.objects.update_or_create(
                    athlete_competition=ac,
                    event=event,
                    note_type=note_type,
                    defaults={
                        'note_value': note_value,
                        'note_value_float': note_value_float,
                    }
                )
                messages.success(request, f"Note saved for {ac.athlete.user.get_full_name()}")





            elif action == 'complete_current_lifter':

                MAX_ATTEMPTS = 4
                run_order_id = request.POST.get('run_order_id')
                score = request.POST.get('score_value')
                mark_as_done = request.POST.get('mark_as_done') == 'on'

                with transaction.atomic():
                    # 1) Lock the current lifter
                    current_ro = CompetitionRunOrder.objects.select_for_update().get(
                        pk=run_order_id,
                        competition=competition,
                        event=event,
                        status='current'
                    )
                    lane = current_ro.lane_number

                    # 2) Save the score/note & update Result
                    if score:
                        # record the attempt as a note
                        prior = AthleteEventNote.objects.filter(
                            athlete_competition=current_ro.athlete_competition,
                            event=event,
                            note_type='next_attempt'
                        ).aggregate(Max('attempt_number'))['attempt_number__max'] or 0
                        attempt_num = prior + 1

                        AthleteEventNote.objects.create(
                            athlete_competition=current_ro.athlete_competition,
                            event=event,
                            note_type='next_attempt',
                            note_value=score,
                            note_value_float=float(score),
                            attempt_number=attempt_num
                        )

                        result, created = Result.objects.get_or_create(
                            athlete_competition=current_ro.athlete_competition,
                            event=event,
                            defaults={'value': score}
                        )
                        if not created and result.value != score:
                            result.value = score
                            result.save()

                        # recalc points/rankings
                        calculate_points_and_rankings(competition.pk, event.pk)

                    # 3) Load and lock *all* run-orders in this lane, in proper order
                    all_ros = list(
                        CompetitionRunOrder.objects
                        .select_for_update()
                        .filter(competition=competition, event=event, lane_number=lane)
                        .order_by('heat_number', 'order')
                    )
                    # find index of the old current
                    idx = next(i for i, ro in enumerate(all_ros) if ro.pk == current_ro.pk)

                    # 4) Complete or re-queue the old current
                    #    If they still have attempts left and aren’t marked done, leave them as 'pending'
                    prior = AthleteEventNote.objects.filter(
                        athlete_competition=current_ro.athlete_competition,
                        event=event,
                        note_type='next_attempt'
                    ).aggregate(Max('attempt_number'))['attempt_number__max'] or 0
                    attempt_num = prior  # after creation above

                    if attempt_num < MAX_ATTEMPTS and not mark_as_done:
                        all_ros[idx].status = 'pending'
                        all_ros[idx].completed_at = None
                    else:
                        all_ros[idx].status = 'completed'
                        all_ros[idx].completed_at = timezone.now()

                    # 5) Promote the very next in line
                    new_current = None
                    if idx + 1 < len(all_ros):
                        new_current = all_ros[idx + 1]
                        new_current.status = 'current'
                        new_current.started_at = timezone.now()

                    # 6) Persist both changes
                    all_ros[idx].save()
                    if new_current:
                        new_current.save()

                # 7) Feedback message
                msg = f"Lane {lane}: "
                msg += f"{current_ro.athlete_competition.athlete.user.get_full_name()} " \
                       f"marked as {'completed' if all_ros[idx].status=='completed' else 're-queued'}"
                if score:
                    msg += f" with score {score}."
                if new_current:
                    msg += f" {new_current.athlete_competition.athlete.user.get_full_name()} is now current."
                    # Next on-deck is left in pending and will be picked up by your GET logic
                else:
                    msg += " No more lifters in this lane."

                messages.success(request, msg)

            elif action == 'reactivate_lifter':
                comp_ro = get_object_or_404(CompetitionRunOrder, pk=request.POST.get('run_order_id'),
                                            status='completed')
                comp_ro.status, comp_ro.completed_at = 'pending', None
                comp_ro.save()
                messages.success(
                    request,
                    f"{comp_ro.athlete_competition.athlete.user.get_full_name()} reactivated in Lane {comp_ro.lane_number}."
                )

        active_tab = request.POST.get('active_tab', '')
        response = redirect('competitions:competition_run_order', competition_pk=competition.pk, event_pk=event.pk)
        if active_tab:
            response['Location'] += f'?tab={active_tab}'
        return response
