from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, AthleteProfile, OrganizerProfile, Division, WeightClass

class AthleteProfileInline(admin.StackedInline):
    model = AthleteProfile
    can_delete = False
    verbose_name_plural = 'Athlete Profile'

class OrganizerProfileInline(admin.StackedInline):
    model = OrganizerProfile
    can_delete = False
    verbose_name_plural = 'Organizer Profile'

class CustomUserAdmin(UserAdmin):
    inlines = (AthleteProfileInline, OrganizerProfileInline)
    list_display = ('username', 'email', 'role', 'is_staff')
    list_filter = ('role', 'is_staff', 'is_active')
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (('Personal info'), {'fields': (
            'first_name', 'last_name', 'email', 'date_of_birth', 'profile_picture',
            'instagram_name', 'x_name', 'facebook_name'  # Include social media fields here
        )}),
        (('Permissions'), {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        (('Important dates'), {'fields': ('last_login', 'date_joined')}),
        (('Role'), {'fields': ('role',)}),
    )


@admin.register(Division)
class DivisionAdmin(admin.ModelAdmin):
    list_display = ('name',)

@admin.register(WeightClass)
class WeightClassAdmin(admin.ModelAdmin):
    list_display = ('name', 'gender', 'federation', 'weight_d')
    fields = ('name', 'gender', 'federation', 'weight_d')

admin.site.register(User, CustomUserAdmin)