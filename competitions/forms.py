import math
import re
import requests
import bleach

import django_filters
from django import forms
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.forms import TypedChoiceField

from .models import Competition, AthleteCompetition, Event, EventImplement, Result, Tag, \
    EventBase, ZipCode, Federation, Sponsor, TshirtSize, Division, WeightClass, AthleteEventNote
from accounts.models import AthleteProfile


def validate_social_media_url(url, platform):
    """
    Validates that the URL is a valid Facebook or Instagram URL and optionally checks its existence.
    """
    patterns = {
        'facebook': r'^https://(www\.)?facebook\.com/.+',
        'instagram': r'^https://(www\.)?instagram\.com/.+',
    }

    if platform not in patterns:
        raise ValueError("Unsupported platform for URL validation.")

    if not re.match(patterns[platform], url):
        raise ValidationError(f"Enter a valid {platform.capitalize()} URL.")

    # Optionally, check if the URL is accessible
    try:
        response = requests.head(url, timeout=5)
        if response.status_code >= 400:
            raise ValidationError(f"The provided {platform.capitalize()} URL is not accessible.")
    except requests.RequestException:
        raise ValidationError(f"Unable to reach the {platform.capitalize()} URL.")

def sanitize_html(html):
    """Sanitizes HTML input to prevent XSS vulnerabilities."""
    allowed_tags = ['p', 'b', 'i', 'u', 'a', 'h1', 'h2', 'h3', 'ul', 'ol', 'li']
    allowed_attributes = {'a': ['href', 'target']}
    return bleach.clean(html, tags=allowed_tags, attributes=allowed_attributes, strip=True)

class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data]
        else:
            result = [single_file_clean(data, initial)]
        return result

from django import forms
from datetime import datetime, time, date
from tinymce.widgets import TinyMCE
from .models import Competition, Division, TshirtSize, Tag


class CompetitionForm(forms.ModelForm):
    """
    Form for creating and updating competitions.
    """
    allowed_divisions = forms.ModelMultipleChoiceField(
        queryset=Division.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False
    )

    liability_waiver_accepted = forms.BooleanField(
        required=True,
        label="Accept Liability Waiver",
        help_text="You must accept the liability waiver to proceed."
    )

    tags = forms.ModelMultipleChoiceField(
        queryset=Tag.objects.all(),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-select'}),
        required=False
    )

    provides_shirts = forms.BooleanField(
        required=False,
        label="Will T-shirts be provided?",
        help_text="Check this box if you want to collect T-shirt sizes from participants."
    )

    allowed_tshirt_sizes = forms.ModelMultipleChoiceField(
        queryset=TshirtSize.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Allowed T-shirt Sizes",
        help_text="Select the sizes athletes can choose from."
    )

    description = forms.CharField(
        widget=TinyMCE(attrs={'cols': 80, 'rows': 30}),
        required=False,
        label="Competition Description"
    )

    class Meta:
        model = Competition
        fields = [
            'name', 'comp_date', 'comp_end_date', 'start_time', 'event_location_name',
            'address', 'city', 'state', 'zip_code', 'federation',
            'signup_price', 'capacity', 'registration_deadline', 'image',
            'description', 'liability_waiver_accepted', 'provides_shirts', 'allowed_tshirt_sizes',
            'allowed_divisions', 'tags', 'facebook_url', 'instagram_url',
        ]
        widgets = {
            'comp_date': forms.DateInput(attrs={'type': 'date'}),
            'comp_end_date': forms.DateInput(attrs={'type': 'date'}),
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'registration_deadline': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'description': TinyMCE(attrs={'cols': 80, 'rows': 30}),
            'state': forms.Select(choices=Competition.STATE_CHOICES),
            'signup_price': forms.NumberInput(attrs={'type': 'number', 'step': '0.01', 'min': '0'}),
            'facebook_url': forms.URLInput(attrs={'placeholder': 'https://www.facebook.com/...'}),
            'instagram_url': forms.URLInput(attrs={'placeholder': 'https://www.instagram.com/...'}),
        }

    def clean_registration_deadline(self):
        """
        Ensures the registration deadline has a valid date and time.
        """
        registration_deadline = self.cleaned_data.get('registration_deadline')
        if registration_deadline:
            # If no specific time is provided, set it to 11:59 PM
            return datetime.combine(registration_deadline.date(), time(23, 59))
        return registration_deadline

    def clean_allowed_tshirt_sizes(self):
        """
        Ensures that if T-shirts are provided, at least one size must be selected.
        """
        if self.cleaned_data.get('provides_shirts') and not self.cleaned_data.get('allowed_tshirt_sizes'):
            raise forms.ValidationError("You must select at least one T-shirt size if T-shirts are provided.")
        return self.cleaned_data.get('allowed_tshirt_sizes', [])

    def clean(self):
        """
        Cleans and validates related data.
        """
        cleaned_data = super().clean()
        comp_date = cleaned_data.get('comp_date')
        comp_end_date = cleaned_data.get('comp_end_date')

        # Ensure that the end date is not before the start date
        if comp_end_date and comp_end_date < comp_date:
            self.add_error('comp_end_date', "End date cannot be before the start date.")

        return cleaned_data

    def save(self, commit=True):
        """
        Saves the competition and updates related ManyToMany fields.
        """
        competition = super().save(commit=False)

        # Set default scoring system
        competition.scoring_system = 'strongman'

        # Determine competition status based on date
        today = date.today()
        if competition.comp_date > today:
            competition.status = 'upcoming'
        elif competition.comp_date < today:
            competition.status = 'completed'

        if commit:
            competition.save()  # Save instance before updating ManyToMany fields

            # Handle ManyToMany fields
            if self.cleaned_data.get('allowed_tshirt_sizes'):
                competition.allowed_tshirt_sizes.set(self.cleaned_data['allowed_tshirt_sizes'])
            else:
                competition.allowed_tshirt_sizes.clear()

            if self.cleaned_data.get('tags'):
                competition.tags.set(self.cleaned_data['tags'])

            if self.cleaned_data.get('allowed_divisions'):
                competition.allowed_divisions.set(self.cleaned_data['allowed_divisions'])

        return competition


