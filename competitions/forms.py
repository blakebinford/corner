import math
from datetime import date

import django_filters
from django.db.models import F, ExpressionWrapper, FloatField
from django import forms
from django.forms import NumberInput, modelformset_factory

from .models import Competition, EventOrder, AthleteCompetition, Event, EventImplement, Result, Tag, \
    DivisionWeightClass, EventBase, ZipCode, Federation
from accounts.models import Division, WeightClass
import bleach
from tinymce.widgets import TinyMCE


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

    class Meta:
        model = Competition
        fields = [
            'name', 'comp_date', 'comp_end_date', 'start_time', 'event_location_name',
            'address', 'city', 'state', 'zip_code', 'federation',
            'signup_price', 'capacity', 'registration_deadline', 'image',
            'description', 'liability_waiver_accepted',
            'allowed_divisions', 'allowed_weight_classes', 'tags'
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
        }

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['allowed_divisions'].queryset = Division.objects.all()

    def save(self, commit=True):
        competition = super().save(commit=False)
        competition.scoring_system = 'strongman'  # Set the default scoring system
        if competition.comp_date > date.today():
            competition.status = 'upcoming'  # Default to upcoming if in the future
        elif competition.comp_date < date.today():
            competition.status = 'completed'
        competition.save()
            # Count the number of signed-up athletes
        signed_up_athletes_count = AthleteCompetition.objects.filter(
            competition=competition,
            signed_up=True
        ).count()

        # Compare the count to the capacity to determine 'full' or 'limited' status
        if signed_up_athletes_count >= competition.capacity:
            competition.status = 'full'
        elif signed_up_athletes_count >= 0.9 * competition.capacity:
            competition.status = 'limited'

        if commit:
            competition.save()

        return competition

class SponsorLogoForm(forms.Form):
    sponsor_logos = MultipleFileField(required=False)

class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ['name', 'event_base', 'weight_type', ]

class EventImplementForm(forms.ModelForm):
    class Meta:
        model = EventImplement
        fields = ['id', 'division_weight_class', 'implement_name', 'implement_order', 'weight', 'weight_unit']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # You might need to adjust the queryset based on your specific needs
        self.fields['division_weight_class'].queryset = DivisionWeightClass.objects.all()

def create_event_implement_formset(competition, extra=1):
    """
    Function to create an EventImplementFormSet with one form per DivisionWeightClass.
    """
    formset_class = forms.formset_factory(EventImplementForm, extra=extra)
    initial_data = []
    allowed_division_weight_classes = DivisionWeightClass.objects.filter(
        division__in=competition.allowed_divisions.all(),
        weight_class__in=competition.allowed_weight_classes.all()
    ).order_by(
        'weight_class__name',  # Sort by division name first
        'gender',          # Then sort by gender
        'division__name'  # Finally, sort by the extracted numeric weight class
    )
    for division_weight_class in allowed_division_weight_classes:
        initial_data.append({'division_weight_class': division_weight_class.id})


    formset = formset_class(initial=initial_data)

    # Set the queryset for the division_weight_class field in each form
    for form in formset:
        form.fields['division_weight_class'].queryset = allowed_division_weight_classes

    return formset

EventImplementFormSet = modelformset_factory(
    EventImplement,
    form=EventImplementForm,
    fields=('id', 'division_weight_class', 'implement_name', 'implement_order', 'weight', 'weight_unit'),
    extra=0,
    can_delete=True
)

class AthleteCompetitionForm(forms.ModelForm):  # New form for AthleteCompetition
    class Meta:
        model = AthleteCompetition
        fields = ['division', 'weight_class',]

        def __init__(self, *args, **kwargs):
            competition = kwargs.pop('competition', None)
            super().__init__(*args, **kwargs)

            # Filter weight classes based on the competition
            if competition:
                self.fields['weight_class'].queryset = competition.allowed_weight_classes.all()

            # Optionally filter divisions as well
            if competition:
                self.fields['division'].queryset = competition.allowed_divisions.all()

            self.instance.payment_status = 'pending'

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
        field_name='events__event_base',  # Use the related field 'event_base' in the Event model
        queryset=EventBase.objects.all(),
        label='Event Base',
        widget=forms.Select(attrs={'class': 'form-control'})   # Or any other suitable widget
    )
    allowed_divisions = django_filters.ModelChoiceFilter(
        field_name='allowed_divisions',
        queryset=Division.objects.all(),
        label='Allowed Divisions',
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    allowed_weight_classes = django_filters.ModelChoiceFilter(
        field_name='allowed_weight_classes',
        queryset=WeightClass.objects.all(),
        label='Allowed Weight Classes',
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
        fields = ['zip_code', 'comp_date_after', 'comp_date_before', 'event_base',  'allowed_divisions', 'allowed_weight_classes', 'tags', 'federation']

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