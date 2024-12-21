from crispy_forms.helper import FormHelper
from django import forms
from .models import Competition, EventOrder, AthleteCompetition, Event, EventImplement, Result
from accounts.models import Division, WeightClass
import bleach
from tinymce.widgets import TinyMCE

def sanitize_html(html):
    """Sanitizes HTML input to prevent XSS vulnerabilities."""
    allowed_tags = ['p', 'b', 'i', 'u', 'a', 'h1', 'h2', 'h3', 'ul', 'ol', 'li']
    allowed_attributes = {'a': ['href', 'target']}
    return bleach.clean(html, tags=allowed_tags, attributes=allowed_attributes, strip=True)


class CompetitionForm(forms.ModelForm):
        allowed_divisions = forms.ModelMultipleChoiceField(
            queryset=Division.objects.all(),  # Set the queryset here
            widget=forms.CheckboxSelectMultiple  # Use CheckboxSelectMultiple widget
        )

        class Meta:
            model = Competition
            fields = ['name', 'comp_date', 'location', 'signup_price', 'description', 'scoring_system', 'status',
                      'registration_deadline', 'allowed_divisions', 'allowed_weight_classes', 'image', 'tags']
            widgets = {
                'comp_date': forms.DateInput(attrs={'type': 'date'}),
                'registration_deadline': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
                'allowed_weight_classes': forms.CheckboxSelectMultiple,
                'description': TinyMCE(attrs={'cols': 80, 'rows': 30}),
            }

        def clean_description(self):
            """Sanitizes the description field before saving."""
            description = self.cleaned_data.get('description')
            if description:
                return sanitize_html(description)
            return description

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.fields['allowed_divisions'].queryset = Division.objects.all()

class EventForm(forms.ModelForm):
    class Meta:
        model = EventOrder
        fields = ['event', 'order']

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.helper = FormHelper()
            self.helper.form_tag = False

        class Meta:
            model = Event
            fields = ['name', 'weight_type']

class EventImplementForm(forms.ModelForm):  # Form for EventImplement
    class Meta:
        model = EventImplement
        fields = ['division_weight_class', 'implement_name',
                  'implement_order', 'weight', 'weight_unit']

EventImplementFormSet = forms.inlineformset_factory(
    Event, EventImplement, form=EventImplementForm, extra=1
)

class AthleteCompetitionForm(forms.ModelForm):  # New form for AthleteCompetition
    class Meta:
        model = AthleteCompetition
        fields = ['division', 'weight_class',]

        def __init__(self, *args, **kwargs):
            self.request = kwargs.pop('request', None)  # Get the request object
            super().__init__(*args, **kwargs)

            if self.request and self.request.user.is_authenticated:
                athlete_profile = self.request.user.athleteprofile
                self.fields['division'].queryset = Division.objects.filter(
                    allowed_competitions=self.instance.competition
                )
                self.fields['weight_class'].queryset = WeightClass.objects.filter(
                    divisionweightclass__division__allowed_competitions=self.instance.competition,
                    divisionweightclass__gender=athlete_profile.gender  # Filter by gender
                ).distinct()

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