class CustomDivisionForm(forms.ModelForm):
    """Form for creating a custom division within a competition."""

    class Meta:
        model = Division
        fields = ['custom_name']
        labels = {'custom_name': 'Division Name'}
        widgets = {
            'custom_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter a custom name'}),
        }

    def clean_custom_name(self):
        custom_name = self.cleaned_data.get('custom_name')
        if not custom_name:
            raise forms.ValidationError("Division name is required.")
        return custom_name


class CustomWeightClassForm(forms.ModelForm):
    """Form for creating a custom weight class within a competition."""
    single_class = forms.BooleanField(
        required=False,
        label="Single Class",
        help_text="Create a single class for this division—no numeric weight required.",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    division = forms.ModelChoiceField(
        queryset=Division.objects.none(),
        required=True,
        help_text="Select the division this weight class belongs to."
    )
    name = forms.DecimalField(
        max_digits=4,
        decimal_places=1,
        widget=forms.NumberInput(attrs={'step': '0.1'}),
        help_text="(e.g., 140.0)."
    )

    class Meta:
        model = WeightClass
        # Note: include single_class before name/weight_d
        fields = ['division', 'gender', 'single_class', 'name', 'weight_d']
        labels = {
            'name': 'Weight (e.g. 140.0)',
            'weight_d': 'Designation (u or +)',
            'division': 'Division',
            'gender': 'Gender',
        }

    def __init__(self, *args, **kwargs):
        competition = kwargs.pop('competition', None)
        super().__init__(*args, **kwargs)

        # only allow divisions in this competition :contentReference[oaicite:0]{index=0}
        if competition:
            self.fields['division'].queryset = competition.allowed_divisions.all()
        self.helper = FormHelper()
        # ← disable crispy’s own <form> tag
        self.helper.form_tag = False
        # Make numeric fields optional (we’ll enforce when single_class is False)
        self.fields['name'].required = False
        self.fields['weight_d'].required = False

        # If the form was POSTed with single_class checked, hide the numeric inputs
        if self.data.get('single_class'):
            self.fields['name'].widget = forms.HiddenInput()
            self.fields['weight_d'].widget = forms.HiddenInput()

    def clean(self):
        cleaned = super().clean()
        single = cleaned.get('single_class')

        if single:
            # Force any numeric values to None/blank
            cleaned['name'] = None
            cleaned['weight_d'] = ''
        else:
            # enforce numeric weight + designation when not single_class
            if cleaned.get('name') is None:
                self.add_error('name', "Enter a weight or check Single Class.")
            if not cleaned.get('weight_d'):
                self.add_error('weight_d', "Choose a designation (u or +).")

        return cleaned

    def save(self, commit=True):
        wc = super().save(commit=False)
        wc.is_custom = True
        if self.cleaned_data.get('single_class'):
            wc.name     = None
            wc.weight_d = ''  # blank designation
        if commit:
            wc.save()
        return wc

class AssignWeightClassesForm(forms.Form):
    """
    Form for assigning weight classes to divisions in a competition.
    """
    def __init__(self, *args, **kwargs):
        self.competition = kwargs.pop("competition", None)
        super().__init__(*args, **kwargs)

        if self.competition:
            # Dynamically create fields for each division in the competition
            for division in self.competition.allowed_divisions.all():
                self.fields[f"division_{division.pk}"] = forms.ModelMultipleChoiceField(
                    queryset=WeightClass.objects.filter(federation=self.competition.federation),
                    required=False,
                    widget=forms.CheckboxSelectMultiple,
                    label=f"Weight Classes for {division.name}",
                )

    def save(self):
        """
        Saves the selected weight classes for each division.
        """
        for field_name, weight_classes in self.cleaned_data.items():
            if field_name.startswith("division_"):
                division_id = int(field_name.split("_")[1])
                division = Division.objects.get(pk=division_id)

                # Clear existing weight classes and add new ones
                division.allowed_weight_classes.set(weight_classes)

class EditWeightClassesForm(forms.Form):
    """
    Form for editing the weight classes assigned to a competition.
    """
    weight_classes = forms.ModelMultipleChoiceField(
        queryset=WeightClass.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Select Weight Classes"
    )

    def __init__(self, *args, **kwargs):
        self.competition = kwargs.pop('competition', None)
        super().__init__(*args, **kwargs)

        if self.competition:
            # Fetch weight classes linked to the competition's federation
            self.fields['weight_classes'].queryset = WeightClass.objects.filter(
                federation=self.competition.federation
            )

            # Pre-select the currently assigned weight classes
            self.fields['weight_classes'].initial = self.competition.allowed_weight_classes.all()

    def save(self):
        """
        Saves the selected weight classes to the competition.
        """
        if self.competition:
            self.competition.allowed_weight_classes.set(self.cleaned_data['weight_classes'])

class SponsorEditForm(forms.ModelForm):
    class Meta:
        model = Sponsor
        fields = ['logo', 'url', 'display_order']
        widgets = {
            'logo': forms.ClearableFileInput(attrs={
                'class': 'form-control',
            }),
            'url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://example.com'}),
            'display_order': forms.NumberInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['logo'].required = False

