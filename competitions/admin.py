import csv
from datetime import date, timedelta

from django.contrib import admin
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import path

from .forms import ExportNationalsForm
from .utils import get_local_qualifiers, get_regional_qualifiers, get_pro_am_qualifiers, create_or_update_qualifier
from rest_framework.authtoken.models import Token
from accounts.models import AthleteProfile
from .models import (
    Competition, Event, AthleteCompetition, EventImplement,
    Tag, Federation, Sponsor, Result, ZipCode, EventBase, Division, WeightClass, TshirtSize, AthleteEventNote,
    LaneAssignment, CompetitionRunOrder, CompetitionStaff, NationalsQualifier
)

class CompetitionRunOrderInline(admin.TabularInline):
    model = CompetitionRunOrder
    extra = 0
    fields = (
        'athlete_competition',
        'get_division',
        'lane_number',
        'order',
    )
    readonly_fields = ('get_division',)
    ordering = ('lane_number', 'order')
    show_change_link = True


    def get_division(self, obj):
        return obj.athlete_competition.division
    get_division.short_description = 'Division'

    def has_add_permission(self, request, obj=None):
        return True

    def has_change_permission(self, request, obj=None):
        return True

    def has_delete_permission(self, request, obj=None):
        return True

class AthleteCompetitionInline(admin.TabularInline):
    model = AthleteCompetition
    extra = 1

class CompetitionStaffInline(admin.TabularInline):
    model = CompetitionStaff
    extra = 1
    autocomplete_fields = ['user']
    fields = ['user', 'role']
    verbose_name = "Staff Member"
    verbose_name_plural = "Competition Staff"


@admin.register(Competition)
class CompetitionAdmin(admin.ModelAdmin):
    list_display = ('name', 'comp_date', 'city', 'state', 'approval_status', 'publication_status', 'organizer', 'status',)
    list_filter = ('status', 'comp_date', 'approval_status')
    search_fields = ('name', 'city', 'state', 'organizer__username', 'organizer__email')
    inlines = [CompetitionStaffInline]
    filter_horizontal = ('allowed_divisions', 'sponsor_logos')
    fieldsets = (
        ('Timing & Access Control', {
            'fields': ('publish_at', 'registration_open_at')
        }),
    )

    def get_tags(self, obj):
        return ", ".join([tag.name for tag in obj.tags.all()])
    get_tags.short_description = 'Tags'

    def get_readonly_fields(self, request, obj=None):
        if not request.user.is_superuser:
            return ['approval_status']
        return []

    def save_model(self, request, obj, form, change):
        if obj.publication_status == 'published' and obj.approval_status != 'approved':
            raise ValueError("A competition must be approved before it can be published.")
        super().save_model(request, obj, form, change)

    # === BEGIN: Export Nationals CSV ===

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'export-nationals/',
                self.admin_site.admin_view(self.export_nationals),
                name='export-nationals-csv',
            ),
        ]
        return custom_urls + urls

    def export_nationals(self, request):
        if request.method == "POST":
            form = ExportNationalsForm(request.POST)
            if form.is_valid():
                start = form.cleaned_data.get("start_date")
                end = form.cleaned_data.get("end_date")

                if not end:
                    end = date.today()
                if not start:
                    start = end - timedelta(days=365)

                local = get_local_qualifiers(start, end)
                regional = get_regional_qualifiers(start, end)
                pro_am = get_pro_am_qualifiers(start, end)
                qualifiers = local + regional + pro_am

                response = HttpResponse(content_type='text/csv')
                response['Content-Disposition'] = 'attachment; filename="nationals_qualifiers.csv"'

                writer = csv.writer(response)
                writer.writerow([
                    'First Name', 'Last Name', 'Email',
                    'Competition Name', 'Competition Type', 'Competition Date',
                    'Division', 'Weight Class', 'Placing', 'Qualification Reason'
                ])

                for q in qualifiers:
                    create_or_update_qualifier(q)

                    writer.writerow([
                        q["user"].first_name,
                        q["user"].last_name,
                        q["user"].email,
                        q["competition"].name,
                        q["competition_type"],
                        q["competition_date"],
                        q["division"],
                        q["weight_class"],
                        q["placing"],
                        q["reason"],
                    ])

                return response
        else:
            form = ExportNationalsForm()

        return render(request, "admin/competitions/export_form.html", {"form": form})

    change_list_template = "admin/competitions/change_list.html"

    # === END: Export Nationals CSV ===



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
    inlines = [EventImplementInline, CompetitionRunOrderInline]

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)

        # Collect all existing CompetitionRunOrders for the event
        event_instance = form.instance
        comp = event_instance.competition
        event = event_instance

        # Build a map to detect conflicts
        existing_orders = {
            (ro.order): ro
            for ro in CompetitionRunOrder.objects.filter(
                competition=comp,
                event=event
            )
        }

        # Track updated orders to avoid double use
        used_orders = {}

        for instance in instances:
            key = instance.order

            if instance.pk:  # Update
                used_orders[key] = instance.pk
                instance.save()

            else:  # New entry
                # If an order already exists and it's a different row, override it
                conflicting = existing_orders.get(key)
                if conflicting and conflicting.pk != instance.pk:
                    conflicting.delete()

                instance.competition = comp
                instance.event = event
                instance.save()
                used_orders[key] = instance.pk

        # Save any many-to-many fields
        formset.save_m2m()


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


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Token)
class TokenAdmin(admin.ModelAdmin):
    list_display = ('key', 'user', 'created')
    search_fields = ('key', 'user__username')
    list_filter = ('created',)

@admin.register(NationalsQualifier)
class NationalsQualifierAdmin(admin.ModelAdmin):
    change_list_template = "admin/change_list.html"

    list_display = (
        'athlete_name',
        'email',
        'competition',
        'competition_type',
        'competition_date',
        'division',
        'weight_class',
        'placing',
        'qualified_on',
    )
    list_display_links = ('athlete_name',)

    list_filter = (
        'competition_type',
        'competition_date',
        'division',
        'weight_class',
    )
    search_fields = (
        'athlete__first_name',
        'athlete__last_name',
        'athlete__email',
        'competition__name',
    )
    date_hierarchy = 'competition_date'

    def athlete_name(self, obj):
        return obj.athlete.get_full_name()

    def email(self, obj):
        return obj.athlete.email