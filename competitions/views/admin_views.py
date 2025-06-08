import csv
from collections import defaultdict
from itertools import groupby
from decimal import Decimal
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
    LaneAssignment, CompetitionRunOrder, Event, Result, EventImplement
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
        lanes_data = {}
        first_pending_index = 0

        if current_event:
            # --- Fetch run orders, results, and notes as before ---
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
            for note in notes_qs:
                ac_id = note.athlete_competition_id
                event_notes.setdefault(ac_id, {}).setdefault(note.event_id, {})[note.note_type] = note.note_value

            for ro in run_orders:
                ac_id = ro.athlete_competition_id
                event_notes.setdefault(ac_id, {})

                lane = ro.lane_number or 1
                heat = ro.heat_number or 1
                lanes_data.setdefault(lane, {
                    'current': None, 'on_deck': None,
                    'pending': [], 'completed': [], 'heats': set()
                })
                lanes_data[lane]['heats'].add(heat)

                if ro.status == 'current':
                    lanes_data[lane]['current'] = ro
                elif ro.status == 'completed':
                    ro.score = results_map.get(ac_id, None) and results_map[ac_id].value
                    ro.points = results_map.get(ac_id, None) and results_map[ac_id].points_earned or 0
                    lanes_data[lane]['completed'].append(ro)
                else:  # 'pending'
                    lanes_data[lane]['pending'].append(ro)

            for lane, data in lanes_data.items():
                data['pending'].sort(key=lambda x: x.order)
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

                athlete_div = ro.athlete_competition.division
                athlete_wc = ro.athlete_competition.weight_class


        else:
            run_orders = []
            load_chart = {}

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
            'load_chart': load_chart,
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
        lane_number = request.POST.get('lane_number')

        with transaction.atomic():
            if action == 'generate_run_order':
                CompetitionRunOrder.objects.filter(competition=competition, event=event).delete()
                athlete_comps = AthleteCompetition.objects.filter(competition=competition)\
                    .select_related('athlete__user','division','weight_class')\
                    .order_by('athlete__user__last_name','athlete__user__first_name')
                needs_lanes = event.number_of_lanes > 1

                if needs_lanes:
                    lane_assignments = {}
                    existing = LaneAssignment.objects.filter(
                        athlete_competition__in=athlete_comps, event=event
                    )
                    assigned = set()
                    for a in existing:
                        lane_assignments.setdefault(a.lane_number, {})\
                            .setdefault(a.heat_number, [])\
                            .append(a.athlete_competition)
                        assigned.add(a.athlete_competition.id)

                    unassigned = [ac for ac in athlete_comps if ac.id not in assigned]
                    lane_c, heat_c = 1, 1
                    per_heat = event.number_of_lanes
                    for ac in unassigned:
                        lane_assignments.setdefault(lane_c, {})\
                            .setdefault(heat_c, []).append(ac)
                        LaneAssignment.objects.update_or_create(
                            athlete_competition=ac, event=event,
                            defaults={'lane_number': lane_c, 'heat_number': heat_c}
                        )
                        lane_c += 1
                        if lane_c > event.number_of_lanes:
                            lane_c = 1
                            if len(lane_assignments[1][heat_c]) >= per_heat:
                                heat_c += 1

                    order = 1
                    for lane in range(1, event.number_of_lanes + 1):
                        for heat in sorted(lane_assignments.get(lane, {})):
                            for ac in lane_assignments[lane][heat]:
                                status = 'current' if heat == min(lane_assignments[lane]) and ac == lane_assignments[lane][heat][0] else 'pending'
                                CompetitionRunOrder.objects.create(
                                    competition=competition,
                                    event=event,
                                    athlete_competition=ac,
                                    order=order,
                                    lane_number=lane,
                                    heat_number=heat,
                                    status=status,
                                    started_at=timezone.now() if status=='current' else None
                                )
                                order += 1
                else:
                    for idx, ac in enumerate(athlete_comps, start=1):
                        status = 'current' if idx == 1 else 'pending'
                        CompetitionRunOrder.objects.create(
                            competition=competition,
                            event=event,
                            athlete_competition=ac,
                            order=idx,
                            lane_number=1,
                            heat_number=1,
                            status=status,
                            started_at=timezone.now() if status=='current' else None
                        )

                messages.success(request, f"Run order generated for {event.name}")

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
                AthleteEventNote.objects.update_or_create(
                    athlete_competition=ac,
                    event=event,
                    note_type=request.POST.get('note_type'),
                    defaults={'note_value': request.POST.get('note_value')}
                )
                messages.success(request, f"Note saved for {ac.athlete.user.get_full_name()}")

            elif action == 'complete_current_lifter':
                current = get_object_or_404(CompetitionRunOrder, pk=request.POST.get('run_order_id'), status='current')
                lane = current.lane_number
                score = request.POST.get('score_value')
                current.status, current.completed_at = 'completed', timezone.now()
                current.save()
                if score:
                    result, created = Result.objects.get_or_create(
                        athlete_competition=current.athlete_competition,
                        event=event,
                        defaults={'value': score}
                    )
                    if not created and result.value != score:
                        result.value = score
                        result.save()
                    calculate_points_and_rankings(competition.pk, event.pk)

                pending = CompetitionRunOrder.objects.filter(
                    competition=competition, event=event, lane_number=lane, status='pending'
                ).order_by('heat_number','order')
                if pending:
                    next_ro = pending[0]
                    next_ro.status, next_ro.started_at = 'current', timezone.now()
                    next_ro.save()
                    if len(pending) > 1:
                        on_deck = pending[1]
                        messages.success(
                            request,
                            f"Lift completed in Lane {lane}. {current.athlete_competition.athlete.user.get_full_name()} "
                            f"marked as completed{' with score '+score if score else ''}. "
                            f"{next_ro.athlete_competition.athlete.user.get_full_name()} is now current. "
                            f"{on_deck.athlete_competition.athlete.user.get_full_name()} is on deck."
                        )
                    else:
                        messages.success(
                            request,
                            f"Lift completed in Lane {lane}. {current.athlete_competition.athlete.user.get_full_name()} "
                            f"marked as completed{' with score '+score if score else ''}. No more lifters in lane {lane}."
                        )
                else:
                    messages.success(
                        request,
                        f"Lift completed in Lane {lane}. {current.athlete_competition.athlete.user.get_full_name()} "
                        f"marked as completed{' with score '+score if score else ''}. No more lifters in lane {lane}."
                    )

            elif action == 'reactivate_lifter':
                comp_ro = get_object_or_404(CompetitionRunOrder, pk=request.POST.get('run_order_id'), status='completed')
                comp_ro.status, comp_ro.completed_at = 'pending', None
                comp_ro.save()
                messages.success(
                    request,
                    f"{comp_ro.athlete_competition.athlete.user.get_full_name()} reactivated in Lane {comp_ro.lane_number}."
                )

        return redirect('competitions:competition_run_order', competition_pk=competition.pk, event_pk=event.pk)