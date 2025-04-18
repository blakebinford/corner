from django.contrib import admin
from .models import (
    Competition, Event, AthleteCompetition, EventImplement,
    Tag, Federation, Sponsor, Result, ZipCode, EventBase, Division, WeightClass, TshirtSize, AthleteEventNote,
    LaneAssignment, CompetitionRunOrder
)


class AthleteCompetitionInline(admin.TabularInline):
    model = AthleteCompetition
    extra = 1

@admin.register(Competition)
class CompetitionAdmin(admin.ModelAdmin):
    list_display = ('name', 'comp_date', 'city', 'state', 'publication_status', 'organizer', 'status',)
    list_filter = ('status', 'comp_date', 'publication_status')
    search_fields = ('name', 'city', 'state', 'organizer__username', 'organizer__email')

    def get_tags(self, obj):
        return ", ".join([tag.name for tag in obj.tags.all()])

    get_tags.short_description = 'Tags'
    filter_horizontal = ('allowed_divisions', 'sponsor_logos')

    def get_readonly_fields(self, request, obj=None):
        """Make 'approval_status' editable only for superusers."""
        if not request.user.is_superuser:
            return ['approval_status']
        return []

    def save_model(self, request, obj, form, change):
        """Ensure only approved competitions can be published."""
        if obj.publication_status == 'published' and obj.approval_status != 'approved':
            raise ValueError("A competition must be approved before it can be published.")
        super().save_model(request, obj, form, change)


@admin.register(Federation)
class FederationAdmin(admin.ModelAdmin):
    list_display = ('name', 'logo')


@admin.register(Sponsor)
class SponsorAdmin(admin.ModelAdmin):
    list_display = ('name', 'logo')


class EventImplementInline(admin.TabularInline):
    model = EventImplement
    extra = 1
    fields = ('event', 'implement_name', 'implement_order', 'weight', 'weight_unit')


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('name', 'weight_type', 'order')
    search_fields = ('name',)
    ordering = ('order',)
    inlines = [EventImplementInline]


@admin.register(AthleteCompetition)
class AthleteCompetitionAdmin(admin.ModelAdmin):
    list_display = ('athlete', 'competition', 'division', 'weight_class', 'payment_status', 'signed_up')
    list_filter = ('competition', 'division', 'weight_class', 'payment_status', 'signed_up')


@admin.register(EventImplement)
class EventImplementAdmin(admin.ModelAdmin):
    list_display = ('event', 'implement_name', 'implement_order', 'weight', 'weight_unit')
    list_filter = ('event',)


@admin.register(Result)
class ResultAdmin(admin.ModelAdmin):
    list_display = ('athlete_competition', 'event', 'points_earned', 'event_rank', 'value')
    search_fields = ('athlete_competition__athlete__user__username', 'event__name')
    list_filter = ('event__competition', 'event')

@admin.register(ZipCode)
class ZipCodeAdmin(admin.ModelAdmin):
    list_display = ('zip_code', 'latitude', 'longitude')
    search_fields = ('zip_code',)

@admin.register(Division)
class DivisionAdmin(admin.ModelAdmin):
    list_display = ('name', 'competition', 'is_custom')
    list_filter = ('competition', 'is_custom')
    search_fields = ('name', 'competition__name')

@admin.register(WeightClass)
class WeightClassAdmin(admin.ModelAdmin):
    list_display = ('name', 'gender', 'federation', 'weight_d', 'category', 'is_custom')
    list_filter = ('gender', 'federation',  'category', 'is_custom')
    search_fields = ('name', 'federation__name')
    ordering = ('category', 'name')

@admin.register(EventBase)
class EventBaseAdmin(admin.ModelAdmin):
    list_display = ('name',)
    ordering = ('name',)

@admin.register(TshirtSize)
class TshirtSizeAdmin(admin.ModelAdmin):
    list_display = ('size',)
    ordering = ('size',)

@admin.register(AthleteEventNote)
class AthleteEventNoteAdmin(admin.ModelAdmin):
    list_display = ('athlete_competition', 'event', 'note_type', 'note_value', 'updated_at')
    list_filter = ('event', 'note_type')
    search_fields = ('athlete_competition__athlete__user__first_name', 'athlete_competition__athlete__user__last_name', 'note_value')

# In competitions/admin.py
@admin.register(LaneAssignment)
class LaneAssignmentAdmin(admin.ModelAdmin):
    list_display = ('athlete_competition', 'event', 'lane_number', 'heat_number')
    list_filter = ('event', 'lane_number', 'heat_number')
    search_fields = ('athlete_competition__athlete__user__first_name', 'athlete_competition__athlete__user__last_name')

@admin.register(CompetitionRunOrder)
class CompetitionRunOrderAdmin(admin.ModelAdmin):
    list_display = ('competition', 'event', 'athlete_competition', 'order', 'status')
    list_filter = ('competition', 'event', 'status')
    search_fields = ('athlete_competition__athlete__user__username', 'athlete_competition__athlete__user__first_name', 'athlete_competition__athlete__user__last_name')