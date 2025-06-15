from django.contrib.auth.models import AbstractUser
from phonenumber_field.modelfields import PhoneNumberField
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    """
    Custom User model inheriting from AbstractUser.
    Adds fields for date of birth, profile picture, and user role.
    """
    date_of_birth = models.DateField(null=True, blank=True)
    email_verified = models.BooleanField(default=False)
    profile_picture = models.ImageField(upload_to='profile_pics/', null=True, blank=True)
    instagram_name = models.CharField(max_length=35, blank=True)
    x_name = models.CharField(max_length=35, blank=True)
    facebook_name = models.CharField(max_length=35, blank=True)
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

    def save(self, *args, **kwargs):
        if self.first_name:
            self.first_name = self.first_name.capitalize()
        if self.last_name:
            self.last_name = self.last_name.capitalize()
        super().save(*args, **kwargs)

class OrganizerProfile(models.Model):
    """
    Profile model for organizers, linked one-to-one with User.
    Stores organization name and contact information.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='organizer_profile')
    organization_name = models.CharField(max_length=255)
    contact_phone = PhoneNumberField(blank=True)
    org_email = models.EmailField(max_length=35, blank=False)
    stripe_account_id = models.CharField(
        max_length=64, blank=True, null=True,
        help_text="ID of the connected Stripe account"
    )

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

    STATE_CHOICES = [
        ('AL', 'Alabama'),
        ('AK', 'Alaska'),
        ('AZ', 'Arizona'),
        ('AR', 'Arkansas'),
        ('CA', 'California'),
        ('CO', 'Colorado'),
        ('CT', 'Connecticut'),
        ('DE', 'Delaware'),
        ('FL', 'Florida'),
        ('GA', 'Georgia'),
        ('HI', 'Hawaii'),
        ('ID', 'Idaho'),
        ('IL', 'Illinois'),
        ('IN', 'Indiana'),
        ('IA', 'Iowa'),
        ('KS', 'Kansas'),
        ('KY', 'Kentucky'),
        ('LA', 'Louisiana'),
        ('ME', 'Maine'),
        ('MD', 'Maryland'),
        ('MA', 'Massachusetts'),
        ('MI', 'Michigan'),
        ('MN', 'Minnesota'),
        ('MS', 'Mississippi'),
        ('MO', 'Missouri'),
        ('MT', 'Montana'),
        ('NE', 'Nebraska'),
        ('NV', 'Nevada'),
        ('NH', 'New Hampshire'),
        ('NJ', 'New Jersey'),
        ('NM', 'New Mexico'),
        ('NY', 'New York'),
        ('NC', 'North Carolina'),
        ('ND', 'North Dakota'),
        ('OH', 'Ohio'),
        ('OK', 'Oklahoma'),
        ('OR', 'Oregon'),
        ('PA', 'Pennsylvania'),
        ('RI', 'Rhode Island'),
        ('SC', 'South Carolina'),
        ('SD', 'South Dakota'),
        ('TN', 'Tennessee'),
        ('TX', 'Texas'),
        ('UT', 'Utah'),
        ('VT', 'Vermont'),
        ('VA', 'Virginia'),
        ('WA', 'Washington'),
        ('WV', 'West Virginia'),
        ('WI', 'Wisconsin'),
        ('WY', 'Wyoming'),
    ]
    nickname = models.CharField(max_length=50, blank=True, help_text=_("Athlete's preferred name or alias"))
    street_number = models.CharField(max_length=50, blank=True, help_text=_("Street number and name"))
    city = models.CharField(max_length=100, blank=True, help_text=_("City"))
    state = models.CharField(max_length=100, blank=True, help_text=_("State"))
    zip_code = models.CharField(max_length=20, blank=True, help_text=_("Zip code"))
    phone_number = PhoneNumberField(blank=True, help_text=_("Athlete's phone number"))
    home_gym = models.CharField(max_length=100, blank=True, help_text=_("Name of the athlete's primary gym"))
    team_name = models.CharField(max_length=100, blank=True, help_text=_("Name of the athlete's team (if any)"))
    coach = models.CharField(max_length=100, blank=True, help_text=_("Name of the athlete's coach"))
    height = models.IntegerField(null=True, blank=True, help_text=_("Athlete's height in inches"))
    weight = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text=_("Athlete's weight (in kg or lbs)"))
    date_of_birth = models.DateField(null=True, blank=True, help_text=_("Athlete's date of birth"))
    whatsapp_number = PhoneNumberField(blank=True, help_text=_("Athlete's WhatsApp number"))
    bio = models.TextField(blank=True)

    def __str__(self):
        return self.user.username

