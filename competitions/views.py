import base64
import csv
import json
import math
from datetime import date
from collections import defaultdict, Counter
from io import BytesIO
import os
from urllib import response

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageEnhance, ImageFilter
from PIL.ImageChops import overlay
from itertools import groupby

from django.utils import timezone
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.timezone import now
from django.contrib import messages
from django.core.mail import send_mass_mail, send_mail
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Prefetch, Count, Max
from django.forms import modelformset_factory, formset_factory
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect, Http404, HttpResponseForbidden, \
    HttpResponseBadRequest
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy, reverse
from django.views import generic, View
from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from channels.layers import get_channel_layer
from django.views.generic import FormView, CreateView, UpdateView, TemplateView
from django_filters import FilterSet, CharFilter, ChoiceFilter

from accounts.models import User, AthleteProfile, WeightClass, Division
from chat.models import OrganizerChatRoom, OrganizerChatMessage
from .models import Competition, EventOrder, AthleteCompetition, DivisionWeightClass, Result, CommentatorNote, Sponsor, \
    Event, EventBase, EventImplement, ZipCode, TshirtSize
from .forms import CompetitionForm, AthleteCompetitionForm, EventImplementFormSet, ResultForm, \
    SponsorLogoForm, EventImplementForm, CompetitionFilter, SponsorEditForm, EditWeightClassesForm, \
    ManualAthleteAddForm, AthleteProfileForm, CombineWeightClassesForm, EventCreationForm
from accounts.forms import CustomDivisionForm, CustomWeightClassForm
from asgiref.sync import async_to_sync

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

class CompetitionListView(generic.ListView):
    model = Competition
    template_name = 'competitions/competition_list.html'
    context_object_name = 'competitions'

    def get_queryset(self):
        # Get competitions with today's date or in the future
        queryset = super().get_queryset().filter(comp_date__gte=now().date())

        # Apply filtering using the filterset
        self.filterset = CompetitionFilter(self.request.GET, queryset=queryset)
        filtered_queryset = self.filterset.qs

        # Sort the filtered queryset by the closest competition date
        return filtered_queryset.order_by('comp_date')

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
            competitions = context['competitions']
            for competition in competitions:
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
            context['competitions'] = sorted(competitions, key=lambda x: x.distance)

        # Add filterset to context
        self.filterset = CompetitionFilter(self.request.GET, queryset=super().get_queryset())
        context['filterset'] = self.filterset

        return context

