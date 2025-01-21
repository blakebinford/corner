import math
from datetime import date
import re
import requests
import bleach
from tinymce.widgets import TinyMCE

import django_filters
from django import forms
from django.forms import NumberInput, modelformset_factory
from django.core.exceptions import ValidationError

from .models import Competition, EventOrder, AthleteCompetition, Event, EventImplement, Result, Tag, \
    DivisionWeightClass, EventBase, ZipCode, Federation, Sponsor, TshirtSize
from accounts.models import User, Division, WeightClass, AthleteProfile


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

class CompetitionForm(forms.ModelForm):
    allowed_divisions = forms.ModelMultipleChoiceField(
        queryset=Division.objects.all(),
        widget=forms.CheckboxSelectMultiple
    )
    liability_waiver_accepted = forms.BooleanField(required=True)
    tags = forms.ModelMultipleChoiceField(
        queryset=Tag.objects.all(),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-select'})
    )
    provides_shirts = forms.BooleanField(
        required=False,
        label="Will T-shirts be provided?",
        help_text="Check this box if you want to collect T-shirt sizes from participants."
    )
    allowed_tshirt_sizes = forms.MultipleChoiceField(
        required=False,
        widget=forms.CheckboxSelectMultiple,
        choices=TshirtSize.SIZE_CHOICES,  # Use SIZE_CHOICES directly
        label="Allowed T-shirt Sizes",
        help_text="Select the sizes athletes can choose from."
    )
    description = forms.CharField(
        widget=TinyMCE(attrs={'cols': 80, 'rows': 30}),
        required=False,
        label="Description",
    )
    class Meta:
        model = Competition
        fields = [
            'name', 'comp_date', 'comp_end_date', 'start_time', 'event_location_name',
            'address', 'city', 'state', 'zip_code', 'federation',
            'signup_price', 'capacity', 'registration_deadline', 'image',
            'description', 'liability_waiver_accepted', 'provides_shirts', 'allowed_tshirt_sizes',
            'allowed_divisions', 'allowed_weight_classes', 'tags', 'facebook_url', 'instagram_url',
        ]
        widgets = {
            'comp_date': forms.DateInput(attrs={'type': 'date'}),
            'comp_end_date': forms.DateInput(attrs={'type': 'date'}),
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'registration_deadline': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'allowed_weight_classes': forms.CheckboxSelectMultiple,
            'description': TinyMCE(attrs={'cols': 80, 'rows': 30}),
            'state': forms.Select(choices=Competition.STATE_CHOICES),
            'signup_price': NumberInput(attrs={'type': 'number', 'step': '0.01', 'min': '0'}),
            'facebook_url': forms.URLInput(attrs={'placeholder': 'https://www.facebook.com/...'}),
            'instagram_url': forms.URLInput(attrs={'placeholder': 'https://www.instagram.com/...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['allowed_divisions'].queryset = Division.objects.all()

        # Pre-check T-shirt sizes if they exist
        if self.instance.pk:  # Ensure this runs for existing instances
            selected_sizes = [tshirt_size.size for tshirt_size in self.instance.allowed_tshirt_sizes.all()]
            print("Selected Sizes in Init:", selected_sizes)  # Debugging output
            self.fields['allowed_tshirt_sizes'].initial = selected_sizes
            print("Initial for allowed_tshirt_sizes:", self.fields['allowed_tshirt_sizes'].initial)
            self.fields['allowed_tshirt_sizes'].widget.attrs['value'] = selected_sizes

    def clean_allowed_tshirt_sizes(self):
        if self.cleaned_data.get('provides_shirts') and not self.cleaned_data.get('allowed_tshirt_sizes'):
            raise forms.ValidationError("You must select at least one T-shirt size if T-shirts are provided.")
        return self.cleaned_data.get('allowed_tshirt_sizes', [])

    def clean_facebook_url(self):
        facebook_url = self.cleaned_data.get('facebook_url')
        if facebook_url:
            validate_social_media_url(facebook_url, 'facebook')
        return facebook_url

    def clean_instagram_url(self):
        instagram_url = self.cleaned_data.get('instagram_url')
        if instagram_url:
            validate_social_media_url(instagram_url, 'instagram')
        return instagram_url

    def clean(self):
        cleaned_data = super().clean()
        is_multi_day = cleaned_data.get('is_multi_day', False)
        comp_date = cleaned_data.get('comp_date')
        comp_end_date = cleaned_data.get('comp_end_date')

        if not is_multi_day and comp_date:
            cleaned_data['comp_end_date'] = comp_date

        return cleaned_data

    def clean_description(self):
        """Sanitizes the description field before saving."""
        description = self.cleaned_data.get('description')
        if description:
            return sanitize_html(description)
        return description

    def save(self, commit=True):
        competition = super().save(commit=False)
        competition.scoring_system = 'strongman'  # Set the default scoring system

        # Determine competition status based on date
        if competition.comp_date > date.today():
            competition.status = 'upcoming'  # Default to upcoming if in the future
        elif competition.comp_date < date.today():
            competition.status = 'completed'

        # Save competition instance before updating ManyToMany fields
        if commit:
            competition.save()

        # Handle T-shirt sizes
        selected_sizes = self.cleaned_data.get('allowed_tshirt_sizes', [])
        selected_sizes = self.cleaned_data.get('allowed_tshirt_sizes', [])
        print("Saving Sizes:", selected_sizes)
        if selected_sizes:
            tshirt_size_objects = TshirtSize.objects.filter(size__in=selected_sizes)
            competition.allowed_tshirt_sizes.set(tshirt_size_objects)
        else:
            competition.allowed_tshirt_sizes.clear()  # Remove all sizes if none are selected

        if commit:
            competition.save()

        return competition

class EditWeightClassesForm(forms.Form):
    weight_classes = forms.ModelMultipleChoiceField(
        queryset=WeightClass.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False
    )

    def __init__(self, *args, **kwargs):
        competition = kwargs.pop('competition', None)
        super().__init__(*args, **kwargs)

        if competition:
            # Fetch weight classes linked to the competition's federation
            self.fields['weight_classes'].queryset = WeightClass.objects.filter(
                federation=competition.federation
            )

            # Pre-select the currently allowed weight classes
            self.initial_weight_classes = competition.allowed_weight_classes.all()

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
    has_multiple_implements = forms.BooleanField(required=False, label="Multiple Implements?")
    number_of_implements = forms.IntegerField(
        required=False,
        min_value=1,
        label="How Many Implements?",
        widget=forms.NumberInput(attrs={'placeholder': 'Enter number of implements'})
    )

    class Meta:
        model = Event
        fields = ['name', 'event_base', 'weight_type', 'has_multiple_implements', 'number_of_implements']
        widgets = {
            'number_of_implements': forms.NumberInput(attrs={'min': 1}),
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
        return cleaned_data




class EventImplementForm(forms.ModelForm):
    """
    Form for assigning implements to weight classes within an event.
    """
    class Meta:
        model = EventImplement
        fields = ['division_weight_class', 'implement_name', 'implement_order', 'weight', 'weight_unit']
        widgets = {
            'implement_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Implement Name'}),
            'implement_order': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Order'}),
            'weight': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Weight'}),
            'weight_unit': forms.Select(attrs={'class': 'form-select'}),
        }


# Formset for EventImplement, auto-managing the number of forms based on competition weight classes
EventImplementFormSet = modelformset_factory(
    EventImplement,
    form=EventImplementForm,
    extra=0,
    can_delete=True
)

class ManualAthleteAddForm(forms.Form):
    email = forms.EmailField(required=True, label="Athlete Email")
    division = forms.ModelChoiceField(queryset=Division.objects.none(), required=True, label="Division")
    weight_class = forms.ModelChoiceField(queryset=WeightClass.objects.none(), required=True, label="Weight Class")
    tshirt_size = forms.ModelChoiceField(queryset=TshirtSize.objects.none(), required=False, label="T-shirt Size")

    def __init__(self, *args, **kwargs):
        competition = kwargs.pop('competition', None)
        super().__init__(*args, **kwargs)

        if competition:
            self.fields['division'].queryset = competition.allowed_divisions.all()
            self.fields['weight_class'].queryset = competition.allowed_weight_classes.all()
            if competition.provides_shirts:
                self.fields['tshirt_size'].queryset = competition.allowed_tshirt_sizes.all()
            else:
                self.fields.pop('tshirt_size', None)

class AthleteProfileForm(forms.ModelForm):
    first_name = forms.CharField(max_length=30, required=True, label="First Name")
    last_name = forms.CharField(max_length=150, required=True, label="Last Name")

    class Meta:
        model = AthleteProfile
        fields = ['first_name', 'last_name', 'gender', 'date_of_birth']
        widgets = {
            'date_of_birth': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control',
                'placeholder': 'YYYY-MM-DD'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class AthleteCompetitionForm(forms.ModelForm):
    class Meta:
        model = AthleteCompetition
        fields = ['division', 'weight_class', 'tshirt_size']

    def __init__(self, *args, **kwargs):
        competition = kwargs.pop('competition', None)
        super().__init__(*args, **kwargs)
        if competition:
            self.fields['weight_class'].queryset = competition.allowed_weight_classes.all()
            self.fields['division'].queryset = competition.allowed_divisions.all()

            # Add conditional logic for T-shirt sizes
            if competition.provides_shirts:
                self.fields['tshirt_size'].queryset = competition.allowed_tshirt_sizes.all()
            else:
                self.fields.pop('tshirt_size', None)

class CombineWeightClassesForm(forms.Form):
    from_weight_class = forms.ModelChoiceField(
        queryset=WeightClass.objects.none(),
        label="From Weight Class",
        required=True
    )
    to_weight_class = forms.ModelChoiceField(
        queryset=WeightClass.objects.none(),
        label="To Weight Class",
        required=True
    )

    def __init__(self, *args, **kwargs):
        competition = kwargs.pop('competition', None)
        super().__init__(*args, **kwargs)
        if competition:
            allowed_weight_classes = competition.allowed_weight_classes.all()
            self.fields['from_weight_class'].queryset = allowed_weight_classes
            self.fields['to_weight_class'].queryset = allowed_weight_classes


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

