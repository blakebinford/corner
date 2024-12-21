from django.core.validators import RegexValidator, MinValueValidator
from django.db import models
from tinymce.models import HTMLField

from accounts.models import User, AthleteProfile, Division, WeightClass

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
    organizer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='organized_competitions')
    image = models.ImageField(upload_to='competition_images/', null=True, blank=True)
    capacity = models.PositiveIntegerField(default=100)
    description = HTMLField(blank=True)
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

    def __str__(self):
        return self.name

class Sponsor(models.Model):
    name = models.CharField(max_length=255)
    logo = models.ImageField(upload_to='sponsor_logos/')

    def __str__(self):
        return self.name


class DivisionWeightClass(models.Model):
    division = models.ForeignKey(Division, on_delete=models.CASCADE)
    weight_class = models.ForeignKey(WeightClass, on_delete=models.CASCADE)
    gender = models.CharField(max_length=10, blank=True, choices=[
        ('male', 'Male'),
        ('female', 'Female'),
    ])

    class Meta:
        pass

    def __str__(self):
        return f"{self.weight_class.name} - {self.division.name} ({self.gender})"


class Event(models.Model):
    name = models.CharField(max_length=80, unique=True)
    competitions = models.ManyToManyField(Competition, through='EventOrder', related_name='events')
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