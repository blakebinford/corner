from django.db import models

from django.contrib.auth.models import AbstractUser
from django.db.models.enums import Choices
from django.utils.regex_helper import Choice
from phonenumber_field.modelfields import PhoneNumberField
from django.db import models
from django.conf import settings
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _

class User(AbstractUser):
    """
    Custom User model inheriting from AbstractUser.
    Adds fields for date of birth, profile picture, and user role.
    """
    date_of_birth = models.DateField(null=True, blank=True)
    email_verified = models.BooleanField(default=False)
    profile_picture = models.ImageField(upload_to='profile_pics/', null=True, blank=True)
    instagram_name = models.CharField(max_length=35)
    x_name = models.CharField(max_length=35)
    facebook_name = models.CharField(max_length=35)
    first_name = models.CharField(max_length=30, blank=True)
    last_name = models.CharField(max_length=150, blank=True)

    role = models.CharField(max_length=20, choices=[
        ('athlete', 'Athlete'),
        ('organizer', 'Organizer'),
        ('judge', 'Judge'),
        ('other', 'other')
    ])

    def get_full_name(self):
        """
        Return the first_name plus the last_name, with a space in between.
        """
        full_name = '%s %s' % (self.first_name, self.last_name)
        return full_name.strip()

class OrganizerProfile(models.Model):
    """
    Profile model for organizers, linked one-to-one with User.
    Stores organization name and contact information.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='organizer_profile')
    organization_name = models.CharField(max_length=255)
    contact_phone = PhoneNumberField(blank=True)
    org_email = models.EmailField(max_length=35, blank=False)

class AthleteProfile(models.Model):
    """
    Profile model for athletes, linked one-to-one with User.
    Stores weight class, division, competition history, and other athlete-specific information.
    """
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='athlete_profile')
    gender = models.CharField(max_length=20, choices=[
        ('male', 'Male'),
        ('female', 'Female')
    ])
    nickname = models.CharField(max_length=50, blank=True, help_text=_("Athlete's preferred name or alias"))
    address = models.CharField(max_length=255, blank=True, help_text=_("Athlete's address"))
    phone_number = PhoneNumberField(blank=True, help_text=_("Athlete's phone number"))
    home_gym = models.CharField(max_length=100, blank=True, help_text=_("Name of the athlete's primary gym"))
    team_name = models.CharField(max_length=100, blank=True, help_text=_("Name of the athlete's team (if any)"))
    coach = models.CharField(max_length=100, blank=True, help_text=_("Name of the athlete's coach"))
    height = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True, help_text=_("Athlete's height (in cm or inches)"))
    weight = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text=_("Athlete's weight (in kg or lbs)"))
    date_of_birth = models.DateField(null=True, blank=True, help_text=_("Athlete's date of birth"))
    whatsapp_number = PhoneNumberField(blank=True, help_text=_("Athlete's WhatsApp number"))

    def __str__(self):
        return self.user.username

class WeightClass(models.Model):
    """
    Model to store weight class information.
    """
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name  # Add this method

class Division(models.Model):
    """
    Model to store division information.
    """
    name = models.CharField(max_length=50, choices=[
        ('novice', 'Novice'),
        ('teen', 'Teen'),
        ('master', 'Master'),
        ('open','Open'),
        ('adaptive', 'Adaptive'),
    ])

    def __str__(self):
        return self.name
