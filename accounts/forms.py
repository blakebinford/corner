from django import forms
from phonenumber_field.formfields import PhoneNumberField
from django.contrib import messages
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import User, AthleteProfile, OrganizerProfile
import re

# Height choices (formatted for dropdown selection)
height_choices = []
feet = 4
inches = 11

while feet <= 7:
    while inches <= 12:
        if feet == 7 and inches == 3:
            break  # Stop at 7'2"
        display_value = f"{feet}'{inches:02d}\""
        total_inches = (feet * 12) + inches
        height_choices.append((total_inches, display_value))
        inches += 1  # Increment inches
        if inches == 12:
            inches = 0  # Reset inches
            feet += 1
    feet += 1
    inches = 1  # Reset inches for the next foot


class CustomUserCreationForm(UserCreationForm):
    """Form for user registration."""
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
        user.email = self.cleaned_data['email']

        if commit:
            user.save()
            if user.role == 'athlete':
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
    """Form for updating the AthleteProfile model."""

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
            'date_of_birth': forms.DateInput(
                attrs={'class': 'form-control', 'placeholder': 'mm/dd/yyyy', 'type': 'date'}
            ),
        }

    phone_number = PhoneNumberField(required=False)
    whatsapp_number = PhoneNumberField(required=False)


class OrganizerProfileForm(forms.ModelForm):
    """Form for creating and updating organizer profiles."""

    class Meta:
        model = OrganizerProfile
        fields = ('organization_name', 'contact_phone', 'org_email')
