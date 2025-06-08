from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy, reverse
from django.views import generic
from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

from ComPodium.settings import base as settings
from accounts.models import User, AthleteProfile
from competitions.models import Competition, AthleteCompetition, TshirtSize, Division, WeightClass
from competitions.forms import AthleteCompetitionForm, AthleteProfileForm, ManualAthleteAddForm


from django.shortcuts import get_object_or_404, render
from accounts.models import AthleteProfile, User
from competitions.models import AthleteCompetition

def athlete_profile(request, athlete_id):
    # athlete_id is the User.pk
    athlete = get_object_or_404(AthleteProfile, user__pk=athlete_id)

    # Get competition history for this athlete profile
    competition_history = AthleteCompetition.objects.filter(athlete=athlete)

    # DEBUG: print who we got
    print(f"AthleteProfile for {athlete.user.username}: {athlete}")

    context = {
        'athlete': athlete,
        'competition_history': competition_history
    }
    return render(request, 'registration/athlete_profile.html', context)


class AthleteProfileUpdateView(LoginRequiredMixin, generic.UpdateView):
    model = AthleteProfile
    form_class = AthleteProfileForm
    template_name = 'competitions/create_athlete_profile.html'

    def get_object(self, queryset=None):
        return get_object_or_404(AthleteProfile, user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        competition = get_object_or_404(Competition, pk=self.kwargs['competition_pk'])
        context['competition'] = competition
        return context

    def form_valid(self, form):
        competition = get_object_or_404(Competition, pk=self.kwargs['competition_pk'])
        athlete_profile = form.save()
        messages.success(self.request, "Your athlete profile has been updated! You can now register for the competition.")
        return redirect('competitions:athletecompetition_create', competition_pk=competition.pk)

    def form_invalid(self, form):
        messages.error(self.request, "Please correct the errors below.")
        return super().form_invalid(form)


class AthleteCompetitionCreateView(LoginRequiredMixin, generic.CreateView):
    model = AthleteCompetition
    form_class = AthleteCompetitionForm
    template_name = 'competitions/registration_form.html'

    def get(self, request, *args, **kwargs):
        try:
            athlete_profile = request.user.athlete_profile
            print(f"User {request.user.username} has AthleteProfile: {athlete_profile}")
            if not athlete_profile.gender or athlete_profile.gender.strip() == '':
                print(f"User {request.user.username} has no gender set in AthleteProfile")
                messages.warning(
                    request,
                    "Please fill out your athlete profile before signing up for a competition."
                )
                return redirect(reverse('competitions:athlete_profile_update',
                                        kwargs={'competition_pk': self.kwargs['competition_pk']}))
        except AthleteProfile.DoesNotExist:
            print(f"User {request.user.username} has no AthleteProfile")
            messages.warning(
                request,
                "You need to create an athlete profile before you can sign up for a competition."
            )
            return redirect(reverse('competitions:athlete_profile_update',
                                    kwargs={'competition_pk': self.kwargs['competition_pk']}))

        print(f"Proceeding to registration form for {request.user.username}")
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        try:
            athlete_profile = request.user.athlete_profile
            print(f"POST: User {request.user.username} has AthleteProfile: {athlete_profile}")
            if not athlete_profile.gender or athlete_profile.gender.strip() == '':
                print(f"POST: User {request.user.username} has no gender set in AthleteProfile")
                messages.warning(
                    request,
                    "You need to set your gender in your athlete profile before you can sign up for a competition."
                )
                return redirect(reverse('competitions:athlete_profile_update',
                                        kwargs={'competition_pk': self.kwargs['competition_pk']}))
        except AthleteProfile.DoesNotExist:
            print(f"POST: User {request.user.username} has no AthleteProfile")
            messages.warning(
                request,
                "You need to create an athlete profile before you can sign up for a competition."
            )
            return redirect(reverse('competitions:athlete_profile_update',
                                    kwargs={'competition_pk': self.kwargs['competition_pk']}))

        return super().post(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['competition'] = self.get_competition()
        kwargs['request'] = self.request
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['competition'] = self.get_competition()
        context['stripe_pub_key'] = settings.STRIPE_PUBLISHABLE_KEY
        return context

    def get_competition(self):
        return get_object_or_404(Competition, pk=self.kwargs['competition_pk'])

    def form_valid(self, form):
        # 1) Pre-set athlete & competition
        form.instance.athlete     = self.request.user.athlete_profile
        form.instance.competition = self.get_competition()
        competition = form.instance.competition

        # 2) Duplicate check
        if AthleteCompetition.objects.filter(
            athlete=form.instance.athlete,
            competition=competition
        ).exists():
            messages.warning(
                self.request,
                "You are already registered for this competition."
            )
            return redirect(
                'competitions:competition_detail',
                pk=competition.pk
            )

        # 3) Capacity check
        if competition.athletecompetition_set.count() >= competition.capacity:
            return render(
                self.request,
                'competitions/registration_full.html',
                {'competition': competition}
            )

        # 4) Save in PENDING state
        athlete_competition = form.save(commit=False)
        athlete_competition.payment_status      = 'pending'
        athlete_competition.registration_status = 'pending'
        athlete_competition.signed_up           = False
        athlete_competition.save()

        # 5) Notify organizer by email
        if competition.email_notifications:
            athlete = athlete_competition.athlete
            athlete_user = athlete.user
            subject = f"🎉 New Athlete Registration for {competition.name}!"
            message = (
                f"Hello {competition.organizer.get_full_name()},\n\n"
                f"A new athlete has signed up for {competition.name}.\n\n"
                f"Name: {athlete_user.get_full_name()}\n"
                f"Email: {athlete_user.email}\n"
                f"Weight class: {athlete_competition.weight_class}\n"
                f"Division: {athlete_competition.division}\n"
                f"Date: {athlete_competition.registration_date:%B %d, %Y}\n\n"
                "They must now complete payment to finalize their registration."
            )
            send_mail(
                subject,
                message,
                from_email="no-reply@atlascompetition.com",
                recipient_list=[competition.organizer.email],
                fail_silently=False,
            )

        # 6) Redirect to payment page with both IDs
        return redirect(
            'competitions:start_checkout',
            competition_id=competition.pk,
            athlete_competition_id=athlete_competition.pk
        )

@login_required
def ajax_weight_classes(request):
    division_id = request.GET.get('division_id')
    wc_qs = WeightClass.objects.filter(division_id=division_id)
    # Apply athlete’s gender filter
    try:
        gender = request.user.athlete_profile.gender.strip().capitalize()
    except AthleteProfile.DoesNotExist:
        gender = None

    if gender in ('Male', 'Female'):
        wc_qs = wc_qs.filter(gender=gender)

    data = [{'id': wc.id, 'name': str(wc)} for wc in wc_qs.order_by('name')]
    return JsonResponse({'weight_classes': data})

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

class AthleteCompetitionDeleteView(LoginRequiredMixin, UserPassesTestMixin, generic.DeleteView):
    model = AthleteCompetition
    template_name = 'competitions/athletecompetition_confirm_delete.html'

    def get_success_url(self):
        return reverse_lazy('competitions:competition_detail', kwargs={'pk': self.object.competition.pk})

    def test_func(self):
        registration = self.get_object()
        return self.request.user == registration.athlete.user  # Check if the logged-in user is the athlete

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


