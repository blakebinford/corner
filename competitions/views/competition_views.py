import math
from datetime import date
from collections import defaultdict


from django.utils.timezone import now
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import HttpResponseRedirect, HttpResponseForbidden
from django.shortcuts import redirect, get_object_or_404, render
from django.urls import reverse_lazy, reverse
from django.views import generic, View
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import TemplateView

from competitions.views.utility_views import haversine_distance
from competitions.models import Competition, AthleteCompetition, EventImplement, ZipCode, WeightClass
from competitions.forms import CompetitionForm, CompetitionFilter

def home(request):
    upcoming_competitions = Competition.objects.filter(status='upcoming')
    return render(request, 'home.html', {'upcoming_competitions': upcoming_competitions})

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

class CompetitionCreateView(LoginRequiredMixin, generic.CreateView):
    """
    View for creating a new competition.
    """
    model = Competition
    form_class = CompetitionForm
    template_name = 'competitions/competition_form.html'

    def form_valid(self, form):
        """
        Handles competition creation, assigns the organizer, and sets the initial status.
        """
        form.instance.organizer = self.request.user  # Assign current user as organizer
        competition = form.save(commit=False)

        # Set default scoring system
        competition.scoring_system = 'strongman'

        # Determine initial competition status
        today = date.today()
        if competition.comp_date > today:
            competition.status = 'upcoming'
        elif competition.comp_date < today:
            competition.status = 'completed'

        competition.save()  # Save competition to generate an ID

        # Handle many-to-many relationships
        if form.cleaned_data.get('tags'):
            competition.tags.set(form.cleaned_data['tags'])
        if form.cleaned_data.get('allowed_divisions'):
            competition.allowed_divisions.set(form.cleaned_data['allowed_divisions'])

        # Update status based on capacity
        signed_up_count = AthleteCompetition.objects.filter(
            competition=competition,
            signed_up=True
        ).count()

        if signed_up_count >= competition.capacity:
            competition.status = 'full'
        elif signed_up_count >= 0.9 * competition.capacity:
            competition.status = 'limited'

        competition.save()  # Save updated status

        return HttpResponseRedirect(reverse('competitions:assign_weight_classes', kwargs={'pk': competition.pk}))

    def form_invalid(self, form):
        """
        Debugging output for form validation errors.
        """
        print("Form is invalid")
        print(form.errors)  # Print form errors for debugging
        return super().form_invalid(form)

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

class CompetitionDetailView(generic.DetailView):
    """
    Displays detailed information about a competition, including divisions, weight classes, and events.
    """
    model = Competition
    template_name = 'competitions/competition_detail.html'
    context_object_name = 'competition'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        competition = self.get_object()

        # Check if the user is signed up for this competition
        if self.request.user.is_authenticated:
            context['is_signed_up'] = AthleteCompetition.objects.filter(
                competition=competition,
                athlete__user=self.request.user
            ).exists()

        # Initialize data structures
        division_tables = {}
        has_male_events = False
        has_female_events = False

        # Retrieve divisions and associated weight classes for this competition
        divisions = competition.allowed_divisions.all()

        for division in divisions:
            division_tables[division.name] = []

            # Get weight classes specifically for this division
            weight_classes = WeightClass.objects.filter(division=division)

            for weight_class in weight_classes:
                row = {
                    'weight_class': weight_class,
                    'gender': weight_class.gender
                }

                # Track if male or female rows exist
                if weight_class.gender == 'Male':
                    has_male_events = True
                elif weight_class.gender == 'Female':
                    has_female_events = True

                # Populate event details within the row
                for event in competition.events.all():
                    event_implements = EventImplement.objects.filter(
                        event=event,
                        division=division,
                        weight_class=weight_class
                    ).order_by('implement_order')

                    implement_data = []
                    for implement in event_implements:
                        implement_info = f"{implement.weight} {implement.weight_unit}"
                        if event.has_multiple_implements and implement.implement_name:
                            implement_info = f"{implement.implement_name} - {implement_info}"
                        implement_data.append(implement_info)

                    # Store implement data in the row
                    row[event.name] = ", ".join(implement_data) if implement_data else "N/A"

                # Append row to the division table
                division_tables[division.name].append(row)

        # Add context variables for the template
        context['division_tables'] = division_tables
        context['events'] = competition.events.all().order_by('order')  # Ensure events are ordered
        context['has_male_events'] = has_male_events
        context['has_female_events'] = has_female_events

        return context

