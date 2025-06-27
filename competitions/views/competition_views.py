import math
from datetime import date
from collections import defaultdict
from decimal import Decimal

import stripe
from django.utils.timezone import now
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import HttpResponseRedirect, HttpResponseForbidden
from django.shortcuts import redirect, get_object_or_404, render
from django.urls import reverse_lazy, reverse
from django.views import generic, View
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import TemplateView

from accounts.models import OrganizerProfile
from competitions.mixins import CompetitionAccessMixin, competition_permission_required
from competitions.utils import get_onboarding_status
from competitions.views.utility_views import haversine_distance
from competitions.models import Competition, AthleteCompetition, EventImplement, ZipCode, WeightClass, Event
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

        return HttpResponseRedirect(reverse('competitions:manage_competition', kwargs={'competition_pk': competition.pk}))

    def form_invalid(self, form):
        """
        Debugging output for form validation errors.
        """
        print("Form is invalid")
        print(form.errors)  # Print form errors for debugging
        return super().form_invalid(form)

class CompetitionUpdateView(CompetitionAccessMixin, LoginRequiredMixin, UserPassesTestMixin, generic.UpdateView):
    model = Competition
    form_class = CompetitionForm
    template_name = 'competitions/competition_form.html'
    access_level = 'full'

    def test_func(self):
        return self.competition.has_full_access(self.request.user)

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


class ManageCompetitionView(LoginRequiredMixin, CompetitionAccessMixin, TemplateView):
    """
    View for managing a competition, including athlete lists, events, and statistics.
    """
    template_name = 'competitions/manage_competition.html'
    access_level = 'full'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        competition_pk = self.kwargs['competition_pk']
        competition = get_object_or_404(Competition, pk=competition_pk)

        # ——— ONBOARDING CHECKLIST FLAGS ———
        context['onboarding_status'] = get_onboarding_status(competition)
        organizer_profile = get_object_or_404(OrganizerProfile, user=competition.organizer)
        if competition.organizer == self.request.user:
            organizer_profile = get_object_or_404(OrganizerProfile, user=self.request.user)
            context['show_intro'] = organizer_profile.first_time_setup
        else:
            context['show_intro'] = False

        # Get the organizer's Stripe account ID
        organizer_profile = get_object_or_404(OrganizerProfile, user=competition.organizer)
        stripe_account_id = organizer_profile.stripe_account_id

        # Fetch weight classes linked to divisions in this competition
        weight_classes = WeightClass.objects.filter(division__competition=competition)
        context["weight_classes"] = weight_classes

        # Core objects
        context['competition'] = competition
        context['athletes'] = AthleteCompetition.objects.filter(
            competition=competition
        ).select_related('division', 'weight_class')
        context['events'] = competition.events.all()

        # ——— PAYMENT / INCOME STATS ———
        # only those who have fully paid
        paid_athletes = AthleteCompetition.objects.filter(
            competition=competition,
            payment_status="paid"
        )
        paid_count = paid_athletes.count()
        signup_price = competition.signup_price or Decimal("0.00")
        total_paid = signup_price * paid_count

        # platform fee is 10%, so organizer nets 90%
        organizer_income = (total_paid * Decimal("0.90")).quantize(Decimal("0.01"))

        # Fetch balance from Stripe connected account
        try:
            stripe_balance = stripe.Balance.retrieve(stripe_account=stripe_account_id)
            stripe_available = sum(item['amount'] for item in stripe_balance['available'])
            stripe_pending = sum(item['amount'] for item in stripe_balance['pending'])
            total_stripe_balance = (stripe_available + stripe_pending) / 100  # Convert from cents to dollars
        except stripe.error.StripeError as e:
            total_stripe_balance = 0  # Handle Stripe errors gracefully

        context.update({
            "paid_count": paid_count,
            "total_paid": total_paid,
            "organizer_income": organizer_income,
            "total_stripe_balance": total_stripe_balance,
        })

        # ——— T-SHIRT SUMMARY ———
        allowed_sizes = {sz.size: 0 for sz in competition.allowed_tshirt_sizes.all()}
        tshirt_counts = (
            AthleteCompetition.objects
            .filter(competition=competition, tshirt_size__isnull=False)
            .values('tshirt_size__size')
            .annotate(count=Count('id'))
        )
        for entry in tshirt_counts:
            size = entry['tshirt_size__size']
            count = entry['count']
            if size in allowed_sizes:
                allowed_sizes[size] = count
        context['tshirt_summary'] = allowed_sizes

        # ——— ATHLETE SUMMARY BY DIVISION & WEIGHT CLASS ———
        athlete_summary = defaultdict(int)
        athlete_counts = (
            AthleteCompetition.objects
            .filter(competition=competition, division__isnull=False, weight_class__isnull=False)
            .values('division_id', 'weight_class_id')
            .annotate(count=Count('id'))
        )
        for entry in athlete_counts:
            key = (entry['division_id'], entry['weight_class_id'])
            athlete_summary[key] = entry['count']

        # ensure zero‐counts for any combo that didn’t appear above
        for division in competition.allowed_divisions.all():
            for wc in weight_classes.filter(division=division):
                athlete_summary.setdefault((division.id, wc.id), 0)

        context['athlete_summary'] = athlete_summary

        return context

@login_required
def set_current_event(request, competition_pk, event_pk):
    competition = get_object_or_404(Competition, pk=competition_pk)
    event = get_object_or_404(Event, pk=event_pk, competition=competition)

    if request.user != competition.organizer:
        messages.error(request, "You are not authorized to change the current event.")
        return redirect('competitions:competition_run_order', competition_pk=competition.pk, event_pk=event.pk)

    competition.set_current_event(event)

    return redirect('competitions:competition_run_order', competition_pk=competition.pk, event_pk=event.pk)

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
@competition_permission_required('full')
def toggle_publish_status(request, pk):
    competition = get_object_or_404(Competition, pk=pk)

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