class ArchivedCompetitionListView(ListView):
    model = Competition
    template_name = 'competitions/archived_competition_list.html'
    context_object_name = 'competitions'

    def get_queryset(self):
        # Get competitions prior to today's date
        queryset = super().get_queryset().filter(comp_date__lt=now().date())

        # Apply filtering using the filterset
        self.filterset = CompetitionFilter(self.request.GET, queryset=queryset)
        filtered_queryset = self.filterset.qs

        # Sort by the most recent past competitions
        return filtered_queryset.order_by('-comp_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        zip_code = self.request.GET.get('zip_code')

        if zip_code:
            try:
                user_zip_code = ZipCode.objects.get(zip_code=zip_code)
            except ZipCode.DoesNotExist:
                print(f"Invalid zip code provided: {zip_code}")  # Log the invalid zip code
                return context

            competitions = context['competitions']
            for competition in competitions:
                try:
                    competition_zip_code = ZipCode.objects.get(zip_code=competition.zip_code)
                    distance = haversine_distance(
                        user_zip_code.latitude, user_zip_code.longitude,
                        competition_zip_code.latitude, competition_zip_code.longitude
                    )
                    competition.distance = distance
                except ZipCode.DoesNotExist:
                    print(f"Missing zip code for competition: {competition.pk}")  # Log the missing zip code
                    competition.distance = float('inf')  # Set a high distance for sorting

            # Sort the competitions by distance
            context['competitions'] = sorted(competitions, key=lambda x: x.distance)

        # Add filterset to context
        self.filterset = CompetitionFilter(self.request.GET, queryset=super().get_queryset())
        context['filterset'] = self.filterset

        return context


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

class CompetitionDetailView(generic.DetailView):
    model = Competition
    template_name = 'competitions/competition_detail.html'
    context_object_name = 'competition'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        competition = self.get_object()

        # Existing logic for signed-up users
        if self.request.user.is_authenticated:
            context['is_signed_up'] = AthleteCompetition.objects.filter(
                competition=competition,
                athlete__user=self.request.user
            ).exists()

        # Organizing event implement data
        division_tables = {}
        has_male_events = False
        has_female_events = False

        for event in competition.events.all():
            event_implements = event.implements.select_related('division_weight_class').order_by('implement_order')
            for implement in event_implements:
                division = implement.division_weight_class.division.name
                weight_class_obj = implement.division_weight_class.weight_class
                gender = implement.division_weight_class.gender

                if division not in division_tables:
                    division_tables[division] = []

                # Find or create a row for the weight class and gender
                row = next(
                    (r for r in division_tables[division]
                     if r['weight_class'] == weight_class_obj and r['gender'] == gender),
                    None
                )
                if not row:
                    row = {'weight_class': weight_class_obj, 'gender': gender}
                    division_tables[division].append(row)

                    # Track if male or female rows exist
                    if gender == 'Male':
                        has_male_events = True
                    elif gender == 'Female':
                        has_female_events = True

                # Add implement data
                implements_data = row.get(event.name, [])
                implement_info = (
                    f"{implement.implement_name} - {implement.weight} {implement.weight_unit}"
                    if event.has_multiple_implements else f"{implement.weight} {implement.weight_unit}"
                )
                if implement_info not in implements_data:
                    implements_data.append(implement_info)

                row[event.name] = implements_data

        # Format implement data for template
        for division, rows in division_tables.items():
            for row in rows:
                for event in competition.events.all():
                    if event.name in row:
                        row[event.name] = '<br>'.join(row[event.name])

        context['division_tables'] = division_tables
        context['events'] = competition.events.all()
        context['has_male_events'] = has_male_events
        context['has_female_events'] = has_female_events
        return context




class AthleteCheckInView(View):
    template_name = 'competitions/checkin_athletes.html'

    def get(self, request, competition_pk):
        competition = get_object_or_404(Competition, pk=competition_pk)

        athletes = AthleteCompetition.objects.filter(competition=competition)\
            .select_related('athlete__user', 'division', 'weight_class', 'tshirt_size')\
            .order_by('athlete__gender', 'weight_class__name', 'weight_class__weight_d', 'athlete__user__last_name', 'athlete__user__first_name')

        grouped_athletes = {}
        for gender, gender_group in groupby(athletes, key=lambda x: x.athlete.gender):
            grouped_athletes[gender] = {}
            for weight_class, weight_class_group in groupby(gender_group, key=lambda x: x.weight_class):
                grouped_athletes[gender][weight_class] = list(weight_class_group)

        return render(request, self.template_name, {
            'competition': competition,
            'grouped_athletes': grouped_athletes,
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
                    athlete.weigh_in = weight_in  # Save the weigh-in value
                athlete.save()

            messages.success(request, "Athlete check-in data saved successfully.")
        elif "finalize_check_in" in request.POST:
            for athlete in athletes:
                showed_up = request.POST.get(f"showed_up_{athlete.pk}") == "on"
                if not showed_up:
                    athlete.delete()
                    messages.success(request, "Athletes who did not check in have been removed.")


        return redirect('competitions:manage_competition', competition.pk)

@login_required
def toggle_publish_status(request, pk):
    competition = get_object_or_404(Competition, pk=pk, organizer=request.user)

    if competition.approval_status != 'approved':
        messages.error(request, "This competition has not been approved yet.")
        return redirect('competitions:manage_competition', competition_pk=pk)

    competition.publication_status = 'published' if competition.publication_status == 'unpublished' else 'unpublished'
    competition.save()

    messages.success(request, f"Competition has been {'published' if competition.publication_status == 'published' else 'unpublished'}.")
    return redirect('competitions:manage_competition', competition_pk=pk)

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
            for weight_class in competition.allowed_weight_classes.all():
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
        if weight_class.weight_d == 'u':
            return f"{weight_class.weight_d}{weight_class.name}"
        elif weight_class.weight_d == '+':
            return f"{weight_class.name}{weight_class.weight_d}"
        return str(weight_class.name)

    @staticmethod
    def get_division_display(division):
        """
        Returns the formatted division name with capitalization.
        """
        return division.name.capitalize()

class CompetitionCreateView(LoginRequiredMixin, generic.CreateView):
    model = Competition
    form_class = CompetitionForm
    template_name = 'competitions/competition_form.html'

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

        return HttpResponseRedirect(reverse('competitions:assign_weight_classes', kwargs={'pk': competition.pk}))

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


        return competition

@method_decorator(login_required, name="dispatch")
class AssignWeightClassesView(View):
    template_name = "competitions/assign_weight_classes.html"

    def get(self, request, *args, **kwargs):
        competition_id = self.kwargs.get("pk")
        competition = get_object_or_404(Competition, pk=competition_id)

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
        competition_id = self.kwargs.get("pk")
        competition = get_object_or_404(Competition, pk=competition_id)

        # Clear all existing DivisionWeightClass entries for this competition
        DivisionWeightClass.objects.filter(division__in=competition.allowed_divisions.all()).delete()

        for key, weight_class_ids in request.POST.lists():
            if key.startswith("division_"):
                division_id = key.replace("division_", "")
                division = get_object_or_404(Division, pk=division_id)

                for weight_class_id in weight_class_ids:
                    weight_class = get_object_or_404(WeightClass, pk=weight_class_id)
                    DivisionWeightClass.objects.create(
                        division=division, weight_class=weight_class, gender=weight_class.gender
                    )

        messages.success(
            request, "Weight classes were successfully assigned to the competition!"
        )
        return redirect("competitions:manage_competition", competition_pk=competition.pk)

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

class CustomWeightClassCreateView(CreateView):
    model = WeightClass
    form_class = CustomWeightClassForm
    template_name = "competitions/custom_weight_class_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        competition = get_object_or_404(Competition, pk=self.kwargs['competition_pk'])
        kwargs['competition'] = competition
        return kwargs

    def form_valid(self, form):
        # Save the WeightClass instance
        weight_class = form.save(commit=False)
        competition = get_object_or_404(Competition, pk=self.kwargs['competition_pk'])
        weight_class.competition = competition
        weight_class.federation = competition.federation
        weight_class.is_custom = True
        weight_class.save()

        # Get the division ID and create the DivisionWeightClass
        division_id = form.cleaned_data.get('division')  # This should now be the ID
        division = get_object_or_404(Division,
                                     pk=division_id.id)  # Ensure it uses .id or directly access it as an object
        DivisionWeightClass.objects.create(
            division=division,
            weight_class=weight_class,
            gender=weight_class.gender
        )
        print(f"Associated WeightClass '{weight_class}' with Division '{division}'")

        return redirect('competitions:manage_competition', competition_pk=self.kwargs['competition_pk'])

class SponsorEditView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = 'competitions/sponsor_edit.html'

    def test_func(self):
        competition_pk = self.kwargs['competition_pk']
        competition = get_object_or_404(Competition, pk=competition_pk)
        return self.request.user == competition.organizer

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        competition_pk = self.kwargs['competition_pk']
        competition = get_object_or_404(Competition, pk=competition_pk)
        context['competition'] = competition

        SponsorFormSet = modelformset_factory(
            Sponsor,
            form=SponsorEditForm,
            extra=0,
            can_delete=True,
        )

        context['formset'] = SponsorFormSet(queryset=competition.sponsor_logos.all())
        context['upload_url'] = reverse_lazy('competitions:sponsor_logo_upload',
                                             kwargs={'competition_pk': competition_pk})
        return context

    def post(self, request, *args, **kwargs):
        competition_pk = self.kwargs['competition_pk']
        competition = get_object_or_404(Competition, pk=competition_pk)
        SponsorFormSet = modelformset_factory(
            Sponsor,
            form=SponsorEditForm,
            extra=0,
            can_delete=True,
        )

        formset = SponsorFormSet(request.POST, request.FILES, queryset=competition.sponsor_logos.all())

        if formset.is_valid():
            # Save formset changes
            sponsors = formset.save(commit=False)
            for sponsor in sponsors:
                display_order_field = f"display_order_{sponsor.pk}"
                if display_order_field in request.POST:
                    sponsor.display_order = int(request.POST[display_order_field])
                sponsor.save()

                # Handle deletions
            for deleted_sponsor in formset.deleted_objects:
                deleted_sponsor.delete()

            return redirect('competitions:competition_detail', pk=competition_pk)
        else:
            print("Formset errors:", formset.errors)
            return self.render_to_response(self.get_context_data(formset=formset))

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

    def test_func(self):
        competition = self.get_object()
        return self.request.user == competition.organizer

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_update'] = True
        return context

    def get_initial(self):
        initial = super().get_initial()
        competition = self.get_object()

        # Fetch the pre-selected T-shirt sizes
        selected_sizes = [tshirt_size.size for tshirt_size in competition.allowed_tshirt_sizes.all()]
        initial['allowed_tshirt_sizes'] = selected_sizes
        print("Initial T-shirt Sizes:", initial['allowed_tshirt_sizes'])  # Debugging output
        return initial

    def get_form(self, *args, **kwargs):
        form = super().get_form(*args, **kwargs)
        print("Competition Instance in Form:", form.instance)  # Debugging output
        return form

    def get_success_url(self):
        # Redirect to the competition detail page
        return reverse('competitions:competition_detail', kwargs={'pk': self.object.pk})


class CompetitionDeleteView(LoginRequiredMixin, UserPassesTestMixin, generic.DeleteView):
    model = Competition
    template_name = 'competitions/competition_confirm_delete.html'
    success_url = reverse_lazy('competitions:competition_list')

    def test_func(self):
        competition = self.get_object()
        return self.request.user == competition.organizer

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

class ManageCompetitionView(TemplateView):
    template_name = 'competitions/manage_competition.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        competition_pk = self.kwargs['competition_pk']
        competition = get_object_or_404(Competition, pk=competition_pk)

        context['competition'] = competition
        context['athletes'] = AthleteCompetition.objects.filter(competition=competition)
        context['events'] = EventOrder.objects.filter(competition=competition).select_related('event')
        context['today'] = date.today()

        # T-shirt size summary
        allowed_sizes = {size.size: 0 for size in competition.allowed_tshirt_sizes.all()}
        tshirt_counts = AthleteCompetition.objects.filter(
            competition=competition, tshirt_size__isnull=False
        ).values('tshirt_size__size').annotate(count=Count('tshirt_size'))

        for entry in tshirt_counts:
            size = entry['tshirt_size__size']
            count = entry['count']
            if size in allowed_sizes:
                allowed_sizes[size] = count

        context['tshirt_summary'] = allowed_sizes

        athlete_summary = defaultdict(int)

        for athlete in competition.athletecompetition_set.all():
            if athlete.division and athlete.weight_class:
                key = (athlete.division.id, athlete.weight_class.id)
                athlete_summary[key] += 1

        # Add all division and weight class combos with zero counts
        for division in competition.allowed_divisions.all():
            for weight_class in competition.allowed_weight_classes.all():
                key = (division.id, weight_class.id)
                if key not in athlete_summary:
                    athlete_summary[key] = 0

        context['athlete_summary'] = athlete_summary
        print("Athlete Summary:", athlete_summary)
        return context


class CompleteCompetitionView(LoginRequiredMixin, View):
    def post(self, request, competition_pk):
        competition = get_object_or_404(Competition, pk=competition_pk)

        # Ensure the user is the organizer
        if competition.organizer != request.user:
            return HttpResponseForbidden("You are not authorized to complete this competition.")

        # Check if the competition date is valid for completion
        if competition.comp_date <= date.today():
            competition.status = 'completed'
            competition.save()
            messages.success(request, f"The competition '{competition.name}' has been marked as completed.")
        else:
            messages.error(request, "You can only complete the competition on or after its scheduled date.")

        return redirect('competitions:manage_competition', competition_pk=competition.pk)


class AthleteListView(ListView):
    model = AthleteCompetition
    template_name = 'competitions/athlete_list.html'
    context_object_name = 'athletes'

    def get_queryset(self):
        competition_pk = self.kwargs['competition_pk']
        competition = get_object_or_404(Competition, pk=competition_pk)
        return AthleteCompetition.objects.filter(competition=competition)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        competition_pk = self.kwargs['competition_pk']
        context['competition'] = get_object_or_404(Competition, pk=competition_pk)
        return context



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

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['competition'] = self.get_competition()
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['competition'] = self.get_competition()
        return context

    def get_competition(self):
        """
        Helper method to retrieve the competition instance based on the URL parameter.
        """
        return get_object_or_404(Competition, pk=self.kwargs['competition_pk'])

    def form_valid(self, form):
        form.instance.athlete = self.request.user.athlete_profile
        form.instance.competition = self.get_competition()

        if AthleteCompetition.objects.filter(
                athlete=self.request.user.athlete_profile,
                competition=form.instance.competition
        ).exists():
            messages.warning(self.request, "You are already registered for this competition.")
            return redirect('competitions:competition_detail', pk=form.instance.competition.pk)

        # Check if competition is full
        competition = form.instance.competition
        if competition.athletecompetition_set.count() >= competition.capacity:
            return render(self.request, 'competitions/registration_full.html', {'competition': competition})

        # Save the AthleteCompetition object
        athlete_competition = form.save()

        # Send email to the organizer if notifications are enabled
        if competition.email_notifications:
            athlete = athlete_competition.athlete
            athlete_user = athlete.user
            email_subject = f"🎉 New Athlete Registration for {competition.name}!"
            email_message = (
                f"Hello {competition.organizer.first_name},\n\n"
                f"Exciting news! A new athlete has just signed up for {competition.name}.\n\n"
                f"🏋️ Athlete Details:\n"
                f"  - Name: {athlete_user.get_full_name()}\n"
                f"  - Email: {athlete_user.email}\n"
                f"  - Gender: {athlete.gender}\n"
                f"  - Weight Class: {athlete_competition.weight_class}\n"
                f"  - Division: {athlete_competition.division}\n"
                f"  - Registration Date: {athlete_competition.registration_date.strftime('%B %d, %Y')}\n"
                f"  - T-shirt Size: {athlete_competition.tshirt_size or 'N/A'}\n\n"
                f"Let’s make this competition an unforgettable experience for all athletes!\n\n"
                f"Stay strong,\n"
                f"The Atlas Competition Team\n"
            )

            send_mail(
                subject=email_subject,
                message=email_message,
                from_email="noreply@example.com",
                recipient_list=[competition.organizer.email],
                fail_silently=False,
            )

        # Render success page
        return render(self.request, 'competitions/registration_success.html', {
            'competition': competition,
            'athlete_competition': athlete_competition
        })


class AthleteCompetitionUpdateView(LoginRequiredMixin, UserPassesTestMixin, generic.UpdateView):
    model = AthleteCompetition
    form_class = AthleteCompetitionForm
    template_name = 'competitions/athletecompetition_form.html'

    def get_success_url(self):
        return reverse_lazy('competitions:manage_competition', kwargs={'competition_pk': self.object.competition.pk})

    def test_func(self):
        registration = self.get_object()
        return (
            self.request.user == registration.athlete.user or
            self.request.user == registration.competition.organizer
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['competition'] = self.object.competition
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request,
                         f"Athlete info for {self.object.athlete.user.get_full_name()} has been successfully updated.")
        return response


class AddAthleteManuallyView(LoginRequiredMixin, generic.FormView):
    template_name = "competitions/add_athlete.html"
    form_class = ManualAthleteAddForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        competition = get_object_or_404(Competition, pk=self.kwargs['competition_pk'])
        kwargs['competition'] = competition
        return kwargs

    def form_valid(self, form):
        competition = get_object_or_404(Competition, pk=self.kwargs['competition_pk'])
        email = form.cleaned_data['email']

        user = User.objects.filter(email=email).first()

        if user:
            athlete_profile, _ = AthleteProfile.objects.get_or_create(user=user)
            AthleteCompetition.objects.create(
                athlete=athlete_profile,
                competition=competition,
                division=form.cleaned_data['division'],
                weight_class=form.cleaned_data['weight_class'],
                tshirt_size=form.cleaned_data.get('tshirt_size')
            )
            messages.success(self.request, "Athlete successfully added!")
            return redirect('competitions:manage_competition', competition_pk=competition.pk)
        else:
            # Store data in the session
            self.request.session['athlete_email'] = email
            self.request.session['division_id'] = form.cleaned_data['division'].id
            self.request.session['weight_class_id'] = form.cleaned_data['weight_class'].id
            self.request.session['tshirt_size_id'] = (
                form.cleaned_data['tshirt_size'].id if form.cleaned_data.get('tshirt_size') else None
            )
            return redirect('competitions:create_athlete_profile', competition_pk=competition.pk)

class CreateAthleteProfileView(LoginRequiredMixin, generic.CreateView):
    template_name = 'competitions/create_athlete_profile.html'
    form_class = AthleteProfileForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        competition = get_object_or_404(Competition, pk=self.kwargs['competition_pk'])
        context['competition'] = competition
        return context

    def form_valid(self, form):
        competition = get_object_or_404(Competition, pk=self.kwargs['competition_pk'])
        athlete_email = self.request.session.get('athlete_email')
        division_id = self.request.session.get('division_id')
        weight_class_id = self.request.session.get('weight_class_id')
        tshirt_size_id = self.request.session.get('tshirt_size_id')

        # Ensure required session data exists
        if not athlete_email or not division_id or not weight_class_id:
            messages.error(self.request, "Error: Missing data from the previous step. Please try again.")
            return redirect('competitions:add_athlete', competition_pk=competition.pk)

        # Get or create user
        user = User.objects.filter(email=athlete_email).first()
        if not user:
            user = User.objects.create_user(
                email=athlete_email,
                first_name=form.cleaned_data['first_name'],
                last_name=form.cleaned_data['last_name'],
                username=athlete_email.split('@')[0]
            )

        # Save athlete profile
        athlete_profile = form.save(commit=False)
        athlete_profile.user = user
        athlete_profile.save()

        # Link athlete to the competition
        AthleteCompetition.objects.create(
            athlete=athlete_profile,
            competition=competition,
            division=Division.objects.get(id=division_id),
            weight_class=WeightClass.objects.get(id=weight_class_id),
            tshirt_size=TshirtSize.objects.get(id=tshirt_size_id) if tshirt_size_id else None
        )

        # Clear session data
        self.request.session.pop('athlete_email', None)
        self.request.session.pop('division_id', None)
        self.request.session.pop('weight_class_id', None)
        self.request.session.pop('tshirt_size_id', None)

        messages.success(self.request, "Athlete profile successfully created and linked to the competition!")
        return redirect('competitions:manage_competition', competition_pk=competition.pk)

from django import forms
from competitions.models import Division, DivisionWeightClass

import logging

logger = logging.getLogger(__name__)

class CombineWeightClassesView(LoginRequiredMixin, UserPassesTestMixin, generic.FormView):
    template_name = "competitions/combine_weight_classes.html"
    form_class = CombineWeightClassesForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        competition = get_object_or_404(Competition, pk=self.kwargs['competition_pk'])
        kwargs['competition'] = competition
        print("Form kwargs initialized:", kwargs)
        return kwargs

    def form_valid(self, form):
        print("Form is valid")
        competition = get_object_or_404(Competition, pk=self.kwargs['competition_pk'])
        division = form.cleaned_data['division']
        from_dwc = form.cleaned_data['from_weight_class']
        to_dwc = form.cleaned_data['to_weight_class']

        print(f"Division: {division}")
        print(f"From Weight Class: {from_dwc}")
        print(f"To Weight Class: {to_dwc}")

        if from_dwc == to_dwc:
            print("Cannot combine the same weight class")
            messages.error(self.request, "You cannot combine a weight class with itself.")
            return redirect('competitions:combine_weight_classes', competition_pk=competition.pk)

        try:
            competition.allowed_weight_classes.remove(from_dwc.weight_class)
            competition.allowed_weight_classes.add(to_dwc.weight_class)
            from_dwc.delete()
            print("Combination successful")
            messages.success(
                self.request,
                f"Successfully combined {from_dwc.weight_class} into {to_dwc.weight_class}."
            )
        except Exception as e:
            print(f"Error during combination: {e}")
            messages.error(self.request, "An error occurred. Please try again.")

        return redirect('competitions:manage_competition', competition_pk=competition.pk)

    def form_invalid(self, form):
        print("Form is invalid")
        print("Errors:", form.errors)
        return super().form_invalid(form)

    def test_func(self):
        competition = get_object_or_404(Competition, pk=self.kwargs['competition_pk'])
        print(f"Test function called. Organizer: {competition.organizer}")
        return self.request.user == competition.organizer

def get_division_weight_classes(request, division_id):
    division = get_object_or_404(Division, id=division_id)
    weight_classes = DivisionWeightClass.objects.filter(division=division)
    return JsonResponse(
        [{'id': dwc.id, 'text': str(dwc.weight_class)} for dwc in weight_classes],
        safe=False
    )
class AthleteCompetitionDeleteView(LoginRequiredMixin, UserPassesTestMixin, generic.DeleteView):
    model = AthleteCompetition
    template_name = 'competitions/athletecompetition_confirm_delete.html'

    def get_success_url(self):
        return reverse_lazy('competitions:competition_detail', kwargs={'pk': self.object.competition.pk})

    def test_func(self):
        registration = self.get_object()
        return self.request.user == registration.athlete.user  # Check if the logged-in user is the athlete


def create_event(request, competition_pk):
    """
    Handles the creation of an event linked to a competition.
    """
    competition = get_object_or_404(Competition, pk=competition_pk)

    if request.method == 'POST':
        form = EventCreationForm(request.POST)

        if form.is_valid():
            # Save the event without committing to the database
            event = form.save(commit=False)

            # Save the event to generate an ID
            event.save()

            max_order = EventOrder.objects.filter(competition=competition).aggregate(Max('order'))['order__max']
            next_order = (max_order or 0) + 1

            # Create the EventOrder entry to link the competition and event
            EventOrder.objects.create(competition=competition, event=event, order=next_order)

            # Link the competition to the event
            event.competitions.add(competition)

            # Save the many-to-many relationship
            form.save_m2m()

            # Redirect to the implement form for the created event
            return redirect('competitions:assign_implements', event_pk=event.pk)
    else:
        form = EventCreationForm()

    return render(request, 'competitions/event_form.html', {
        'form': form,
        'competition': competition,
        'action_url': 'competitions:create_event',  # Dynamically set the form action
        'action_kwargs': {'competition_pk': competition.pk},  # Pass competition_pk for creation
    })


def assign_implements(request, event_pk):
    event = get_object_or_404(Event, pk=event_pk)
    competition = event.competitions.first()

    if not competition:
        return HttpResponseBadRequest("This event is not associated with any competition.")

    # Get allowed DivisionWeightClasses
    allowed_division_weight_classes = DivisionWeightClass.objects.filter(
        division__in=competition.allowed_divisions.all()
    )

    if competition.allowed_weight_classes.exists():
        allowed_division_weight_classes = allowed_division_weight_classes.filter(
            weight_class__in=competition.allowed_weight_classes.all()
        )
    print("Allowed DivisionWeightClasses:", allowed_division_weight_classes)
    # Prepare initial data for the formset
    initial_data = []
    existing_implements = EventImplement.objects.filter(event=event)

    if event.has_multiple_implements:
        for dwc in allowed_division_weight_classes:
            for implement_order in range(1, event.number_of_implements + 1):
                existing_implement = existing_implements.filter(
                    division_weight_class=dwc, implement_order=implement_order
                ).first()
                if existing_implement:
                    # Use existing data
                    initial_data.append({
                        'division_weight_class': existing_implement.division_weight_class.id,
                        'implement_name': existing_implement.implement_name,
                        'implement_order': existing_implement.implement_order,
                        'weight': existing_implement.weight,
                        'weight_unit': existing_implement.weight_unit,
                    })
                    print("Initial Data:", initial_data)
                else:
                    # New implement data
                    initial_data.append({
                        'division_weight_class': dwc.id,
                        'implement_order': implement_order,
                    })
                    print("Initial Data:", initial_data)
    else:
        for dwc in allowed_division_weight_classes:
            existing_implement = existing_implements.filter(
                division_weight_class=dwc, implement_order=1
            ).first()
            if existing_implement:
                # Use existing data
                initial_data.append({
                    'division_weight_class': existing_implement.division_weight_class.id,
                    'implement_name': existing_implement.implement_name,
                    'implement_order': existing_implement.implement_order,
                    'weight': existing_implement.weight,
                    'weight_unit': existing_implement.weight_unit,
                })
            else:
                # New implement data
                initial_data.append({
                    'division_weight_class': dwc.id,
                    'implement_order': 1,
                })

    # Create a formset using formset_factory instead of modelformset_factory
    EventImplementFormSet = formset_factory(EventImplementForm, extra=0)

    if request.method == 'POST':
        formset = EventImplementFormSet(request.POST)
        if formset.is_valid():
            # Delete all existing implements for the event to avoid duplicates
            existing_implements.delete()

            # Save the formset data
            for form in formset:
                instance = form.save(commit=False)
                instance.event = event
                instance.save()

            return redirect('competitions:competition_detail', pk=competition.pk)
        else:
            print("Formset Errors:", formset.errors)
    else:
        formset = EventImplementFormSet(initial=initial_data)

    return render(request, 'competitions/event_implements_form.html', {
        'formset': formset,
        'event': event,
    })


def update_event(request, event_pk):
    """
    Handles the update of an existing event.
    """
    event = get_object_or_404(Event, pk=event_pk)
    competition = event.competitions.first()  # Assuming the event belongs to one competition

    if request.method == 'POST':
        form = EventCreationForm(request.POST, instance=event)  # Pass the instance to the form
        if form.is_valid():
            form.save()  # Save updates to the existing event
            return redirect('competitions:assign_implements', event_pk=event.pk)
    else:
        form = EventCreationForm(instance=event)  # Pass the instance to the form

    return render(request, 'competitions/event_form.html', {
        'form': form,
        'competition': competition,
        'event': event,
        'action_url': 'competitions:update_event',  # Dynamically set the form action
        'action_kwargs': {'event_pk': event.pk},  # Pass event_pk for editing
    })

def home(request):
    upcoming_competitions = Competition.objects.filter(status='upcoming')
    return render(request, 'home.html', {'upcoming_competitions': upcoming_competitions})

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
        key = (
            result.athlete_competition.athlete.gender,
            result.athlete_competition.division,
            result.athlete_competition.weight_class,
        )
        grouped_results[key].append(result)

    # 2. Sort and assign points and ranks within each group
    for key, group_results in grouped_results.items():
        # Sort results based on event type within the group
        event_type = event_order.event.weight_type
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

        # Process all results
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

        # Handle any remaining tied results
        if len(tied_results) > 1:
            for tied_result in tied_results:
                tied_result.event_rank = current_rank
                tied_result.save()
        elif tied_results:
            tied_results[0].event_rank = current_rank
            tied_results[0].save()

    # Update overall rankings after calculating points for the event
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

@login_required
def event_list(request, competition_pk):
    competition = get_object_or_404(Competition, pk=competition_pk)
    event_orders = EventOrder.objects.filter(competition=competition)
    return render(request, 'competitions/event_list.html', {
        'competition': competition,
        'event_orders': event_orders,
    })


@login_required
def event_scores(request, competition_pk, eventorder_pk):
    competition = get_object_or_404(Competition, pk=competition_pk)
    event_order = get_object_or_404(EventOrder, pk=eventorder_pk)
    athlete_competitions = AthleteCompetition.objects.filter(competition=competition)

    # Group athletes by gender, then by division, then by weight class
    grouped_athletes = defaultdict(lambda: defaultdict(list))
    for athlete_competition in athlete_competitions:
        gender = athlete_competition.athlete.gender
        division = athlete_competition.division.name if athlete_competition.division else "Unknown Division"
        weight_class = athlete_competition.weight_class

        grouped_athletes[gender][division].append({
            'athlete_competition': athlete_competition,
            'weight_class': {
                'name': weight_class.name if weight_class else "Unknown Weight Class",
                'weight_d': weight_class.weight_d if weight_class else None,
            },
            'result': Result.objects.get_or_create(
                athlete_competition=athlete_competition,
                event_order=event_order
            )[0],
        })

    # Sort grouped athletes
    grouped_athletes = {
        gender: {
            division: sorted(athletes, key=lambda x: x['weight_class']['name'])
            for division, athletes in divisions.items()
        }
        for gender, divisions in sorted(grouped_athletes.items())
    }

    if request.method == 'POST':
        for key, value in request.POST.items():
            if key.startswith('result_'):
                try:
                    athlete_competition_id, event_order_id = map(int, key.replace('result_', '').split('_'))
                    result = Result.objects.get(
                        athlete_competition_id=athlete_competition_id,
                        event_order_id=event_order_id
                    )
                    result.value = value
                    result.save()
                except (ValueError, Result.DoesNotExist):
                    pass
        calculate_points_and_rankings(competition.pk, eventorder_pk)

        # Add a success message
        messages.success(request, "Scores updated successfully!")
        return redirect('competitions:event_scores', competition_pk=competition_pk, eventorder_pk=eventorder_pk)

    return render(request, 'competitions/event_score_update.html', {
        'competition': competition,
        'event_order': event_order,
        'grouped_athletes': grouped_athletes,
    })

def athlete_profile(request, athlete_id):
    athlete = get_object_or_404(AthleteProfile, pk=athlete_id)
    competition_history = AthleteCompetition.objects.filter(athlete=athlete)
    print(athlete.__dict__)
    context = {
        'athlete': athlete,
        'competition_history': competition_history
    }
    return render(request, 'registration/athlete_profile.html', context)

@login_required
def commentator_comp_card(request, competition_id):
    competition = get_object_or_404(Competition, pk=competition_id)

    # Check if the user is the organizer of this competition
    if not competition.organizer == request.user:
        return render(request, 'unauthorized.html')  # Replace 'unauthorized.html' with your unauthorized template

    # Get all event bases for the current competition
    current_event_bases = EventBase.objects.filter(
        event__competitions=competition
    ).distinct()

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
                event_order__event__event_base__in=current_event_bases
            )
            .select_related(
                'event_order__event__event_base',
                'event_order__event',
                'athlete_competition__competition'
            )
            .order_by('event_order__event__event_base__name', '-athlete_competition__competition__comp_date')
        )

        # Add `weight_type` to the past performances
        for result in past_performances:
            result.weight_type = result.event_order.event.weight_type

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

def get_weight_classes(request):
    federation_id = request.GET.get('federation_id')
    if not federation_id:
        return JsonResponse({'error': 'Federation ID is required'}, status=400)

    # Fetch weight classes for the selected federation
    weight_classes = WeightClass.objects.filter(federation_id=federation_id)
    weight_class_data = [{'id': wc.id, 'name': str(wc)} for wc in weight_classes]

    return JsonResponse({'weight_classes': weight_class_data})


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

def ordinal(n):
    """
    Convert an integer into its ordinal representation.
    E.g. 1 => '1st', 2 => '2nd', 3 => '3rd', etc.
    """
    try:
        n = int(n)
        if 10 <= n % 100 <= 20:
            suffix = "th"
        else:
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
        return f"{n}{suffix}"
    except (ValueError, TypeError):
        return "N/A"


def draw_gradient_text(draw, text, position, font, start_color, end_color):
    """
    Draws gradient text on the given ImageDraw object.

    :param draw: ImageDraw object to draw on
    :param text: Text string to render
    :param position: (x, y) starting position of the text
    :param font: Font object for the text
    :param start_color: RGB tuple for the start of the gradient (e.g., (255, 0, 0))
    :param end_color: RGB tuple for the end of the gradient (e.g., (150, 0, 0))
    """
    x, y = position

    # Calculate text width using textbbox
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]

    # Calculate gradient step for each pixel
    r_step = (end_color[0] - start_color[0]) / text_width
    g_step = (end_color[1] - start_color[1]) / text_width
    b_step = (end_color[2] - start_color[2]) / text_width

    for i, char in enumerate(text):
        char_width = draw.textbbox((0, 0), char, font=font)[2]  # Get individual character width
        r = int(start_color[0] + r_step * (x - position[0]))
        g = int(start_color[1] + g_step * (x - position[0]))
        b = int(start_color[2] + b_step * (x - position[0]))
        draw.text((x, y), char, font=font, fill=(r, g, b))
        x += char_width  # Move x position for the next character

