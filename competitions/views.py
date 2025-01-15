import math
from datetime import date
from collections import defaultdict
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageEnhance, ImageFilter
from PIL.ImageChops import overlay

from django.utils import timezone
from django.contrib import messages
from django.core.mail import send_mass_mail
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Prefetch
from django.forms import modelformset_factory
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy, reverse
from django.views import generic
from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from channels.layers import get_channel_layer
from django.views.generic import FormView, CreateView, UpdateView, TemplateView
from django_filters import FilterSet, CharFilter, ChoiceFilter

from accounts.models import AthleteProfile, WeightClass
from .models import Competition, EventOrder, AthleteCompetition, DivisionWeightClass, Result, CommentatorNote, Sponsor, \
    Event, EventBase, EventImplement, ZipCode
from .forms import CompetitionForm, EventForm, AthleteCompetitionForm, EventImplementFormSet, ResultForm, \
    SponsorLogoForm, EventImplementForm, CompetitionFilter, SponsorEditForm
from chat.models import OrganizerChatMessage, OrganizerChatRoom

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

class CompetitionListView(generic.ListView):
    model = Competition
    template_name = 'competitions/competition_list.html'
    context_object_name = 'competitions'

    def get_queryset(self):
        queryset = super().get_queryset()

        # Apply filtering using the filterset
        self.filterset = CompetitionFilter(self.request.GET, queryset=queryset)

        # Return the filtered and sorted queryset
        return self.filterset.qs

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
            for competition in context['competitions']:
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
            context['competitions'] = sorted(context['competitions'], key=lambda x: x.distance)

        # Add filterset to context
        queryset = super().get_queryset()
        self.filterset = CompetitionFilter(self.request.GET, queryset=queryset)
        context['filterset'] = self.filterset

        return context

class CompetitionDetailView(generic.DetailView):
    model = Competition
    template_name = 'competitions/competition_detail.html'
    context_object_name = 'competition'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        competition = self.get_object()

        if self.request.user.is_authenticated:
            context['is_signed_up'] = AthleteCompetition.objects.filter(
                competition=competition,
                athlete__user=self.request.user  # Traverse AthleteProfile to User
            ).exists()

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
        # Fetch and organize event implement data
        division_tables = {}
        for event in competition.events.all():
            event_implements = event.implements.select_related('division_weight_class').all()
            for implement in event_implements:
                division = implement.division_weight_class.division.name
                weight_class_obj = implement.division_weight_class.weight_class  # Use the full WeightClass object here
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

                # Add the event weight
                row[event.name] = f"{implement.weight} {implement.weight_unit}"
        context['division_tables'] = division_tables
        context['events'] = competition.events.all()
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
        return redirect(self.success_url)

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
            self.save_m2m()

        return competition

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
    success_url = reverse_lazy('competitions:competition_list')

    def test_func(self):
        competition = self.get_object()
        return self.request.user == competition.organizer

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_update'] = True
        return context

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
        upcoming_competitions = all_competitions.filter(comp_date__gte=timezone.now()).order_by('comp_date')
        completed_competitions = all_competitions.filter(comp_date__lt=timezone.now()).order_by('-comp_date')

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
        return context


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

class EventCreateView(CreateView):
    model = Event
    form_class = EventForm
    template_name = 'competitions/event_form.html'  # Create this template

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        competition_pk = self.kwargs['competition_pk']
        competition = get_object_or_404(Competition, pk=competition_pk)
        context['competition'] = competition
        context['is_update'] = False

        allowed_division_weight_classes = DivisionWeightClass.objects.filter(
            division__in=competition.allowed_divisions.all(),
            weight_class__in=competition.allowed_weight_classes.all()
        ).order_by('division__name', 'gender', 'weight_class__name')

        # Create the formset using modelformset_factory
        EventImplementFormSet = modelformset_factory(
            EventImplement,
            form=EventImplementForm,
            extra=len(allowed_division_weight_classes)  # Set extra to the number of allowed DivisionWeightClass objects
        )

        # Get the allowed division_weight_class IDs for this competition
        allowed_division_weight_class_ids = DivisionWeightClass.objects.filter(
            division__in=competition.allowed_divisions.all(),
            weight_class__in=competition.allowed_weight_classes.all()
        ).values_list('id', flat=True)

        if self.request.POST:
            context['formset'] = EventImplementFormSet(
                self.request.POST,  # Update the existing formset with POST data
            )
        else:
            # Create initial data for the formset
            initial_data = [{'division_weight_class': dwc.id} for dwc in allowed_division_weight_classes]
            context['formset'] = EventImplementFormSet(
                queryset=EventImplement.objects.none(),  # Use an empty queryset to avoid extra forms
                initial=initial_data
            )

        context['event_bases'] = EventBase.objects.all().order_by('name')
        return context

    def save_event_implements(request, event):
        implements = []
        for key, value in request.POST.items():
            if key.startswith('implement_name_'):
                parts = key.split('_')
                weight_class_id = int(parts[2])
                implement_order = int(parts[3])

                implement_name = value
                weight = request.POST.get(f'weight_{weight_class_id}_{implement_order}')
                weight_unit = request.POST.get(f'weight_unit_{weight_class_id}_{implement_order}')

                implements.append(EventImplement(
                    event=event,
                    division_weight_class_id=weight_class_id,
                    implement_name=implement_name,
                    implement_order=implement_order,
                    weight=weight,
                    weight_unit=weight_unit
                ))
        EventImplement.objects.bulk_create(implements)

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']
        competition = context['competition']

        if formset.is_valid() and form.is_valid():  # Check if both form and formset are valid
            event = form.save()
            for form in formset:
                if form.cleaned_data:  # Check if the form has data
                    event_implement = form.save(commit=False)
                    event_implement.event = event  # Explicitly set the event
                    event_implement.save()

            formset.save()

            EventOrder.objects.create(competition=competition, event=event)
            return redirect('competitions:competition_detail', pk=competition.pk)
        else:

            return redirect('competitions:competition_detail', pk=competition.pk)