class SponsorLogoForm(forms.Form):
    sponsor_logos = MultipleFileField(required=False)

class EventCreationForm(forms.ModelForm):
    """
    Form for creating and editing an event, including details for multiple implements.
    """
    has_multiple_implements = forms.BooleanField(
        required=False,
        label="Multiple Implements?",
        help_text="Check this if the event will use multiple implements."
    )
    number_of_implements = forms.IntegerField(
        required=False,
        min_value=1,
        label="How Many Implements?",
        widget=forms.NumberInput(attrs={'placeholder': 'Enter number of implements'})
    )
    number_of_lanes = forms.IntegerField(
        min_value=1,
        initial=1,
        label="Number of Lanes",
        help_text="Set to 1 for single-lane events, or higher for multi-lane events.",
        widget=forms.NumberInput(attrs={'min': 1, 'class': 'form-control'})
    )

    class Meta:
        model = Event
        fields = ['name', 'event_base', 'weight_type', 'has_multiple_implements', 'number_of_implements', 'number_of_lanes']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter Event Name'}),
            'event_base': forms.Select(attrs={'class': 'form-control'}),
            'weight_type': forms.Select(attrs={'class': 'form-control'}),
            'number_of_implements': forms.NumberInput(attrs={'min': 1, 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Ensure the checkbox value reflects the instance value
        if self.instance and self.instance.pk:
            self.fields['has_multiple_implements'].initial = self.instance.has_multiple_implements

    def clean(self):
        """
        Validate form data to ensure correct implement details when multiple implements are selected.
        """
        cleaned_data = super().clean()
        has_multiple = cleaned_data.get('has_multiple_implements')
        num_implements = cleaned_data.get('number_of_implements')

        if has_multiple and not num_implements:
            raise forms.ValidationError("Please specify the number of implements.")

        if not has_multiple:
            cleaned_data['number_of_implements'] = None  # Reset if not using multiple implements

        return cleaned_data


class EventImplementForm(forms.ModelForm):
    implement_order = forms.IntegerField(
        widget=forms.NumberInput(attrs={
            'class': 'form-control implement-order',
            'placeholder': 'Order',
            'required': 'required',
            'min': '1'
        }),
        required=True,
        initial=1
    )
    event = forms.ModelChoiceField(
        queryset=Event.objects.all(),
        widget=forms.HiddenInput(),
        required=True
    )
    division = forms.ModelChoiceField(
        queryset=Division.objects.all(),
        widget=forms.HiddenInput(),
        required=True
    )
    weight_class = forms.ModelChoiceField(
        queryset=WeightClass.objects.all(),
        widget=forms.HiddenInput(),
        required=True
    )

    class Meta:
        model = EventImplement
        fields = ['event', 'division', 'weight_class', 'implement_order', 'implement_name', 'weight', 'weight_unit']
        widgets = {
            'implement_name': forms.TextInput(attrs={
                'class': 'form-control implement-name',
                'placeholder': 'Implement Name',
                'required': 'required'
            }),
            'weight': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Weight',
                'required': 'required',
                'min': '0'
            }),
            'weight_unit': forms.Select(attrs={
                'class': 'form-select',
                'required': 'required'
            }),
        }

    def __init__(self, *args, **kwargs):
        event = kwargs.pop('event', None)
        super().__init__(*args, **kwargs)

        if event:
            self.fields['event'].initial = event
            if event and not event.has_multiple_implements:
                self.fields['implement_order'].initial = 1
                self.fields['implement_order'].widget = forms.HiddenInput()

        # Update querysets dynamically if we have initial data
        if self.initial:
            division_id = self.initial.get('division')
            weight_class_id = self.initial.get('weight_class')

            # Set the querysets to include only the relevant objects
            if division_id:
                self.fields['division'].queryset = Division.objects.filter(id=division_id)
                self.fields['division'].initial = division_id

            if weight_class_id:
                self.fields['weight_class'].queryset = WeightClass.objects.filter(id=weight_class_id)
                self.fields['weight_class'].initial = weight_class_id

        # Hide implement_order if not multiple implements
        if event and not event.has_multiple_implements:
            self.fields['implement_order'].widget = forms.HiddenInput()
            self.fields['implement_order'].initial = 1