def wrap_text(text, font, max_width):
    """Wrap text to fit within the specified width."""
    lines = []
    words = text.split()
    while words:
        line = words.pop(0)
        while words and font.getbbox(line + " " + words[0])[2] <= max_width:
            line += " " + words.pop(0)
        lines.append(line)
    return lines

def add_gradient_rectangle(draw, x, y, width, height, start_opacity, end_opacity, color):
    """
    Adds a gradient rectangle to the given canvas.
    :param draw: ImageDraw object
    :param x: X-coordinate of the top-left corner
    :param y: Y-coordinate of the top-left corner
    :param width: Width of the rectangle
    :param height: Height of the rectangle
    :param start_opacity: Starting opacity (0-255)
    :param end_opacity: Ending opacity (0-255)
    :param color: Base color of the gradient
    """
    for i in range(height):
        opacity = start_opacity + int((end_opacity - start_opacity) * (i / height))
        fill_color = (*color, opacity)
        draw.line([(x, y + i), (x + width, y + i)], fill=fill_color)


def competition_overlay(request, competition_pk, user_pk):
    from PIL import Image, ImageDraw, ImageFont, ImageOps

    # Fetch competition and athlete details
    competition = get_object_or_404(Competition, pk=competition_pk)
    athlete = get_object_or_404(AthleteProfile, user_id=user_pk)
    athlete_competition = AthleteCompetition.objects.filter(
        competition=competition, athlete=athlete
    ).first()
    athlete_rank = ordinal(athlete_competition.rank) if athlete_competition and athlete_competition.rank else "N/A"
    division = athlete_competition.division.name.upper() if athlete_competition else "N/A"
    weight_class_obj = athlete_competition.weight_class if athlete_competition else None
    athlete_results = athlete_competition.results.all() if athlete_competition else []

    # Process weight class
    weight_class = f"{weight_class_obj.weight_d}{weight_class_obj.name}" if weight_class_obj and weight_class_obj.weight_d == "u" else \
        f"{weight_class_obj.name}{weight_class_obj.weight_d}" if weight_class_obj else "N/A"

    # Fonts and paths
    profile_photo_path = athlete.user.profile_picture.path
    trophy_image_path = "competitions/static/competitions/images/trophy-xxl.png"
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    output_path = f"/tmp/overlay_{athlete.user.pk}_{competition.pk}.png"

    if request.method == "POST" and 'custom_photo' in request.FILES:
        custom_photo = request.FILES['custom_photo']
        temp_path = default_storage.save(f"tmp/{custom_photo.name}", ContentFile(custom_photo.read()))
        profile_photo_path = default_storage.path(temp_path)
    else:
        profile_photo_path = athlete.user.profile_picture.path  # Default to profile picture

    light_gray = "#d3dade"
    # Canvas setup
    # Canvas setup
    canvas_size = 1080  # Updated for a square canvas
    border_thickness = 50
    canvas = Image.new("RGBA", (canvas_size, canvas_size), light_gray)

    # Create dark background
    gradient = Image.new("RGBA", (canvas_size, canvas_size))
    draw_gradient = ImageDraw.Draw(gradient)
    for y in range(canvas_size):
        color = "black"
        draw_gradient.line([(0, y), (canvas_size, y)], fill=color)
    canvas = Image.alpha_composite(canvas, gradient)

    # Inner box setup
    inner_box_size = canvas_size - 2 * border_thickness
    inner_box_radius = 30  # Adjusted for rounded corners
    inner_box = Image.new("RGBA", (inner_box_size, inner_box_size), (255, 255, 255, 0))
    draw_inner_box = ImageDraw.Draw(inner_box)
    draw_inner_box.rounded_rectangle(
        [(0, 0), (inner_box_size, inner_box_size)],
        radius=inner_box_radius,
        fill="#242423",
    )
    inner_box_x, inner_box_y = border_thickness, border_thickness
    canvas.paste(inner_box, (inner_box_x, inner_box_y), inner_box)

    # Profile photo
    profile_photo_height = int(inner_box_size * 0.6)
    profile_photo = Image.open(profile_photo_path).convert("RGBA")
    profile_photo = ImageOps.fit(profile_photo, (inner_box_size, profile_photo_height), Image.Resampling.LANCZOS)

    # Create a mask for top-rounded corners
    mask = Image.new("L", profile_photo.size, 0)
    draw_mask = ImageDraw.Draw(mask)

    # Top-rounded rectangle
    corner_radius = 50  # Adjust corner radius as needed
    width, height = profile_photo.size

    # Apply rounded corners to profile photo
    mask = Image.new("L", profile_photo.size, 0)
    draw_mask = ImageDraw.Draw(mask)
    corner_radius = 30
    width, height = profile_photo.size
    draw_mask.rectangle([(0, corner_radius), (width, height)], fill=255)
    draw_mask.rectangle([(corner_radius, 0), (width - corner_radius, corner_radius)], fill=255)
    draw_mask.pieslice([(0, 0), (2 * corner_radius, 2 * corner_radius)], 180, 270, fill=255)
    draw_mask.pieslice([(width - 2 * corner_radius, 0), (width, 2 * corner_radius)], 270, 360, fill=255)
    profile_photo.putalpha(mask)
    canvas.paste(profile_photo, (inner_box_x, inner_box_y), profile_photo)

    # Fonts
    try:
        competition_font = ImageFont.truetype(font_path, 45)
        comp_font = ImageFont.truetype(font_path, 25)
        athlete_font = ImageFont.truetype(font_path, 80)
        division_font = ImageFont.truetype(font_path, 30)
        rank_font = ImageFont.truetype(font_path, 80)
        event_font = ImageFont.truetype(font_path, 30)
        place_font = ImageFont.truetype(font_path, 30)
    except OSError:
        raise OSError(f"Font file not found or invalid: {font_path}")

    draw = ImageDraw.Draw(canvas)

    # Add athlete's last name overlapping the photo
    last_name_text = athlete.user.last_name.upper()
    text_x = canvas_size // 2
    text_y = inner_box_y
    shadow_offset = 5

    draw.text((text_x + shadow_offset, text_y + shadow_offset), last_name_text, font=athlete_font, fill="black", anchor="mm")
    draw.text((text_x, text_y), last_name_text, font=athlete_font, fill="white", anchor="mm")



    # Add rounded rectangle at the bottom of the profile picture
    rectangle_width = int(inner_box_size * 0.8)
    rectangle_height = 150
    rectangle_x = inner_box_x + (inner_box_size - rectangle_width) // 2
    rectangle_y = inner_box_y + profile_photo_height - rectangle_height // 2
    draw.rounded_rectangle(
        [(rectangle_x, rectangle_y), (rectangle_x + rectangle_width, rectangle_y + rectangle_height)],
        radius=40,
        fill=(30, 30, 30),
        outline="white",
        width=5,
    )

    if athlete_rank == "1st":
        circle_fill_color = "#DED831" # Gold
    elif athlete_rank == "2nd":
        circle_fill_color = "#b3bcc7"   # Silver
    elif athlete_rank == "3rd":
        circle_fill_color = "#c47b3b"  # Bronze
    else:
        circle_fill_color = "#7EBDC2"  # Blue

    # Add circle with light blue fill extending outside the rectangle
    circle_radius = 100
    circle_x = rectangle_x + circle_radius - 20
    circle_y = rectangle_y + rectangle_height // 2
    draw.ellipse(
        [(circle_x - circle_radius, circle_y - circle_radius),
         (circle_x + circle_radius, circle_y + circle_radius)],
        fill=circle_fill_color,
    )

    # Add "Competition Corner" above the rounded rectangle
    competition_corner_text = "COMPETITION CORNER"
    text_x = canvas_size // 2.2
    text_y = rectangle_y - 15  # Position above the rounded rectangle with padding

    # Draw black outline for the text (thin stroke effect)
    outline_offset = 2
    for dx in [-outline_offset, 0, outline_offset]:
        for dy in [-outline_offset, 0, outline_offset]:
            if dx != 0 or dy != 0:  # Skip the center position
                draw.text(
                    (text_x + dx, text_y + dy),
                    competition_corner_text,
                    font=comp_font,
                    fill="black",
                    anchor="mm"
                )

    # Draw the main "Competition Corner" text in white
    draw.text(
        (text_x, text_y),
        competition_corner_text,
        font=comp_font,
        fill="white",
        anchor="mm"
    )


    # Add trophy image inside the circle
    trophy_image = Image.open(trophy_image_path).convert("RGBA")
    trophy_size = int(circle_radius * 1.5)
    trophy_image = ImageOps.fit(trophy_image, (trophy_size, trophy_size), Image.Resampling.LANCZOS)
    canvas.paste(trophy_image, (circle_x - trophy_size // 2, circle_y - trophy_size // 2), trophy_image)

    # Add "1st Place" in larger bold text
    text_x = circle_x + circle_radius + 40
    text_y = rectangle_y + rectangle_height // 2 - 15
    draw.text((text_x, text_y), f"{athlete_rank.upper()} PLACE", font=rank_font, fill="white", anchor="lm")

    # Add division and weight class in smaller text below
    draw.text((text_x, text_y + 50), f"{division} - {weight_class}", font=division_font, fill="white", anchor="lm")

    competition_name_text = competition.name.upper()
    competition_name_y = rectangle_y + rectangle_height + 60  # Position just below the rounded rectangle

    outline_offset = 2
    for dx in [-outline_offset, 0, outline_offset]:
        for dy in [-outline_offset, 0, outline_offset]:
            if dx != 0 or dy != 0:  # Skip the center position
                draw.text(
                    (canvas_size // 2 + dx, competition_name_y + dy),
                    competition_name_text,
                    font=competition_font,
                    fill="black",
                    anchor="mm"
                )

    # Draw the main competition name text in white
    draw.text(
        (canvas_size // 2, competition_name_y),
        competition_name_text,
        font=competition_font,
        fill="white",
        anchor="mm"
    )
    # Add light gray background for event performance
    event_bg_y = rectangle_y + rectangle_height + 85
    event_bg_y = competition_name_y + 75  # Add padding below the competition name
    event_bg_height = canvas_size - event_bg_y - 150

    # Add event performances in rows of 3
    cols = 5
    col_width = inner_box_size // cols
    row_height = 150
    event_x_start = inner_box_x
    event_y_start = event_bg_y

    num_events = len(athlete_results)

    for row in range((num_events + cols - 1) // cols):  # Calculate the number of rows
        # Events in the current row
        events_in_row = min(cols, num_events - row * cols)

        # Calculate horizontal offset to center the row
        row_offset = (inner_box_size - (events_in_row * col_width)) // 2

        for col in range(events_in_row):
            # Calculate the event's index and positions
            event_index = row * cols + col
            x_center = event_x_start + row_offset + col * col_width + col_width // 2
            y_top = event_y_start + row * row_height

            result = athlete_results[event_index]

            # Finishing place (above event name)
            event_rank = ordinal(result.event_rank)
            draw.text((x_center, y_top), event_rank, font=place_font, fill="#BB4430", anchor="mm")

            # Event name (below finishing place)
            event_name = result.event_order.event.name
            wrapped_event_name = wrap_text(event_name, event_font, col_width - 20)
            for line_index, line in enumerate(wrapped_event_name):
                draw.text((x_center, y_top + 50 + (line_index * 40)), line, font=event_font, fill="white", anchor="mm")

            # Draw vertical line separator (not for the last event in the row)
            if col < events_in_row - 1:
                line_x = event_x_start + row_offset + (col + 1) * col_width
                draw.line([(line_x, y_top - 20), (line_x, y_top + 100)], fill="gray", width=3)

    # Save the image
    canvas.save(output_path)
    if request.method == "POST" and 'custom_photo' in request.FILES:
        os.remove(profile_photo_path)

    return render(request, 'competitions/competition_overlay.html', {
        'competition': competition,
        'athlete': athlete,
    })

def competition_overlay_image(request, competition_pk, user_pk):

    competition = get_object_or_404(Competition, pk=competition_pk)
    athlete = get_object_or_404(AthleteProfile, user_id=user_pk)
    output_path = f"/tmp/overlay_{athlete.user.pk}_{competition.pk}.png"

    with open(output_path, "rb") as img:
        return HttpResponse(img.read(), content_type="image/png")