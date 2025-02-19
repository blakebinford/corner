from django.contrib import admin
from .models import (
    Competition, Event, EventOrder, AthleteCompetition, EventImplement,
    DivisionWeightClass, Tag, Federation, Sponsor, Result, ZipCode, EventBase
)

class EventOrderInline(admin.TabularInline):
    model = EventOrder
    extra = 1
    autocomplete_fields = ['event']

class AthleteCompetitionInline(admin.TabularInline):
    model = AthleteCompetition
    extra = 1

@admin.register(Competition)
class CompetitionAdmin(admin.ModelAdmin):
    list_display = ('name', 'comp_date', 'city', 'state', 'publication_status', 'organizer', 'status', )
    list_filter = ('status', 'comp_date', 'publication_status')
    search_fields = ('name', 'city', 'state', 'organizer__username', 'organizer__email')

    inlines = [EventOrderInline, AthleteCompetitionInline]

    def get_tags(self, obj):
        return ", ".join([tag.name for tag in obj.tags.all()])

    get_tags.short_description = 'Tags'
    filter_horizontal = ('allowed_divisions', 'allowed_weight_classes', 'sponsor_logos', 'tags')


    def get_readonly_fields(self, request, obj=None):
        """
        Make 'approval_status' editable only for superusers in the admin panel.
        """
        if not request.user.is_superuser:
            return ['approval_status']
        return []

    def save_model(self, request, obj, form, change):
        """
        Ensure only approved competitions can be published.
        """
        if obj.publication_status == 'published' and obj.approval_status != 'approved':
            raise ValueError("A competition must be approved before it can be published.")
        super().save_model(request, obj, form, change)

@admin.register(Federation)
class FederationAdmin(admin.ModelAdmin):
    list_display = ('name', 'logo')  # Display the logo in the list view

@admin.register(Sponsor)
class SponsorAdmin(admin.ModelAdmin):
    list_display = ('name', 'logo')  # Display the logo in the list view

class EventImplementInline(admin.TabularInline):
    model = EventImplement
    extra = 1
    fields = (
        'division_weight_class', 'implement_name', 'implement_order', 'weight', 'weight_unit'
    )

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('name', 'weight_type')
    search_fields = ('name',)
    inlines = [EventImplementInline]

@admin.register(AthleteCompetition)
class AthleteCompetitionAdmin(admin.ModelAdmin):
    list_display = ('athlete', 'competition', 'division', 'weight_class', 'payment_status', 'signed_up')
    list_filter = ('competition', 'division', 'weight_class', 'payment_status', 'signed_up')

@admin.register(EventOrder)
class EventOrderAdmin(admin.ModelAdmin):
    list_display = ('event', 'competition', 'order')
    list_filter = ('competition',)

@admin.register(EventImplement)
class EventImplementAdmin(admin.ModelAdmin):
    list_display = ('event', 'division_weight_class', 'implement_name', 'implement_order', 'weight', 'weight_unit')
    list_filter = ('event__competitions', 'division_weight_class__division', 'division_weight_class__weight_class')

@admin.register(DivisionWeightClass)
class DivisionWeightClassAdmin(admin.ModelAdmin):
    list_display = ('division', 'weight_class', 'gender')
    list_filter = ('division',)

admin.site.register(Tag)
admin.site.register(ZipCode)
admin.site.register(EventBase)
