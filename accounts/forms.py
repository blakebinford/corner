
from django import forms
from django.shortcuts import redirect, render
from phonenumber_field.formfields import PhoneNumberField
from django.contrib import messages
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import User, AthleteProfile, OrganizerProfile

height_choices = []
feet = 4
inches = 11

while feet <= 7:
    while inches <= 12:
        if feet == 7 and inches == 3:
            break  # Stop at 7'2"

        # Format the display value with leading zero for inches < 10
        display_value = f"{feet}'{inches:02d}\""

        # Calculate total inches for the database value
        total_inches = (feet * 12) + inches

        height_choices.append((total_inches, display_value))

        inches += 1  # Increment inches here

        if inches == 12:  # Check if inches reached 12
            inches = 0  # Reset inches to 0
            feet += 1   # Increment feet

    feet += 1
    inches = 1  # Reset inches for the next foot

class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'role')

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("A user with that email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.email = self.cleaned_data['email']  # Save the email
        if commit:
            user.save()

            # Create AthleteProfile if the role is 'athlete'
            if user.role == 'athlete':
                AthleteProfile.objects.create(user=user)

        return user
    def save(self, commit=True):
        user = super().save(commit=False)  # Don't save the user yet
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        if commit:
            user.save()

            # Create AthleteProfile if the role is 'athlete'
            if user.role == 'athlete':
                AthleteProfile.objects.create(user=user)

        return user

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            # Create an AthleteProfile for the new user
            AthleteProfile.objects.create(user=user)
        return user

class UserUpdateForm(UserChangeForm):
    """Form to update user-related information."""

    class Meta:
        model = User
        fields = (
            'email',
            'first_name',
            'last_name',
            'profile_picture',
            'instagram_name',
            'x_name',
            'facebook_name',
        )
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs.update({'class': 'form-control'})
        for field_name in ['instagram_name', 'x_name', 'facebook_name']:
                self.fields[field_name].required = False

class AthleteProfileUpdateForm(forms.ModelForm):

    class Meta:
        model = AthleteProfile
        fields = [
            'gender',
            'nickname',
            'phone_number',
            'home_gym',
            'team_name',
            'coach',
            'height',
            'weight',
            'date_of_birth',
            'whatsapp_number',
            'street_number',
            'city',
            'state',
            'zip_code',
            'bio',
        ]



        widgets = {
            'height': forms.Select(choices=height_choices),
            'state': forms.Select(choices=AthleteProfile.STATE_CHOICES),
        }

        phone_number = PhoneNumberField(required=False)
        whatsapp_number = PhoneNumberField(required=False)
        date_of_birth = forms.DateField(
            widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'mm/dd/yyyy'}),
            input_formats=['%m/%d/%Y'],  # Specify accepted date format
            required=False
        )

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.fields['gender'].widget.attrs.update({'class': 'form-select'})

            for field_name, field in self.fields.items():
                if field_name != 'gender':
                    field.widget.attrs.update({'class': 'form-control'})

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
                profile_form = AthleteProfileUpdateForm(request.POST, instance=request.user.athlete_profile)

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

            context = {  # Define the context dictionary here
                'user_form': user_form,
                'profile_form': profile_form,
                'user': request.user
            }

            return render(request, 'registration/update_profile.html', context)


class OrganizerProfileForm(forms.ModelForm):
    """
    Form for creating and updating organizer profiles.
    """
    class Meta:
        model = OrganizerProfile
        fields = ('organization_name', 'contact_phone', 'org_email')