class EventUpdateView(LoginRequiredMixin, UserPassesTestMixin, generic.UpdateView):
    model = Event
    form_class = EventForm
    template_name = 'competitions/event_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        event = self.get_object()
        event_order = get_object_or_404(EventOrder, event=event)
        competition = event_order.competition
        context['competition'] = competition
        context['is_update'] = True

        queryset = EventImplement.objects.filter(event=event)
        print("Queryset for Formset:", queryset)

        allowed_division_weight_classes = DivisionWeightClass.objects.filter(
            division__in=competition.allowed_divisions.all(),
            weight_class__in=competition.allowed_weight_classes.all()
        )

        EventImplementFormSet = modelformset_factory(
            EventImplement,
            form=EventImplementForm,
            extra=0,
            can_delete=True  # Allow deletion of existing objects if needed
        )

        if self.request.POST:
            context['formset'] = EventImplementFormSet(self.request.POST, queryset=queryset)
        else:
            context['formset'] = EventImplementFormSet(queryset=queryset)

        return context

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']

        print("Formset Data:", self.request.POST)  # Print the POST data
        print("Formset Errors Before Validation:", formset.errors)  # Print errors before validation

        if formset.is_valid() and form.is_valid():
            event = form.save()
            for form in formset:
                if form.cleaned_data:
                    event_implement = form.save(commit=False)
                    event_implement.event = event
                    event_implement.save()

            formset.save()
            return redirect(self.get_success_url())
        else:
            print("Formset Errors:", formset.errors)
            return self.form_invalid(form)

    def get_success_url(self):
        event_order = get_object_or_404(EventOrder, event=self.object)
        return reverse_lazy('competitions:competition_detail', kwargs={'pk': event_order.competition.pk})

    def test_func(self):
        event = self.get_object()
        event_order = get_object_or_404(EventOrder, event=event)
        return self.request.user == event_order.competition.organizer

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

    def get_form(self, *args, **kwargs):
        form = super().get_form(*args, **kwargs)
        competition = get_object_or_404(Competition, pk=self.kwargs['competition_pk'])

        # Filter the fields based on the competition
        form.fields['weight_class'].queryset = competition.allowed_weight_classes.all()
        form.fields['division'].queryset = competition.allowed_divisions.all()
        return form

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
        key = (result.athlete_competition.athlete.gender,
               result.athlete_competition.division,
               result.athlete_competition.weight_class)
        grouped_results[key].append(result)

    # 2. Sort and assign points within each group
    for key, group_results in grouped_results.items():
        # Sort results based on event type within the group
        event_type = event_order.event.weight_type
        if event_type == 'time':
            # For time-based events, extract time and sort in ascending order
            group_results.sort(key=lambda x: extract_time_from_result(x))  # Use helper function
        elif event_type in ('reps', 'distance', 'height', 'max'):
            # For other event types, sort by value in ascending order (assuming lower is better)
            group_results.sort(key=lambda x: int(x.value) if x.value and x.value.isdigit() else float('-inf'))
        else:
            # For unknown event types, sort by value in descending order (you might need to adjust this)
            group_results.sort(key=lambda x: -int(x.value) if x.value and x.value.isdigit() else float('-inf'))

        # Assign points within the group, handling ties
        num_competitors = len(group_results)
        current_points = -1  # Start from 0, so first place gets 1 point
        tied_results = []
        for i, result in enumerate(group_results):
            if tied_results and result.value == tied_results[-1].value:
                tied_results.append(result)  # Add to tied group
            else:
                # Process previous tied group (if any)
                if len(tied_results) > 1:
                    # Calculate average points for tied results
                    total_tied_points = sum(range(current_points + 1, current_points + len(tied_results) + 1))  # Add 1 to start from the correct point value
                    avg_points = total_tied_points / len(tied_results)
                    for tied_result in tied_results:
                        tied_result.points_earned = avg_points
                        tied_result.save()
                    current_points += len(tied_results)  # Increment points for the next position after the tie
                else:
                    # Not a tie, assign points normally
                    if tied_results:  # Assign points to the single result
                        tied_results[0].points_earned = current_points + 1  # Add 1 to get the correct point value
                        tied_results[0].save()
                    current_points += 1  # Increment for next position

                tied_results = [result]  # Start a new tied group

        # Handle any remaining tied results at the end of the group
        if len(tied_results) > 1:
            total_tied_points = sum(range(current_points + 1, current_points + len(tied_results) + 1))  # Add 1 to start from the correct point value
            avg_points = total_tied_points / len(tied_results)
            for tied_result in tied_results:
                tied_result.points_earned = avg_points
                tied_result.save()
            current_points += len(tied_results)  # Increment points after the tie
        else:
            if tied_results:
                tied_results[0].points_earned = current_points + 1  # Add 1 to get the correct point value
                tied_results[0].save()

    # After calculating points for the event, update overall rankings
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
            (subject, message, 'no-reply@comppodium.com', [email]) for email in athlete_emails
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
            event_rank = ordinal(result.points_earned)
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
    with open(output_path, "rb") as img:
        return HttpResponse(img.read(), content_type="image/png")
