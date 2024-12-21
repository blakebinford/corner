import django_filters
from django import forms
from django.forms.widgets import DateInput, Select
from .models import Competition, Division, Event

class CompetitionFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains', label='Competition Name')
    comp_date_after = django_filters.DateFilter(
        field_name='comp_date',
        lookup_expr='gte',
        widget=DateInput(attrs={'type': 'date'}),
        label='Start Date'
    )
    comp_date_before = django_filters.DateFilter(
        field_name='comp_date',
        lookup_expr='lte',
        widget=DateInput(attrs={'type': 'date'}),
        label='End Date'
    )
    location = django_filters.ChoiceFilter(
        choices=[(loc, loc) for loc in Competition.objects.values_list('location', flat=True).distinct()],
        # Dynamically populate choices
        widget=forms.Select(attrs={'class': 'form-control'}),
        empty_label="Any Location",
        label='Competition Location',
        required=False,
    )
    events = django_filters.ModelMultipleChoiceFilter(
        field_name='events__name',  # Corrected field_name
        queryset=Event.objects.all(),
        widget=forms.Select(attrs={'class': 'form-control'}),
        label='Events',
        required=False,
    )
    allowed_divisions = django_filters.ModelMultipleChoiceFilter(
        field_name='allowed_divisions',
        queryset=Division.objects.all(),
        widget=forms.Select(attrs={'class': 'form-control'}),
        label='Divisions',
        required=False,
    )

    class Meta:
        model = Competition
        fields = ['name', 'comp_date_after', 'comp_date_before', 'location', 'events', 'status', 'allowed_divisions']