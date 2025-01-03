import random
from django.core.validators import RegexValidator, MinValueValidator
from django.db import models
from tinymce.models import HTMLField
from django.conf import settings
from accounts.models import User, AthleteProfile, Division, WeightClass
from django.db.models.functions import Substr, Cast, StrIndex, Coalesce
from django.db.models import DecimalField, Value, Case, When

class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name

class Federation(models.Model):
    name = models.CharField(max_length=255)
    logo = models.ImageField(upload_to='federation_logos/')  # Add logo field

    def __str__(self):
        return self.name

class Competition(models.Model):
    name = models.CharField(max_length=255)
    comp_date = models.DateField()
    location = models.CharField(max_length=255)
    start_time = models.TimeField(null=True, blank=True)
    organizer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='organized_competitions')
    image = models.ImageField(upload_to='competition_images/',
                              null=True,
                              blank=True,
                              default='competition_images/default_competition_image2.jpg',
                              )
    capacity = models.PositiveIntegerField(default=100)
    description = HTMLField(blank=True)
    event_location_name = models.CharField(max_length=255, blank=True)
    comp_end_date = models.DateField(null=True, blank=True)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=255, blank=True)
    state = models.CharField(max_length=255, blank=True)
    zip_code = models.CharField(max_length=10, blank=True)
    liability_waiver = models.TextField(blank=True)
    scoring_system = models.CharField(max_length=50)
    tags = models.ManyToManyField(Tag, related_name='competitions', blank=True)
    status = models.CharField(max_length=20, choices=[
        ('upcoming', 'Upcoming'),
        ('full', 'Full'),
        ('completed', 'Completed'),
        ('canceled', 'Canceled'),
        ('limited', 'Limited'),
        ('closed','Closed'),
    ])
    registration_deadline = models.DateTimeField()
    allowed_divisions = models.ManyToManyField(Division, related_name='allowed_competitions')
    allowed_weight_classes = models.ManyToManyField(WeightClass, related_name='allowed_competitions')
    federation = models.ForeignKey(Federation, on_delete=models.SET_NULL, null=True, blank=True)  # Add federation field
    sponsor_logos = models.ManyToManyField('Sponsor', blank=True)
    signup_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00,
                                       validators=[MinValueValidator(0.00)])
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
    def __str__(self):
        return self.name

class CommentatorNote(models.Model):
    competition = models.ForeignKey(Competition, on_delete=models.CASCADE)
    athlete = models.ForeignKey(AthleteProfile, on_delete=models.CASCADE)
    commentator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    note = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)  # Add created_at field

    def __str__(self):
        return f"Note for {self.athlete.user.get_full_name()} at {self.competition.name}"

class Sponsor(models.Model):
    name = models.CharField(max_length=255)
    logo = models.ImageField(upload_to='sponsor_logos/')

    def __str__(self):
        return self.name


class DivisionWeightClass(models.Model):
    division = models.ForeignKey(Division, on_delete=models.CASCADE)
    weight_class = models.ForeignKey(WeightClass, on_delete=models.CASCADE)
    gender = models.CharField(max_length=10, blank=True, choices=[
        ('Male', 'Male'),
        ('Female', 'Female'),
    ])

    class Meta:
        pass


    def __str__(self):
        if self.weight_class.weight_d == 'u':
            return f"{self.division.name} - ({self.gender}) {self.weight_class.weight_d}{self.weight_class.name}"
        elif self.weight_class.weight_d == '+':
            return f"{self.division.name} - ({self.gender}) {self.weight_class.name}{self.weight_class.weight_d}"
        return f"{self.division.name} - ({self.gender}) {self.weight_class.name}"

class EventBase(models.Model):
    """
    Model representing the base movement for a strongman event.
    """
    name = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.name


class Event(models.Model):
    name = models.CharField(max_length=80, unique=True)
    competitions = models.ManyToManyField(Competition, through='EventOrder', related_name='events')
    event_base = models.ForeignKey(EventBase, on_delete=models.SET_NULL, null=True)
    weight_type = models.CharField(max_length=20, choices=[
        ('time', 'Time'),
        ('distance', 'Distance'),
        ('max', 'Max Weight'),
        ('height', 'Height'),
        ('reps', 'Reps'),
    ])

    def __str__(self):
        return self.name

class EventOrder(models.Model):
    competition = models.ForeignKey(Competition, on_delete=models.CASCADE)
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.event.name} - {self.competition.name} (Order: {self.order})"

class EventImplement(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='implements')
    division_weight_class = models.ForeignKey(DivisionWeightClass, on_delete=models.CASCADE)
    implement_name = models.CharField(max_length=100, blank=True)
    implement_order = models.PositiveIntegerField(default=1)
    weight = models.IntegerField()
    weight_unit = models.CharField(max_length=20, choices=[
        ('lbs', 'lbs'),
        ('kg', 'kg'),
    ], default='lbs')

    def __str__(self):
        base_str = f"{self.weight} {self.weight_unit} - {self.division_weight_class}"
        if self.implement_name:
            return f"{self.implement_name} - {base_str}"
        return f"Implement {self.implement_order} - {base_str}"


class AthleteCompetition(models.Model):
    athlete = models.ForeignKey(AthleteProfile, on_delete=models.CASCADE)
    competition = models.ForeignKey(Competition, on_delete=models.CASCADE)
    registration_date = models.DateTimeField(auto_now_add=True)
    payment_status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('canceled', 'Canceled'),
        ('refunded', 'Refunded'),
        ('paid', 'Paid')
    ])
    registration_status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('complete', 'Complete'),
        ('canceled', 'Canceled'),
    ], default='pending')
    signed_up = models.BooleanField(default=False)
    division = models.ForeignKey(Division, on_delete=models.CASCADE, null=True, blank=True)
    weight_class = models.ForeignKey(WeightClass, on_delete=models.CASCADE, null=True, blank=True)
    total_points = models.PositiveIntegerField(default=0)
    rank = models.PositiveIntegerField(null=True, blank=True)  # Allow null for unranked athletes

    class Meta:
        unique_together = ('athlete', 'competition')

    def get_results_for_event(self, event_order):
        return self.result_set.filter(event_order=event_order).first()

    def __str__(self):
        return f"{self.athlete.user.username} - {self.competition.name}"

class Result(models.Model):
    athlete_competition = models.ForeignKey(AthleteCompetition, on_delete=models.CASCADE, related_name='results')
    event_order = models.ForeignKey(EventOrder, on_delete=models.CASCADE)
    points_earned = models.PositiveIntegerField(default=0)
    time = models.DurationField(null=True, blank=True)
    value = models.CharField(
        max_length=255,
        blank=True,
    )

    def __str__(self):
        return f"{self.athlete_competition.athlete.user.get_full_name()} - {self.event_order.event.name}"

class ZipCode(models.Model):
    zip_code = models.CharField(max_length=5, primary_key=True)
    latitude = models.FloatField()
    longitude = models.FloatField()

    def __str__(self):
        return self.zip_code