class ManualAthleteAddForm(forms.Form):
    """
    Form for manually adding an athlete to a competition.
    """
    email = forms.EmailField(
        required=True,
        label="Athlete Email",
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Enter athlete email'})
    )
    division = forms.ModelChoiceField(
        queryset=Division.objects.none(),
        required=True,
        label="Division",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    weight_class = forms.ModelChoiceField(
        queryset=WeightClass.objects.none(),
        required=True,
        label="Weight Class",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    tshirt_size = forms.ModelChoiceField(
        queryset=TshirtSize.objects.none(),
        required=False,
        label="T-shirt Size",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    def __init__(self, *args, **kwargs):
        """
        Dynamically filters divisions, weight classes, and T-shirt sizes based on the selected competition.
        """
        self.competition = kwargs.pop('competition', None)
        super().__init__(*args, **kwargs)

        if self.competition:
            # Set available divisions and weight classes for the competition
            self.fields['division'].queryset = self.competition.allowed_divisions.all()
            self.fields['weight_class'].queryset = WeightClass.objects.filter(
                competition=self.competition
            )

            # Handle T-shirt size field based on competition settings
            if self.competition.provides_shirts:
                self.fields['tshirt_size'].queryset = self.competition.allowed_tshirt_sizes.all()
            else:
                self.fields.pop('tshirt_size', None)  # Remove field if not applicable

    def clean_email(self):
        """
        Validate that the email belongs to a registered athlete.
        """
        email = self.cleaned_data.get('email')
        if not AthleteProfile.objects.filter(user__email=email).exists():
            raise forms.ValidationError("No registered athlete found with this email.")
        return email

    def save(self):
        """
        Save the manually added athlete to the competition.
        """
        email = self.cleaned_data.get('email')
        athlete_profile = AthleteProfile.objects.get(user__email=email)

        # Create the AthleteCompetition entry
        athlete_competition, created = AthleteCompetition.objects.get_or_create(
            athlete=athlete_profile,
            competition=self.competition,
            defaults={
                'division': self.cleaned_data['division'],
                'weight_class': self.cleaned_data['weight_class'],
                'signed_up': True
            }
        )

        # Assign T-shirt size if applicable
        if 'tshirt_size' in self.cleaned_data and self.cleaned_data['tshirt_size']:
            athlete_competition.tshirt_size = self.cleaned_data['tshirt_size']
            athlete_competition.save()

        return athlete_competition

class AthleteProfileForm(forms.ModelForm):
    """
    Form for updating an athlete's profile information.
    """
    first_name = forms.CharField(
        max_length=30,
        required=True,
        label="First Name",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter first name'})
    )
    last_name = forms.CharField(
        max_length=150,
        required=True,
        label="Last Name",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter last name'})
    )

    class Meta:
        model = AthleteProfile
        fields = ['first_name', 'last_name', 'gender', 'date_of_birth', 'phone_number', 'home_gym', 'team_name', 'coach', 'height', 'weight']
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date', 'class': 'form-control', 'placeholder': 'YYYY-MM-DD'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter phone number'}),
            'home_gym': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter home gym'}),
            'team_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter team name'}),
            'coach': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter coach name'}),
            'height': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Enter height in inches'}),
            'weight': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Enter weight in lbs or kg'}),
        }

    def __init__(self, *args, **kwargs):
        """
        Initialize form and prepopulate user fields if available.
        """
        super().__init__(*args, **kwargs)

        # Pre-fill first and last name from the related User model
        if self.instance and self.instance.user:
            self.fields['first_name'].initial = self.instance.user.first_name
            self.fields['last_name'].initial = self.instance.user.last_name

    def save(self, commit=True):
        """
        Save the AthleteProfile and also update the related User model.
        """
        athlete_profile = super().save(commit=False)

        # Update User model first_name and last_name
        athlete_profile.user.first_name = self.cleaned_data['first_name']
        athlete_profile.user.last_name = self.cleaned_data['last_name']

        if commit:
            athlete_profile.user.save()  # Save User model
            athlete_profile.save()  # Save AthleteProfile model

        return athlete_profile

