from django import forms
from phonenumber_field.formfields import PhoneNumberField
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import User, AthleteProfile, OrganizerProfile

class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = UserCreationForm.Meta.fields + ('email', 'role',)

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
            'instagram_name',
            'x_name',
            'facebook_name',
        )
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs.update({'class': 'form-control'})

class AthleteProfileUpdateForm(forms.ModelForm):

    locationiq_token = forms.CharField(widget=forms.HiddenInput())
    validated_address = forms.CharField(widget=forms.HiddenInput(), required=False)
    validated_city = forms.CharField(widget=forms.HiddenInput(), required=False)
    validated_state = forms.CharField(widget=forms.HiddenInput(), required=False)
    validated_zip = forms.CharField(widget=forms.HiddenInput(), required=False)
    validated_country = forms.CharField(widget=forms.HiddenInput(), required=False)

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
            'locationiq_token',
            'validated_address',
            'validated_city',
            'validated_state',
            'validated_zip',
            'validated_country',
        ]

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

            self.fields['locationiq_token'].initial = settings.LOCATIONIQ_API_KEY

            for field_name, field in self.fields.items():
                if field_name != 'gender':
                    field.widget.attrs.update({'class': 'form-control'})

class OrganizerProfileForm(forms.ModelForm):
    """
    Form for creating and updating organizer profiles.
    """
    class Meta:
        model = OrganizerProfile
        fields = ('organization_name', 'contact_phone', 'org_email')