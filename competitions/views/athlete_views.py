from django.contrib import messages
from django.core.mail import send_mail
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy, reverse
from django.views import generic
from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin


from accounts.models import User, AthleteProfile
from competitions.models import Competition, AthleteCompetition, TshirtSize, Division, WeightClass
from competitions.forms import AthleteCompetitionForm, AthleteProfileForm, ManualAthleteAddForm


def athlete_profile(request, athlete_id):
    athlete = get_object_or_404(AthleteProfile, pk=athlete_id)
    competition_history = AthleteCompetition.objects.filter(athlete=athlete)
    print(athlete.__dict__)
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
        return context

    def get_competition(self):
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

        competition = form.instance.competition
        if competition.athletecompetition_set.count() >= competition.capacity:
            return render(self.request, 'competitions/registration_full.html', {'competition': competition})

        athlete_competition = form.save()

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

            from django.core.mail import send_mail
            send_mail(
                subject=email_subject,
                message=email_message,
                from_email="noreply@example.com",
                recipient_list=[competition.organizer.email],
                fail_silently=False,
            )

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