class ManageCompetitionView(TemplateView):
    """
    View for managing a competition, including athlete lists, events, and statistics.
    """
    template_name = 'competitions/manage_competition.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        competition_pk = self.kwargs['competition_pk']
        competition = get_object_or_404(Competition, pk=competition_pk)

        # Fetch weight classes linked to divisions in this competition
        weight_classes = WeightClass.objects.filter(division__competition=competition)
        context["weight_classes"] = weight_classes

        # Add competition, athletes, and events
        context['competition'] = competition
        context['athletes'] = (
            AthleteCompetition.objects
            .filter(competition=competition)
            .select_related('division', 'weight_class')  # ✅ Optimized query
        )
        context['events'] = competition.events.all()

        # T-shirt size summary
        allowed_sizes = {size.size: 0 for size in competition.allowed_tshirt_sizes.all()}
        tshirt_counts = (
            AthleteCompetition.objects.filter(competition=competition, tshirt_size__isnull=False)
            .values('tshirt_size__size')
            .annotate(count=Count('tshirt_size'))
        )

        for entry in tshirt_counts:
            size = entry['tshirt_size__size']
            count = entry['count']
            if size in allowed_sizes:
                allowed_sizes[size] = count

        context['tshirt_summary'] = allowed_sizes

        # Optimized athlete summary by division & weight class
        athlete_summary = defaultdict(int)

        # Fetch all athlete counts in one query
        athlete_counts = (
            AthleteCompetition.objects
            .filter(competition=competition, division__isnull=False, weight_class__isnull=False)
            .values('division_id', 'weight_class_id')
            .annotate(count=Count('id'))
        )

        for entry in athlete_counts:
            key = (entry['division_id'], entry['weight_class_id'])
            athlete_summary[key] = entry['count']

        # Ensure all division & weight class combos exist in summary
        for division in competition.allowed_divisions.all():
            for weight_class in weight_classes.filter(division=division):
                key = (division.id, weight_class.id)
                athlete_summary.setdefault(key, 0)  # Avoids overwriting existing counts

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

class ArchivedCompetitionListView(generic.ListView):
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


from django.views.generic import FormView
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.db import transaction

from accounts.models import User, AthleteProfile
from competitions.models import Competition, AthleteCompetition
from competitions.forms import OrlandosStrongestSignupForm

class OrlandosStrongestSignupView(FormView):
    template_name = 'competitions/orlandos_strongest_signup.html'
    form_class = OrlandosStrongestSignupForm

    def get_competition(self):
        return get_object_or_404(Competition, name__iexact='ORLANDO\'S STRONGEST (MEN, WOMEN, AND TEENS)')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['competition'] = self.get_competition()
        return kwargs

    @transaction.atomic
    def form_valid(self, form):
        data = form.cleaned_data
        comp = self.get_competition()

        # 1) Create User
        user = User(
            username=data['email'],  # using email as username
            email=data['email'],
            first_name=data['first_name'],
            last_name=data['last_name'],
            role='athlete'
        )
        user.set_password(data['password1'])
        user.save()

        # 2) Create AthleteProfile
        profile = AthleteProfile.objects.create(
            user=user,
            gender=data['gender'],
            date_of_birth=data['date_of_birth'],
            home_gym=data.get('home_gym'),
            team_name=data.get('team_name'),
            coach=data.get('coach'),
            height=data.get('height'),
            weight=data.get('weight'),
            city=data.get('city'),
            state=data.get('state'),
        )

        # 3) Sign up for competition
        AthleteCompetition.objects.create(
            athlete=profile,
            competition=comp,
            division=data['division'],
            weight_class=data['weight_class'],
            tshirt_size=data.get('tshirt_size'),
            signed_up=True,
            registration_status='complete',
            payment_status='pending'
        )

        messages.success(self.request, "Your account has been created and you’re signed up for Orlando’s Strongest!")
        return redirect('competitions:competition_detail', pk=comp.pk)