class AthleteCompetitionForm(forms.ModelForm):
    class Meta:
        model = AthleteCompetition
        fields = ['division', 'weight_class', 'tshirt_size']
        widgets = {
            'division': forms.Select(attrs={'class': 'form-select'}),
            'weight_class': forms.Select(attrs={'class': 'form-select'}),
            'tshirt_size': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        competition = kwargs.pop('competition', None)
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        if competition:
            # Filter divisions based on the competition
            self.fields['division'].queryset = competition.allowed_divisions.all()

            # Determine athlete gender
            athlete_gender = None
            print(f"Request available: {self.request is not None}")
            print(f"Instance exists: {self.instance and self.instance.pk}")
            if self.instance and hasattr(self.instance, 'athlete') and self.instance.athlete_id:
                athlete_gender = self.instance.athlete.gender
                print(f"Gender from instance: {athlete_gender} (Athlete: {self.instance.athlete.user.username})")
            elif self.request and hasattr(self.request.user, 'athlete_profile'):
                try:
                    athlete_gender = self.request.user.athlete_profile.gender
                    print(f"Gender from request.user.athlete_profile: {athlete_gender} (User: {self.request.user.username})")
                except ObjectDoesNotExist:
                    print("No AthleteProfile for user")
                    athlete_gender = None
            else:
                print("No instance or request available to determine gender")

            # Filter weight classes
            weight_class_queryset = WeightClass.objects.filter(federation=competition.federation)
            print(f"Initial Weight Classes: {list(weight_class_queryset.values('name', 'gender'))}")
            if athlete_gender in ['male', 'female']:
                # Capitalize to match WeightClass.gender
                filtered_gender = athlete_gender.capitalize()
                weight_class_queryset = weight_class_queryset.filter(gender=filtered_gender)
                print(f"Weight Classes after gender filter ({filtered_gender}): {list(weight_class_queryset.values('name', 'gender'))}")
            else:
                print(f"No gender filter applied (athlete_gender: {athlete_gender})")

            # Further filter by divisions allowed in the competition
            weight_class_queryset = weight_class_queryset.filter(
                division__in=competition.allowed_divisions.all()
            ).distinct()
            print(f"Final Weight Class Queryset: {list(weight_class_queryset)}")

            self.fields['weight_class'].queryset = weight_class_queryset

            # Handle T-shirt sizes dynamically based on competition settings
            if competition.provides_shirts:
                self.fields['tshirt_size'].queryset = competition.allowed_tshirt_sizes.all()
            else:
                self.fields.pop('tshirt_size', None)


class CombineWeightClassesForm(forms.Form):
    """
    Form for merging weight classes within a division.
    """
    division = forms.ModelChoiceField(
        queryset=Division.objects.none(),
        label="Division",
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    from_weight_class = forms.ModelChoiceField(
        queryset=WeightClass.objects.none(),
        label="From Weight Class",
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    to_weight_class = forms.ModelChoiceField(
        queryset=WeightClass.objects.none(),
        label="To Weight Class",
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    def __init__(self, *args, **kwargs):
        competition = kwargs.pop('competition', None)
        division_id = kwargs.get('data', {}).get('division')
        super().__init__(*args, **kwargs)

        if competition:
            # Populate the division field with allowed divisions
            self.fields['division'].queryset = competition.allowed_divisions.all()

            # If a division is selected, filter weight classes accordingly
            if division_id:
                try:
                    division = Division.objects.get(id=division_id)
                    self.fields['from_weight_class'].queryset = WeightClass.objects.filter(
                        competition=competition,  # Filter by competition
                        is_custom=True  # Only custom weight classes
                    )
                    self.fields['to_weight_class'].queryset = WeightClass.objects.filter(
                        competition=competition,
                        is_custom=True
                    )
                except Division.DoesNotExist:
                    pass


class ResultForm(forms.ModelForm):
    class Meta:
        model = Result
        fields = ['value']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        event_order = self.instance.event_order
        event_type = event_order.event.weight_type

        self.fields['value'].label = f"{event_order.event.name} ({event_order.event.get_weight_type_display()})"

        if event_type == 'time':
            self.fields['value'].widget.attrs['placeholder'] = "Time in 1+HH:MM:SS format"
        elif event_type == 'reps':
            self.fields['value'].widget.attrs['placeholder'] = "Enter number of reps"
        elif event_type == 'distance':
            self.fields['value'].widget.attrs['placeholder'] = "Enter distance in meters"
        elif event_type == 'height':
            self.fields['value'].widget.attrs['placeholder'] = "Enter height in centimeters"
        elif event_type == 'max':
            self.fields['value'].widget.attrs['placeholder'] = "Enter max weight in kilograms"

    def clean_value(self):
        value = self.cleaned_data['value']
        event_order = self.instance.event_order
        event_type = event_order.event.weight_type

        if event_type == 'time':
            try:
                implements, time_str = value.split('+')
                int(implements)  # Check if 'implements' is an integer
                hours, minutes, seconds = map(int, time_str.split(':'))
                if not (0 <= hours <= 23 and 0 <= minutes <= 59 and 0 <= seconds <= 59):
                    raise ValueError("Invalid time format.")
            except ValueError:
                raise forms.ValidationError("Invalid format. Use 'implements+HH:MM:SS'.")
        elif event_type == 'reps':
            try:
                # Attempt to convert the reps value to an integer
                reps = int(value)
                if reps <= 0:
                    raise ValueError("Reps must be a positive integer.")
            except ValueError:
                raise forms.ValidationError("Invalid reps value. Please enter a positive integer.")
        elif event_type == 'distance':
            try:
                # Attempt to convert the distance value to a float
                distance = float(value)
                if distance <= 0:
                    raise ValueError("Distance must be a positive number.")
            except ValueError:
                raise forms.ValidationError("Invalid distance value. Please enter a positive number.")
        elif event_type == 'height':
            try:
                # Attempt to convert the height value to a float
                height = float(value)
                if height <= 0:
                    raise ValueError("Height must be a positive number.")
            except ValueError:
                raise forms.ValidationError("Invalid height value. Please enter a positive number.")
        elif event_type == 'max':
            try:
                # Attempt to convert the max weight value to a float
                max_weight = float(value)
                if max_weight <= 0:
                    raise ValueError("Max weight must be a positive number.")
            except ValueError:
                raise forms.ValidationError("Invalid max weight value. Please enter a positive number.")

        return value

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


class CompetitionFilter(django_filters.FilterSet):
    zip_code = django_filters.CharFilter(
        method='filter_by_zip_code',
        label='Zip Code',
        widget=forms.TextInput(attrs={'placeholder': 'Enter zip code'})
    )
    comp_date_after = django_filters.DateFilter(
        field_name='comp_date',
        lookup_expr='gte',
        label='Competition Date After',
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    comp_date_before = django_filters.DateFilter(
        field_name='comp_date',
        lookup_expr='lte',
        label='Competition Date Before',
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    event_base = django_filters.ModelChoiceFilter(
        field_name='events__event_base',
        queryset=EventBase.objects.all(),
        label='Event Base',
        widget=forms.Select(attrs={'class': 'form-control', 'placeholder': 'Select an event...'}),
    )

    allowed_divisions = django_filters.ModelChoiceFilter(
        field_name='allowed_divisions',
        queryset=Division.objects.all(),
        label='Allowed Divisions',
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    tags = django_filters.ModelChoiceFilter(
        field_name='tags',
        queryset=Tag.objects.all(),
        label='Tags',
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    federation = django_filters.ModelChoiceFilter(
        field_name='federation',
        queryset=Federation.objects.all(),
        label='Federation',
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    class Meta:
        model = Competition
        fields = ['zip_code', 'comp_date_after', 'comp_date_before', 'event_base',  'allowed_divisions', 'tags', 'federation']

    def filter_by_zip_code(self, queryset, name, value):
        if value:
            try:
                # Get the user's zip code object
                user_zip_code = ZipCode.objects.get(zip_code=value)
            except ZipCode.DoesNotExist:
                print(f"Invalid zip code provided: {value}")
                return queryset

            # Create a list of tuples to store distances
            competitions_with_distances = []

            for competition in queryset:
                try:
                    competition_zip_code = ZipCode.objects.get(zip_code=competition.zip_code)
                    distance = haversine_distance(
                        user_zip_code.latitude,
                        user_zip_code.longitude,
                        competition_zip_code.latitude,
                        competition_zip_code.longitude
                    )
                    competitions_with_distances.append((competition, distance))
                except ZipCode.DoesNotExist:
                    # If competition's zip code is missing, set distance to infinity
                    competitions_with_distances.append((competition, float('inf')))

            # Sort the competitions by distance
            competitions_with_distances.sort(key=lambda x: x[1])

            # Return the sorted competitions as a QuerySet-like list
            sorted_competitions = [competition for competition, _ in competitions_with_distances]

            # Create a new queryset that matches the sorted competitions' IDs
            sorted_ids = [competition.pk for competition in sorted_competitions]
            return queryset.filter(pk__in=sorted_ids).order_by('pk')

        # If no zip code is provided, return the queryset as-is
        return queryset


class AthleteEventNoteForm(forms.ModelForm):
    class Meta:
        model = AthleteEventNote
        fields = ['note_type', 'note_value']
        widgets = {
            'note_type': forms.Select(attrs={'class': 'form-select note-type-select'}),
            'note_value': forms.TextInput(attrs={'class': 'form-control'})
        }

    def __init__(self, *args, **kwargs):
        event = kwargs.pop('event', None)
        super().__init__(*args, **kwargs)

        # Customize note_type choices based on event weight_type
        if event:
            choices = [('', '-- Select Note Type --')]

            # Common note types for all events
            common_types = [
                ('general', 'General Note'),
                ('equipment', 'Equipment Note'),
            ]

            # Event-specific note types
            if event.weight_type == 'max':
                specific_types = [
                    ('opening_weight', 'Opening Weight'),
                    ('next_attempt', 'Next Attempt'),
                    ('rack_height', 'Rack Height'),
                ]
            elif event.weight_type == 'time':
                specific_types = [
                    ('target_time', 'Target Time'),
                    ('strategy', 'Strategy'),
                ]
            elif event.weight_type == 'distance':
                specific_types = [
                    ('implement_selection', 'Implement Selection'),
                ]
            elif event.weight_type == 'reps':
                specific_types = [
                    ('target_reps', 'Target Reps'),
                ]
            else:
                specific_types = []

            # Add custom note type for this specific event
            event_specific = [(f"event_{event.id}_custom", f"Custom for {event.name}")]

            # Combine and set choices
            self.fields['note_type'].choices = choices + common_types + specific_types + event_specific


from accounts.models import User, AthleteProfile
from competitions.models import Competition, AthleteCompetition, Division, WeightClass, TshirtSize
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Row, Column, Fieldset, Submit, HTML

class OrlandosStrongestSignupForm(forms.Form):
    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'you@example.com'})
    )
    first_name = forms.CharField(
        max_length=30,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    last_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    password1 = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        help_text=password_validation.password_validators_help_text_html(),
    )
    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        strip=False,
        help_text="Enter the same password again, for verification.",
    )

    # AthleteProfile fields
    profile_picture = forms.ImageField(
        required=False,
        label="Profile Picture",
        widget=forms.ClearableFileInput(attrs={'class': 'form-control'})
    )

    gender        = forms.ChoiceField(
        choices=AthleteProfile._meta.get_field('gender').choices,
        widget=forms.Select(attrs={'class':'form-select'})
    )
    date_of_birth = forms.DateField(
        widget=forms.DateInput(attrs={'type':'date','class':'form-control'})
    )
    city = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label="City"
    )
    state = forms.ChoiceField(
        choices=AthleteProfile.STATE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="State"
    )
    home_gym      = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class':'form-control'})
    )
    team_name     = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class':'form-control'})
    )
    coach         = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class':'form-control'})
    )
    height = TypedChoiceField(
        required=False,
        choices=[],  # we’ll fill this in __init__
        coerce=int,  # cleaned_data['height'] will be an int
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Select your height (feet & inches)",
        label="Height"
    )
    weight = forms.DecimalField(
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )

    # Competition signup fields
    division = forms.ModelChoiceField(
        queryset=Division.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    weight_class = forms.ModelChoiceField(
        queryset=WeightClass.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    def __init__(self, *args, **kwargs):
        self.competition = kwargs.pop("competition")
        super().__init__(*args, **kwargs)

        choices = []
        for feet in range(4, 8):  # from 4'0" to 7'11"
            for inch in range(0, 12):
                total_in = feet * 12 + inch
                label = f"{feet}'{inch}\""
                choices.append((total_in, label))
        self.fields['height'].choices = choices

        # 1) Crispy helper setup
        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.form_class = "needs-validation"
        self.helper.attrs = {"novalidate": "", "autocomplete": "off"}
        self.helper.layout = Layout(
            # Header card
            HTML("""
                <div class="card mb-4 shadow-sm">
                  <div class="card-body text-center">
                    <h2 class="card-title">Join Orlando’s Strongest</h2>
                    <p class="card-text text-muted">Create your account & register in one step.</p>
                  </div>
                </div>
            """),
            # Account credentials row
            Fieldset(
                "Account Details",
                Row(
                    Column("first_name", css_class="mb-3"),
                    Column("last_name", css_class="mb-3"),
                ),
                "email",
                Row(
                    Column("password1", css_class="mb-3"),
                    Column("password2", css_class="mb-3"),
                ),
            ),
            # Athlete profile card
            Fieldset(
                "Athlete Profile",
                Row(Column("gender"), Column("date_of_birth")),
                Row(Column("city"), Column("state")),
                Row(Column("home_gym"), Column("team_name")),
                Row(Column("coach"), Column("profile_picture")),  # ← here
                Row(Column("height"), Column("weight")),
            ),
            # Competition signup card
            Fieldset(
                "Competition Entry",
                Row(
                    Column("division", css_class="mb-3"),
                    Column("weight_class", css_class="mb-3"),
                ),
            ),
            # Submit
            Submit("submit", "Join Now", css_class="btn-lg btn-primary w-100 mt-4")
        )

        # 2) Populate the dynamic querysets
        self.fields["division"].queryset = self.competition.allowed_divisions.all()
        wc_qs = WeightClass.objects.filter(
            federation=self.competition.federation,
            division__in=self.competition.allowed_divisions.all()
        ).distinct()
        self.fields["weight_class"].queryset = wc_qs

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if User.objects.filter(email=email).exists():
            raise ValidationError("An account with this email already exists. Please log in.")
        return email

    def clean_password2(self):
        p1 = self.cleaned_data.get('password1')
        p2 = self.cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            raise ValidationError("The two password fields didn’t match.")
        password_validation.validate_password(p2, user=None)
        return p2