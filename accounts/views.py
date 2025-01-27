from django.contrib.sites.shortcuts import get_current_site
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views import generic
from django.urls import reverse_lazy
from django.contrib.auth.decorators import login_required
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.template.loader import render_to_string
from django.core.mail import EmailMessage
from competitions.models import Competition, AthleteCompetition, EventOrder, Result
from .forms import CustomUserCreationForm, OrganizerProfileForm, AthleteProfileUpdateForm, \
    UserUpdateForm
from .tokens import account_activation_token
from .models import AthleteProfile, OrganizerProfile, User, WeightClass
from django.contrib import messages
import re

class SignUpView(generic.CreateView):
    """
    View for user registration.
    """
    form_class = CustomUserCreationForm
    success_url = reverse_lazy('login')
    template_name = 'registration/signup.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        competition = get_object_or_404(Competition, pk=self.kwargs['competition_pk'])
        kwargs['competition'] = competition
        return kwargs

    def form_valid(self, form):
        """
        If the form is valid, save the user and create their profile based on their role.
        """
        user = form.save(commit=False)
        user.is_active = False  # Deactivate account until email is verified
        user.save()

        # Send email verification
        current_site = get_current_site(self.request)
        mail_subject = 'Activate your account.'
        message = render_to_string('registration/acc_active_email.html', {
            'user': user,
            'domain': 'comppodium.onrender.com',
            'uid': urlsafe_base64_encode(force_bytes(user.pk)),
            'token': account_activation_token.make_token(user),
        })
        to_email = form.cleaned_data.get('email')

        email = EmailMessage(
            mail_subject, message, to=[to_email]
        )
        email.send()
        if user.role == 'athlete':
            AthleteProfile.objects.create(user=user)  # Create AthleteProfile here
        elif user.role == 'organizer':
            OrganizerProfile.objects.create(user=user)

        return render(self.request, 'registration/email_verification_sent.html')

    def get(self, request, *args, **kwargs):
        """
        Handles GET requests and instantiates a blank version of the form.
        """
        self.object = None  # Initialize self.object to None for GET requests
        form = self.get_form()
        return self.render_to_response(self.get_context_data(form=form))


class UserUpdateView(generic.UpdateView):
    """
    View for updating user profiles.
    """
    form_class = UserUpdateForm
    success_url = reverse_lazy('home')  # Replace 'home' with your desired URL
    template_name = 'registration/update_profile.html'

    def get_object(self):
        return self.request.user


@login_required
def update_profile(request):
    """
    View for updating the user's athlete profile and user information.
    """
    if request.method == 'POST':
        # Ensure the user has an AthleteProfile before creating the forms
        if not hasattr(request.user, 'athlete_profile'):
            AthleteProfile.objects.create(user=request.user)

        # Pass `request.FILES` for handling file uploads
        user_form = UserUpdateForm(request.POST, request.FILES, instance=request.user)
        profile_form = AthleteProfileUpdateForm(request.POST, request.FILES, instance=request.user.athlete_profile)

        if user_form.is_valid() and profile_form.is_valid():
            instagram_name = user_form.cleaned_data.get('instagram_name')
            x_name = user_form.cleaned_data.get('x_name')
            facebook_name = user_form.cleaned_data.get('facebook_name')

            if instagram_name and not re.match(r'^[\w.]+$', instagram_name):
                messages.error(request,
                               'Invalid Instagram username. Only letters, numbers, underscores, and periods are allowed.')
            elif x_name and not re.match(r'^[a-zA-Z][\w_]*$', x_name):
                messages.error(request,
                               'Invalid X username. Only letters, numbers, and underscores are allowed, and it cannot start with a number.')
            elif facebook_name and not re.match(r'^[\w.]+$', facebook_name):
                messages.error(request,
                               'Invalid Facebook username. Only letters, numbers, and periods are allowed.')
            else:
                user_form.save()
                profile_form.save()
                messages.success(request, 'Your profile has been updated successfully!')
            return redirect('accounts:profile_update')  # Redirect to the profile page
        else:
            messages.error(request, 'Error updating profile. Please check the form.')
    else:
        # Ensure the user has an AthleteProfile before creating the forms
        if not hasattr(request.user, 'athlete_profile'):
            AthleteProfile.objects.create(user=request.user)

        user_form = UserUpdateForm(instance=request.user)
        profile_form = AthleteProfileUpdateForm(instance=request.user.athlete_profile)

    context = {
        'user_form': user_form,
        'profile_form': profile_form,
        'user': request.user,
    }

    return render(request, 'registration/update_profile.html', context)



class OrganizerProfileUpdateView(generic.UpdateView):
    """
    View for updating organizer profiles.
    """
    form_class = OrganizerProfileForm
    template_name = 'registration/update_organizer_profile.html'
    success_url = reverse_lazy('home')  # Replace 'home' with your desired URL

    def get_object(self):
        return self.request.user.organizer_profile


def activate(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and account_activation_token.check_token(user, token):
        if user.is_active:
            # User already activated
            return render(request, 'registration/acc_active_already.html')
        else:
            # Activate the user
            user.is_active = True
            user.email_verified = True
            user.save()
            messages.success(request, 'Your account has been successfully activated!')
            return redirect('accounts:login')  # Redirect to login page
    else:
        # Invalid or already used token
        return render(request, 'registration/acc_active_invalid.html')

def get_weight_classes(request):
    federation_id = request.GET.get('federation_id')
    weight_classes = WeightClass.objects.filter(federation=federation_id)
    weight_class_data = [{'id': wc.id, 'name': str(wc)} for wc in weight_classes]
    return JsonResponse({'weight_classes': weight_class_data})
